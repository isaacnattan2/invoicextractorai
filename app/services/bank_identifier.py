import json
import os
from pathlib import Path

from openai import OpenAI

from app.schemas.pdf import ExtractedPDF


class BankIdentificationResult:
    def __init__(self, name: str, confidence: float):
        self.name = name
        self.confidence = confidence


def load_bank_prompt_template() -> str:
    prompt_path = Path(__file__).parent.parent / "prompts" / "bank_identification_prompt.txt"
    with open(prompt_path, "r") as f:
        return f.read()


def identify_bank(extracted_pdf: ExtractedPDF) -> BankIdentificationResult:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return BankIdentificationResult(name="Unknown", confidence=0.0)

    first_page_text = ""
    if extracted_pdf.pages:
        first_page_text = extracted_pdf.pages[0].text

    if not first_page_text.strip():
        return BankIdentificationResult(name="Unknown", confidence=0.0)

    client = OpenAI(api_key=api_key)

    prompt_template = load_bank_prompt_template()
    prompt = prompt_template.replace("{text}", first_page_text)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a bank identification system. Return only valid JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
    except Exception:
        return BankIdentificationResult(name="Unknown", confidence=0.0)

    content = response.choices[0].message.content
    if not content:
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
