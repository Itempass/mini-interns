import logging
from openai import OpenAI
from shared.app_settings import load_app_settings
from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_workflow(email_body: str):
    """
    Runs the LLM workflow to process an email using the OpenAI SDK configured for OpenRouter.
    """
    try:
        app_settings = load_app_settings()
        if not all([app_settings.OPENROUTER_API_KEY, app_settings.OPENROUTER_MODEL]):
            logger.warning("OpenRouter API key or model is not configured. Skipping workflow.")
            return

        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=app_settings.OPENROUTER_API_KEY,
        )
        redis_client = get_redis_client()

        # 1. Fetch prompts from Redis
        trigger_conditions_prompt = redis_client.get(RedisKeys.TRIGGER_CONDITIONS)
        system_prompt = redis_client.get(RedisKeys.SYSTEM_PROMPT)
        user_context = redis_client.get(RedisKeys.USER_CONTEXT)

        if not trigger_conditions_prompt:
            logger.warning("Trigger conditions prompt not set in Redis. Skipping workflow.")
            return
        
        # Decode from bytes to string
        trigger_conditions_prompt = trigger_conditions_prompt.decode('utf-8')

        # 2. First LLM call to check trigger conditions
        logger.info("Checking trigger conditions...")
        trigger_response = client.chat.completions.create(
            model=app_settings.OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": trigger_conditions_prompt},
                {"role": "user", "content": email_body},
            ],
            temperature=0.0,
        )

        decision = trigger_response.choices[0].message.content.strip().lower()
        logger.info(f"Trigger decision: {decision}")

        # 3. If trigger is met, run the second LLM call
        if "true" in decision:
            logger.info("Trigger met. Generating draft...")

            if not system_prompt or not user_context:
                logger.warning("System prompt or user context not set in Redis. Cannot generate draft.")
                return

            # Decode from bytes to string
            system_prompt = system_prompt.decode('utf-8')
            user_context = user_context.decode('utf-8')

            # Construct the full prompt for the second call
            final_prompt = f"{system_prompt}\n\nHere is some context about me: {user_context}\n\nPlease write a draft response to the following email:\n\n---\n{email_body}\n---"

            draft_response = client.chat.completions.create(
                model=app_settings.OPENROUTER_MODEL,
                messages=[
                    {"role": "user", "content": final_prompt}
                ],
            )
            
            draft_email = draft_response.choices[0].message.content
            
            # 4. Log the outcome
            logger.info("LLM Draft Generation Complete:")
            logger.info(f"----- DRAFT EMAIL -----\n{draft_email}\n-----------------------")

        else:
            logger.info("Trigger not met. No draft will be generated.")

    except Exception as e:
        logger.error(f"An error occurred in the LLM workflow: {e}", exc_info=True) 