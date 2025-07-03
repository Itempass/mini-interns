import httpx
import logging
from shared.config import settings

logger = logging.getLogger(__name__)

class OpenRouterService:
    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not found in settings.")
        
        self.base_url = "https://openrouter.ai/api/v1"
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            timeout=120  # Generous timeout for model generation
        )

    async def get_llm_response(self, prompt: str, system_prompt: str, model: str) -> str:
        """
        Gets a response from a specified LLM on OpenRouter with a given prompt.
        """
        json_payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        }
        try:
            response = await self.client.post("/chat/completions", json=json_payload)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTPStatusError calling OpenRouter: {e}")
            logger.error(f"Request body: {json_payload}")
            raise
        except (KeyError, IndexError) as e:
            logger.error(f"Error parsing OpenRouter response: {e}")
            logger.error(f"Response body: {response.text}")
            raise

# Create a singleton instance to be used by other modules
openrouter_service = OpenRouterService() 