import json
import urllib.request
import urllib.error

from app.services.llm_client import LLMClient, LLMError


class OllamaClient(LLMClient):
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self.model = "llama3.1:8b"

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.base_url}/api/chat"

        full_prompt = f"{system_prompt}\n\nIMPORTANT: You MUST respond with ONLY valid JSON. No explanations, no markdown, no code blocks. Just the raw JSON object.\n\n{user_prompt}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": full_prompt}
            ],
            "stream": False,
            "format": "json"
        }

        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=3600) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise LLMError(f"Ollama connection error: {str(e)}. Make sure Ollama is running at {self.base_url}")
        except json.JSONDecodeError:
            raise LLMError("Invalid response from Ollama")

        content = result.get("message", {}).get("content", "")
        if not content:
            raise LLMError("Empty response from Ollama")

        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        return content
