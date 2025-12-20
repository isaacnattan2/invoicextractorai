import json
import os
from pathlib import Path
from typing import List

from openai import OpenAI

from app.schemas.pdf import ExtractedPDF
from app.schemas.transaction import ExtractionResult, Transaction


class ExtractionError(Exception):
    pass


def load_prompt_template() -> str:
    prompt_path = Path(__file__).parent.parent / "prompts" / "extraction_prompt.txt"
    with open(prompt_path, "r") as f:
        return f.read()


def combine_pages_text(extracted_pdf: ExtractedPDF) -> str:
    combined_parts = []
    for page in extracted_pdf.pages:
        combined_parts.append(f"--- PAGE {page.page_number} ---\n{page.text}")
    return "\n\n".join(combined_parts)


def normalize_date(date_str: str) -> str:
    date_str = date_str.strip()
    if len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
        return date_str
    return date_str


def remove_duplicates(transactions: List[Transaction]) -> List[Transaction]:
    seen = set()
    unique = []
    for t in transactions:
        key = (t.date, t.description.lower().strip(), t.amount)
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return unique


def call_llm(text: str, retry: bool = False) -> ExtractionResult:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ExtractionError("OpenAI API key not configured")

    client = OpenAI(api_key=api_key)

    prompt_template = load_prompt_template()
    prompt = prompt_template.replace("{text}", text)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a financial data extraction system. Return only valid JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
    except Exception as e:
        raise ExtractionError(f"OpenAI API error: {str(e)}")

    content = response.choices[0].message.content
    if not content:
        raise ExtractionError("Empty response from LLM")

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise ExtractionError("Invalid JSON response from LLM")

    if "transactions" not in data:
        data = {"transactions": []}

    try:
        result = ExtractionResult(**data)
    except Exception as e:
        raise ExtractionError(f"Invalid transaction data: {str(e)}")

    return result


def calculate_average_confidence(transactions: List[Transaction]) -> float:
    if not transactions:
        return 1.0
    return sum(t.confidence for t in transactions) / len(transactions)


def extract_expenses(extracted_pdf: ExtractedPDF) -> ExtractionResult:
    combined_text = combine_pages_text(extracted_pdf)

    result = call_llm(combined_text)

    avg_confidence = calculate_average_confidence(result.transactions)
    if avg_confidence < 0.8 and result.transactions:
        result = call_llm(combined_text, retry=True)

    unique_transactions = remove_duplicates(result.transactions)

    return ExtractionResult(transactions=unique_transactions)
