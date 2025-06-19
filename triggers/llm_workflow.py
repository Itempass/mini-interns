import logging
import json
from openai import OpenAI
from shared.app_settings import load_app_settings
from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_workflow(msg):
    """
    Runs the LLM workflow to process an email using the OpenAI SDK configured for OpenRouter.
    
    Args:
        msg: The email message object from imap_tools
        
    Returns:
        Dict with workflow results including draft content if generated
    """
    try:
        app_settings = load_app_settings()
        if not all([app_settings.OPENROUTER_API_KEY, app_settings.OPENROUTER_MODEL]):
            logger.warning("OpenRouter API key or model is not configured. Skipping workflow.")
            return {"should_create_draft": False, "message": "OpenRouter not configured"}
        
        # Extract email body from message
        email_body = msg.text or msg.html

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
            return {"should_create_draft": False, "message": "Trigger conditions prompt not set"}
        
        with open("triggers/triggercondition_systemprompt.md", "r") as f:
            trigger_system_prompt = f.read()

        # 2. First LLM call to check trigger conditions
        logger.info("Checking trigger conditions...")
        
        trigger_response = client.chat.completions.create(
            model=app_settings.OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": trigger_system_prompt},
                {"role": "user", "content": trigger_conditions_prompt},
                {"role": "user", "content": email_body},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        decision = False
        try:
            response_content = trigger_response.choices[0].message.content
            decision_json = json.loads(response_content)
            decision = decision_json.get("should_draft", False)
        except (json.JSONDecodeError, AttributeError):
            logger.warning(f"Could not parse decision from LLM, will not draft. Got: {response_content}")

        logger.info(f"Trigger decision: {decision}")

        # 3. If trigger is met, run the second LLM call
        if decision:
            logger.info("Trigger met. Generating draft...")

            if not system_prompt or not user_context:
                logger.warning("System prompt or user context not set in Redis. Cannot generate draft.")
                return {"should_create_draft": False, "message": "System prompt or user context not set"}

            draft_response = client.chat.completions.create(
                model=app_settings.OPENROUTER_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Here is some context: {user_context}"},
                    {"role": "user", "content": f"Please write a draft response to the following email:\n\n---\n{email_body}\n---"}
                ],
            )
            
            draft_email = draft_response.choices[0].message.content
            
            # 4. Log the outcome
            logger.info("LLM Draft Generation Complete:")
            logger.info(f"----- DRAFT EMAIL -----\n{draft_email}\n-----------------------")
            
            return {
                "should_create_draft": True,
                "draft_content": draft_email,
                "original_message": msg,
                "message": "Draft generated successfully"
            }

        else:
            logger.info("Trigger not met. No draft will be generated.")
            return {"should_create_draft": False, "message": "Trigger conditions not met"}

    except Exception as e:
        logger.error(f"An error occurred in the LLM workflow: {e}", exc_info=True)
        return {"should_create_draft": False, "message": f"Error in workflow: {str(e)}"} 