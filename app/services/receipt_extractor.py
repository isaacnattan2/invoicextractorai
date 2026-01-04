import json
from pathlib import Path

from app.schemas.receipt import ReceiptExtractionResult, ReceiptItem
from app.services.llm_client import LLMClient, LLMError, get_llm_client


class ReceiptExtractionError(Exception):
    pass


def load_receipt_prompt_template() -> str:
    prompt_path = Path(__file__).parent.parent / "prompts" / "receipt_extraction_full_nfce.txt"
    with open(prompt_path, "r") as f:
        return f.read()


def build_receipt_llm_prompt(text: str) -> str:
    prompt_template = load_receipt_prompt_template()
    return prompt_template.replace("{text}", text)


def call_receipt_llm(text: str, llm_client: LLMClient) -> ReceiptExtractionResult:
    prompt = build_receipt_llm_prompt(text)

    system_prompt = "You are a receipt data extraction system. Return only valid JSON."

    try:
        content = llm_client.chat(system_prompt, prompt)
    except LLMError as e:
        raise ReceiptExtractionError(str(e))

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise ReceiptExtractionError("Invalid JSON response from LLM")

    if "items" not in data:
        data["items"] = []

    try:
        result = ReceiptExtractionResult(**data)
    except Exception as e:
        raise ReceiptExtractionError(f"Invalid receipt data: {str(e)}")

    return result


def extract_receipt_items(text: str, provider: str = "offline") -> ReceiptExtractionResult:
    try:
        llm_client = get_llm_client(provider)
    except LLMError as e:
        raise ReceiptExtractionError(str(e))

    result = call_receipt_llm(text, llm_client)

    return result
