import json
import logging
from pathlib import Path
from typing import List, Dict, Any

from app.schemas.receipt import ReceiptExtractionResult, ReceiptItem
from app.services.llm_client import LLMClient, LLMError, get_llm_client

logger = logging.getLogger(__name__)

BATCH_SIZE = 30
ITEM_BLOCK_START = "===== ITEM_BLOCK_START ====="
ITEM_BLOCK_END = "===== ITEM_BLOCK_END ====="


class SegmentedExtractionError(Exception):
    pass


def load_prompt_template(prompt_path: str) -> str:
    full_path = Path(__file__).parent.parent / "prompts" / prompt_path
    with open(full_path, "r") as f:
        return f.read()


def extract_global_data(text: str, llm_client: LLMClient) -> dict:
    logger.warning("[SKELETON] Phase 1: Starting global data extraction")
    prompt_template = load_prompt_template(
        "receipt_extraction_segmentation_strategy/extraction_global_data.txt"
    )
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

    logger.warning(
        "[SKELETON] Phase 1 completed: Global data extracted - market_name=%s, cnpj=%s",
        data.get("market_name"),
        data.get("cnpj"),
    )
    return data


def extract_skeleton(text: str, llm_client: LLMClient) -> dict:
    logger.warning("[SKELETON] Phase 2: Starting skeleton extraction")
    prompt_template = load_prompt_template("skeleton_strategy/skeleton_extraction_prompt.txt")
    prompt = prompt_template.replace("{text}", text)
    system_prompt = "You are a receipt structural analysis system. Return only valid JSON."

    try:
        content = llm_client.chat(system_prompt, prompt)
    except LLMError as e:
        raise SegmentedExtractionError(f"Skeleton extraction failed: {str(e)}")

    try:
        logger.warning("[SKELETON] Phase 2: Raw skeleton response: %s", content[:500] if len(content) > 500 else content)
        data = json.loads(content)
    except json.JSONDecodeError:
        raise SegmentedExtractionError("Invalid JSON response from LLM for skeleton")

    if "total_items" not in data or "items" not in data:
        raise SegmentedExtractionError("Skeleton response missing 'total_items' or 'items' field")

    total_items = data["total_items"]
    items = data["items"]

    if len(items) != total_items:
        logger.warning(
            "[SKELETON] Phase 2: Warning - total_items=%d but items array has %d elements",
            total_items,
            len(items),
        )

    logger.warning(
        "[SKELETON] Phase 2 completed: Skeleton extracted with %d items",
        len(items),
    )
    return data


def extract_item_text_by_anchors(
    text: str, skeleton_items: List[dict]
) -> List[str]:
    logger.warning(
        "[SKELETON] Phase 3a: Extracting item text blocks using anchors for %d items",
        len(skeleton_items),
    )

    item_texts = []
    cursor = 0

    for idx, item in enumerate(skeleton_items):
        sequence = item.get("sequence", idx + 1)
        start_anchor = item.get("start_anchor", "")
        end_anchor = item.get("end_anchor", "")

        if not start_anchor or not end_anchor:
            raise SegmentedExtractionError(
                f"Item {sequence} missing start_anchor or end_anchor"
            )

        start_idx = text.find(start_anchor, cursor)
        if start_idx == -1:
            logger.warning(
                "[SKELETON] Phase 3a: Could not find start_anchor for item %d: '%s' (cursor=%d)",
                sequence,
                start_anchor[:50],
                cursor,
            )
            raise SegmentedExtractionError(
                f"Could not find start_anchor for item {sequence}: '{start_anchor[:50]}'"
            )

        end_idx = text.find(end_anchor, start_idx)
        if end_idx == -1:
            logger.warning(
                "[SKELETON] Phase 3a: Could not find end_anchor for item %d: '%s' (start_idx=%d)",
                sequence,
                end_anchor[:50],
                start_idx,
            )
            raise SegmentedExtractionError(
                f"Could not find end_anchor for item {sequence}: '{end_anchor[:50]}'"
            )

        slice_end = end_idx + len(end_anchor)
        block_text = text[start_idx:slice_end]
        item_texts.append(block_text)

        cursor = slice_end

        logger.warning(
            "[SKELETON] Phase 3a: Extracted text for item %d (chars %d-%d, length=%d)",
            sequence,
            start_idx,
            slice_end,
            len(block_text),
        )

    logger.warning(
        "[SKELETON] Phase 3a completed: Extracted %d item text blocks",
        len(item_texts),
    )
    return item_texts


def build_delimited_batch_input(item_texts: List[str]) -> str:
    blocks = []
    for item_text in item_texts:
        block = f"{ITEM_BLOCK_START}\n{item_text}\n{ITEM_BLOCK_END}"
        blocks.append(block)
    return "\n\n".join(blocks)


def extract_items_from_batch(
    batch_input: str, expected_count: int, llm_client: LLMClient
) -> List[dict]:
    prompt_template = load_prompt_template("skeleton_strategy/item_extraction_prompt.txt")
    prompt = prompt_template.replace("{text}", batch_input)
    system_prompt = "You are a receipt item extraction system. Return only valid JSON array."

    try:
        content = llm_client.chat(system_prompt, prompt)
    except LLMError as e:
        raise SegmentedExtractionError(f"Item batch extraction failed: {str(e)}")

    try:
        items = json.loads(content)
    except json.JSONDecodeError:
        raise SegmentedExtractionError("Invalid JSON response from LLM for item extraction")

    if not isinstance(items, list):
        raise SegmentedExtractionError("Item extraction response is not a JSON array")

    if len(items) != expected_count:
        logger.warning(
            "[SKELETON] Phase 3b: Item count mismatch - expected %d, got %d",
            expected_count,
            len(items),
        )
        raise SegmentedExtractionError(
            f"Item count mismatch: expected {expected_count}, got {len(items)}"
        )

    return items


def extract_items_paginated(
    text: str, skeleton: dict, llm_client: LLMClient
) -> List[dict]:
    skeleton_items = skeleton.get("items", [])
    total_items = len(skeleton_items)

    if total_items == 0:
        logger.warning("[SKELETON] Phase 3: No items in skeleton, returning empty list")
        return []

    item_texts = extract_item_text_by_anchors(text, skeleton_items)

    all_items = []
    total_batches = (total_items + BATCH_SIZE - 1) // BATCH_SIZE

    logger.warning(
        "[SKELETON] Phase 3b: Starting paginated extraction - %d items in %d batches (batch_size=%d)",
        total_items,
        total_batches,
        BATCH_SIZE,
    )

    for batch_num in range(total_batches):
        start_idx = batch_num * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, total_items)
        batch_item_texts = item_texts[start_idx:end_idx]
        batch_size = len(batch_item_texts)

        logger.warning(
            "[SKELETON] Phase 3b: Processing batch %d/%d (items %d-%d, count=%d)",
            batch_num + 1,
            total_batches,
            start_idx + 1,
            end_idx,
            batch_size,
        )

        batch_input = build_delimited_batch_input(batch_item_texts)

        batch_items = extract_items_from_batch(batch_input, batch_size, llm_client)

        all_items.extend(batch_items)

        logger.warning(
            "[SKELETON] Phase 3b: Batch %d/%d completed - extracted %d items (total so far: %d)",
            batch_num + 1,
            total_batches,
            len(batch_items),
            len(all_items),
        )

    logger.warning(
        "[SKELETON] Phase 3 completed: Extracted %d items total",
        len(all_items),
    )
    return all_items


def consolidate_result(global_data: dict, items: List[dict]) -> ReceiptExtractionResult:
    logger.warning("[SKELETON] Phase 4: Consolidating result with %d items", len(items))

    receipt_items = []
    for idx, item_data in enumerate(items):
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
            raise SegmentedExtractionError(f"Invalid item data at index {idx}: {str(e)}")

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

    logger.warning("[SKELETON] Phase 4 completed: Result consolidated successfully")
    return result


def extract_receipt_segmented(
    text: str,
    provider: str = "offline",
    enable_chunking: bool = False,
    chunk_size: int = 10,
) -> ReceiptExtractionResult:
    logger.warning(
        "[SKELETON] Starting skeleton-based extraction (provider=%s)",
        provider,
    )

    try:
        llm_client = get_llm_client(provider)
    except LLMError as e:
        raise SegmentedExtractionError(str(e))

    global_data = extract_global_data(text, llm_client)

    skeleton = extract_skeleton(text, llm_client)

    items = extract_items_paginated(text, skeleton, llm_client)

    result = consolidate_result(global_data, items)

    logger.warning(
        "[SKELETON] Skeleton-based extraction completed successfully with %d items",
        len(result.items),
    )
    return result
