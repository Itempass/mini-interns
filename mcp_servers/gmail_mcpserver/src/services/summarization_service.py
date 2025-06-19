"""
Service to handle email summarization using OpenAI.
"""
import os
import logging
from typing import List
from openai import OpenAI, OpenAIError
from dotenv import load_dotenv

# Set up logging
logger = logging.getLogger(__name__)

load_dotenv(override=True)

# The prompt is based on the one used in the vectorization worker
SUMMARIZATION_PROMPT = "You are an expert email summarizer. Summarize this email in 3 sentences or less. Provide only the summary, with no additional commentary."

class SummarizationService:
    """A service to summarize email content using an OpenAI model."""

    def __init__(self):
        """Initializes the SummarizationService."""
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.summarization_model = os.getenv("OPENAI_COMPLETIONS_MODEL", "gpt-4-turbo")
        
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set.")
        
        self.client = OpenAI(api_key=self.api_key)
        logger.info(f"[SummarizationService] Initialized with model: {self.summarization_model}")

    def summarize_email_body(self, body: str) -> str:
        """
        Summarizes the body of an email.

        Args:
            body: The email content to summarize.

        Returns:
            The summarized text.
        
        Raises:
            Exception: If the summarization fails.
        """
        if not body or not isinstance(body, str):
            logger.error("[SummarizationService] Invalid input: Email body cannot be empty or non-string.")
            raise ValueError("Input body cannot be empty or non-string.")

        try:
            logger.debug(f"[SummarizationService] Summarizing email body: '{body[:100]}...'")
            response = self.client.chat.completions.create(
                model=self.summarization_model,
                messages=[
                    {"role": "system", "content": SUMMARIZATION_PROMPT},
                    {"role": "user", "content": body}
                ],
                temperature=0.2, # Lower temperature for more factual summaries
                max_tokens=150
            )
            summary = response.choices[0].message.content.strip()
            logger.debug(f"[SummarizationService] Successfully created summary: '{summary[:100]}...'")
            return summary
        except OpenAIError as e:
            logger.error(f"[SummarizationService] OpenAI API error during summarization: {e}")
            raise Exception(f"Failed to summarize due to OpenAI API error: {e}") from e
        except Exception as e:
            logger.error(f"[SummarizationService] An unexpected error occurred during summarization: {e}")
            raise Exception(f"An unexpected error occurred while summarizing: {e}") from e 