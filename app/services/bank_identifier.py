import json
from pathlib import Path

from app.schemas.pdf import ExtractedPDF
from app.services.llm_client import LLMError, get_llm_client


class BankIdentificationResult:
    def __init__(self, name: str, confidence: float):
        self.name = name
        self.confidence = confidence


def load_bank_prompt_template() -> str:
    prompt_path = Path(__file__).parent.parent / "prompts" / "bank_identification_prompt.txt"
    with open(prompt_path, "r") as f:
        return f.read()


def identify_bank(extracted_pdf: ExtractedPDF, provider: str = "offline") -> BankIdentificationResult:
    first_page_text = ""
    if extracted_pdf.pages:
        first_page_text = extracted_pdf.pages[0].text

    if not first_page_text.strip():
        return BankIdentificationResult(name="Unknown", confidence=0.0)

    try:
        llm_client = get_llm_client(provider)
    except LLMError:
        return BankIdentificationResult(name="Unknown", confidence=0.0)

    prompt_template = load_bank_prompt_template()
    prompt = prompt_template.replace("{text}", first_page_text)

    system_prompt = "You are a bank identification system. Return only valid JSON."

    try:
        content = llm_client.chat(system_prompt, prompt)
    except LLMError:
        return BankIdentificationResult(name="Unknown", confidence=0.0)

    try:
        data = json.loads(content)
        name = data.get("name", "Unknown")
        confidence = float(data.get("confidence", 0.0))
        if confidence < 0.5:
            name = "Unknown"
        return BankIdentificationResult(name=name, confidence=confidence)
    except (json.JSONDecodeError, ValueError):
        return BankIdentificationResult(name="Unknown", confidence=0.0)
