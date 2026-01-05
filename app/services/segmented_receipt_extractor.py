import json
from pathlib import Path
from typing import List, Optional

from app.schemas.receipt import ReceiptExtractionResult, ReceiptItem
from app.services.llm_client import LLMClient, LLMError, get_llm_client


class SegmentedExtractionError(Exception):
    pass


def load_prompt_template(prompt_name: str) -> str:
    prompt_path = (
        Path(__file__).parent.parent
        / "prompts"
        / "receipt_extraction_segmentation_strategy"
        / prompt_name
    )
    with open(prompt_path, "r") as f:
        return f.read()


def extract_global_data(text: str, llm_client: LLMClient) -> dict:
    prompt_template = load_prompt_template("extraction_global_data.txt")
    prompt = prompt_template.replace("{text}", text)
    system_prompt = "You are a receipt data extraction system. Return only valid JSON."

    try:
        content = llm_client.chat(system_prompt, prompt)
    except LLMError as e:
        raise SegmentedExtractionError(f"Global data extraction failed: {str(e)}")

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise SegmentedExtractionError("Invalid JSON response from LLM for global data")

    return data


def segment_item_blocks(text: str, llm_client: LLMClient) -> List[str]:
    prompt_template = load_prompt_template("segmentation_item_blocks.txt")
    prompt = prompt_template.replace("{text}", text)
    system_prompt = "You are a text segmentation system. Return only valid JSON."

    try:
        content = llm_client.chat(system_prompt, prompt)
    except LLMError as e:
        raise SegmentedExtractionError(f"Segmentation failed: {str(e)}")

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise SegmentedExtractionError("Invalid JSON response from LLM for segmentation")

    if "product_blocks" not in data:
        raise SegmentedExtractionError("Segmentation response missing 'product_blocks' field")

    return data["product_blocks"]


def extract_single_item(block: str, llm_client: LLMClient) -> dict:
    prompt_template = load_prompt_template("extraction_from_item_blocks.txt")
    prompt = prompt_template.replace("{text}", block)
    system_prompt = "You are a receipt item extraction system. Return only valid JSON."

    try:
        content = llm_client.chat(system_prompt, prompt)
    except LLMError as e:
        raise SegmentedExtractionError(f"Item extraction failed: {str(e)}")

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise SegmentedExtractionError("Invalid JSON response from LLM for item extraction")

    return data


def extract_items_from_blocks(
    blocks: List[str],
    llm_client: LLMClient,
    enable_chunking: bool = False,
    chunk_size: int = 10
) -> List[dict]:
    if not blocks:
        return []

    all_items = []

    if not enable_chunking:
        for block in blocks:
            item = extract_single_item(block, llm_client)
            all_items.append(item)
    else:
        for i in range(0, len(blocks), chunk_size):
            chunk = blocks[i : i + chunk_size]
            for block in chunk:
                item = extract_single_item(block, llm_client)
                all_items.append(item)

    return all_items


def consolidate_result(global_data: dict, items: List[dict]) -> ReceiptExtractionResult:
    receipt_items = []
    for item_data in items:
        try:
            receipt_item = ReceiptItem(
                item_id=item_data.get("item_id"),
                item=item_data.get("item", ""),
                quantidade=item_data.get("quantidade", 0),
                valor_unitario=item_data.get("valor_unitario", 0),
                valor_total=item_data.get("valor_total", 0),
                desconto=item_data.get("desconto", 0),
                ean=item_data.get("ean"),
            )
            receipt_items.append(receipt_item)
        except Exception as e:
            raise SegmentedExtractionError(f"Invalid item data: {str(e)}")

    try:
        result = ReceiptExtractionResult(
            market_name=global_data.get("market_name"),
            cnpj=global_data.get("cnpj"),
            address=global_data.get("address"),
            access_key=global_data.get("access_key"),
            issue_date=global_data.get("issue_date"),
            items=receipt_items,
        )
    except Exception as e:
        raise SegmentedExtractionError(f"Failed to consolidate result: {str(e)}")

    return result


def extract_receipt_segmented(
    text: str,
    provider: str = "offline",
    enable_chunking: bool = False,
    chunk_size: int = 10
) -> ReceiptExtractionResult:
    try:
        llm_client = get_llm_client(provider)
    except LLMError as e:
        raise SegmentedExtractionError(str(e))

    global_data = extract_global_data(text, llm_client)

    blocks = segment_item_blocks(text, llm_client)

    items = extract_items_from_blocks(
        blocks,
        llm_client,
        enable_chunking=enable_chunking,
        chunk_size=chunk_size
    )

    result = consolidate_result(global_data, items)

    return result
