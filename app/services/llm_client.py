from abc import ABC, abstractmethod
from typing import Optional


class LLMClient(ABC):
    @abstractmethod
    def chat(self, system_prompt: str, user_prompt: str) -> str:
        pass


class LLMError(Exception):
    pass


def get_llm_client(provider: str) -> LLMClient:
    if provider == "offline":
        from app.services.ollama_client import OllamaClient
        return OllamaClient()
    elif provider == "online":
        from app.services.openai_client import OpenAIClient
        return OpenAIClient()
    else:
        raise LLMError(f"Unknown LLM provider: {provider}")
