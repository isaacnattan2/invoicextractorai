import logging
import os

from openai import OpenAI

from app.services.llm_client import LLMClient, LLMError

logger = logging.getLogger(__name__)


class OpenAIClient(LLMClient):
    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise LLMError("OpenAI API key not configured")
        self.client = OpenAI(api_key=self.api_key)

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0,
                response_format={"type": "json_object"}
            )
        except Exception as e:
            logger.exception("OpenAI API request failed")
            raise LLMError(f"OpenAI API error: {str(e)}") from e

        content = response.choices[0].message.content
        if not content:
            raise LLMError("Empty response from OpenAI")

        return content
