import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Dict, Any

from app.schemas.receipt import ReceiptExtractionResult, ReceiptItem
from app.services.llm_client import LLMClient, LLMError, get_llm_client

from difflib import SequenceMatcher

import re
from typing import List

import os

class SegmentedExtractionError(Exception):
    pass

logger = logging.getLogger(__name__)

# Evita duplicação de logs
if not logger.handlers:

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # Handler de arquivo com rotação
    file_handler = RotatingFileHandler(
        filename="app.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    # (Opcional) handler de console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

BATCH_SIZE = 10
ITEM_BLOCK_START = "===== ITEM_BLOCK_START ====="
ITEM_BLOCK_END = "===== ITEM_BLOCK_END ====="


class SegmentedExtractionError(Exception):
    pass


def load_prompt_template(prompt_path: str) -> str:
    full_path = Path(__file__).parent.parent / "prompts" / prompt_path
    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
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


def sanitize_prompt(prompt: str) -> str:
    return prompt.encode("utf-8", errors="ignore").decode("utf-8")

def extract_skeleton_with_llm(text: str, llm_client: LLMClient) -> dict:
    logger.warning("[SKELETON] Phase 2: Starting skeleton extraction")
    prompt_template = sanitize_prompt(load_prompt_template("skeleton_strategy/skeleton_extraction_prompt_v3.txt"))
    prompt = prompt_template.replace("{text}", text)
    system_prompt = "You are a receipt structural analysis system. Return only valid JSON."

    try:
        content = llm_client.chat(system_prompt, prompt)
    except LLMError as e:
        raise SegmentedExtractionError(f"Skeleton extraction failed: {str(e)}")

    try:
        # logger.warning("[SKELETON] Phase 2: Raw skeleton response: %s", content[:500] if len(content) > 500 else content)
        logger.warning("[SKELETON] Phase 2: Raw skeleton response: %s", content)
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

def fuzzy_find(text: str, pattern: str, start: int, window: int = 800, threshold: float = 0.85):
    """
    Procura pattern no text a partir de start usando similaridade.
    Retorna o índice do melhor match ou -1.
    """
    best_ratio = 0.0
    best_idx = -1
    pat_len = len(pattern)

    search_end = min(len(text), start + 5000)

    for i in range(start, search_end - pat_len):
        chunk = text[i : i + pat_len + window]

        ratio = SequenceMatcher(None, chunk[:pat_len], pattern).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_idx = i

    if best_ratio >= threshold:
        return best_idx

    return -1


def extract_item_text_by_anchors(
    text: str, skeleton_items: List[dict]
) -> List[str]:
    logger.warning(
        "[SKELETON] Phase 3a: Extracting item text blocks using anchors for %d items",
        len(skeleton_items),
    )

    item_texts = []
    cursor = 0

    # versão auxiliar para busca case-insensitive
    text_lower = text.lower()

    for idx, item in enumerate(skeleton_items):
        logger.warning("[SKELETON] Phase 3a: item:")
        logger.warning(idx)
        logger.warning(item)

        sequence = item.get("sequence", idx + 1)
        start_anchor = item.get("start_anchor", "")
        end_anchor = item.get("end_anchor", "")

        if not start_anchor or not end_anchor:
            raise SegmentedExtractionError(
                f"Item {sequence} missing start_anchor or end_anchor"
            )

        logger.warning(
            "[SKELETON] Phase 3a: cursor: '%d'",
            cursor
        )

        # start_anchor continua case-sensitive
        start_idx = text.find(start_anchor, cursor)

        if start_idx == -1:
            logger.warning(
                "[SKELETON] Exact start_anchor not found for item %d, trying fuzzy match",
                sequence,
            )

            start_idx = fuzzy_find(text, start_anchor, cursor)

            if start_idx == -1:
                raise SegmentedExtractionError(
                    f"Could not find start_anchor (exact or fuzzy) for item {sequence}: '{start_anchor[:50]}'"
                )


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

        # end_anchor passa a ser case-insensitive
        end_anchor_lower = end_anchor.lower()
        end_idx = text_lower.find(end_anchor_lower, start_idx)

        if end_idx == -1:
            logger.warning(
                "[SKELETON] Phase 3a: Could not find end_anchor (case-insensitive) for item %d: '%s' (start_idx=%d)",
                sequence,
                end_anchor[:50],
                start_idx,
            )
            raise SegmentedExtractionError(
                f"Could not find end_anchor for item {sequence}: '{end_anchor[:50]}'"
            )

        if end_idx < start_idx:
            raise SegmentedExtractionError(
                f"Invalid anchor order for item {sequence}"
            )

        logger.debug(
            "[SKELETON] Anchors resolved: start=%d end=%d cursor=%d",
            start_idx,
            end_idx,
            cursor
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
    prompt_template = load_prompt_template(
        "skeleton_strategy/item_extraction_prompt_v2.txt"
    )
    prompt = prompt_template.replace("{text}", batch_input)
    system_prompt = (
        "You are a receipt item extraction system. "
        "Return only valid JSON."
    )

    try:
        content = llm_client.chat(system_prompt, prompt)
        logger.warning(
            "[SKELETON] Phase 3b: LLM RESPONSE CONTENT:\n%s",
            content,
        )
    except LLMError as e:
        raise SegmentedExtractionError(
            f"Item batch extraction failed: {str(e)}"
        )

    # --------------------------------------------------
    # PARSE JSON
    # --------------------------------------------------
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise SegmentedExtractionError(
            f"Invalid JSON response from LLM for item extraction: {str(e)}"
        )

    # --------------------------------------------------
    # ACCEPT WRAPPER { "items": [...] }
    # --------------------------------------------------
    if not isinstance(data, dict) or "items" not in data:
        raise SegmentedExtractionError(
            "LLM response must be a JSON object with an 'items' array"
        )

    items = data["items"]

    if not isinstance(items, list):
        raise SegmentedExtractionError(
            "'items' must be a JSON ARRAY"
        )

    # --------------------------------------------------
    # COUNT VALIDATION
    # --------------------------------------------------
    if len(items) != expected_count:
        logger.warning(
            "[SKELETON] Phase 3b: Item count mismatch - expected %d, got %d",
            expected_count,
            len(items),
        )
        raise SegmentedExtractionError(
            f"Item count mismatch: expected {expected_count}, got {len(items)}"
        )

    # --------------------------------------------------
    # PER-ITEM VALIDATION
    # --------------------------------------------------
    REQUIRED_FIELDS = {
        "item",
        "quantidade",
        "valor_unitario",
        "valor_total",
        "desconto",
        "ean",
    }

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise SegmentedExtractionError(
                f"Item {idx + 1} is not a JSON object"
            )

        missing = REQUIRED_FIELDS - item.keys()
        if missing:
            raise SegmentedExtractionError(
                f"Item {idx + 1} missing required fields: {missing}"
            )

    return items



# def extract_items_from_batch(
#     batch_input: str, expected_count: int, llm_client: LLMClient
# ) -> List[dict]:
#     prompt_template = load_prompt_template("skeleton_strategy/item_extraction_prompt.txt")
#     prompt = prompt_template.replace("{text}", batch_input)
#     system_prompt = "You are a receipt item extraction system. Return only valid JSON array."

#     try:
#         content = llm_client.chat(system_prompt, prompt)
#         logger.warning(
#             "[SKELETON] Phase 3b: LLM RESPONSE CONTENT %s",
#             content
#         )
#     except LLMError as e:
#         raise SegmentedExtractionError(f"Item batch extraction failed: {str(e)}")

#     try:
#         items = json.loads(content)
#     except json.JSONDecodeError:
#         raise SegmentedExtractionError("Invalid JSON response from LLM for item extraction")

#     if not isinstance(content, dict) or "items" not in content:
#         raise SegmentedExtractionError("LLM response must be a JSON object with 'items'")

#     items = content["items"]

#     if not isinstance(items, list):
#         raise SegmentedExtractionError("'items' must be a JSON array")

#     if len(items) != expected_count:
#         logger.warning(
#             "[SKELETON] Phase 3b: Item count mismatch - expected %d, got %d",
#             expected_count,
#             len(items),
#         )
#         raise SegmentedExtractionError(
#             f"Item count mismatch: expected {expected_count}, got {len(items)}"
#         )

#     return items


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

    # skeleton = extract_skeleton_with_llm(text, llm_client)
    skeleton = extract_skeleton_by_cofins(text)

    #items = extract_items_paginated(text, skeleton, llm_client)
    #items = extract_items_paginated_with_deterministic_skeleton(text, skeleton, llm_client)
    items = extract_items_single_loop_with_deterministic_skeleton(text, skeleton, llm_client)

    result = consolidate_result(global_data, items)

    logger.warning(
        "[SKELETON] Skeleton-based extraction completed successfully with %d items",
        len(result.items),
    )
    return result

def extract_skeleton_by_cofins(text: str) -> dict:
    """
    Geração determinística de skeleton baseada em COFINS,
    descartando o último item (footer),
    com auditoria completa em arquivo de log separado.
    """

    logger.warning(
        "[SKELETON] Phase 2: Starting skeleton extraction (deterministic COFINS mode)"
    )

    if not text or not text.strip():
        raise SegmentedExtractionError("Empty OCR text")

    # Normalização defensiva (encoding / OCR sujo)
    text = text.encode("utf-8", errors="replace").decode("utf-8")

    audit_log_path = os.path.join(os.getcwd(), "skeleton_items_audit.log")

    # Limpa o arquivo de auditoria
    with open(audit_log_path, "w", encoding="utf-8") as audit_file:
        audit_file.write("=== SKELETON ITEMS AUDIT LOG ===\n\n")

    cofins_matches = list(re.finditer(r"cofins", text, re.IGNORECASE))

    logger.warning(
        "[SKELETON][AUDIT] Total COFINS matches found: %d",
        len(cofins_matches),
    )

    if len(cofins_matches) < 2:
        raise SegmentedExtractionError(
            "Not enough COFINS blocks to extract items (need at least 2)"
        )

    items = []
    cursor = 0

    # IMPORTANTE:
    # percorremos TODOS para log,
    # mas descartamos o ÚLTIMO como item útil (footer)
    with open(audit_log_path, "a", encoding="utf-8") as audit_file:
        for idx, match in enumerate(cofins_matches):
            end_idx = match.end()
            block_text = text[cursor:end_idx].strip()

            # Log completo de auditoria (inclusive footer)
            audit_file.write(f"{'=' * 80}\n")
            audit_file.write(f"ITEM {idx + 1}\n")
            audit_file.write(f"CHARS {cursor}-{end_idx} (length={len(block_text)})\n")
            audit_file.write(f"END ANCHOR: {match.group(0)}\n\n")
            audit_file.write(block_text)
            audit_file.write("\n\n")

            logger.warning(
                "[SKELETON][AUDIT] Item %d written to audit log (chars %d-%d, length=%d)",
                idx + 1,
                cursor,
                end_idx,
                len(block_text),
            )

            # Só adiciona ao skeleton se NÃO for o último (footer)
            if idx < len(cofins_matches) - 1:
                items.append({
                    "sequence": idx + 1,
                    "start_anchor": "__DETERMINISTIC_START__",
                    "end_anchor": match.group(0),
                })

            cursor = end_idx

    data = {
        "total_items": len(items),
        "items": items,
    }

    logger.warning(
        "[SKELETON] Phase 2 completed: Skeleton extracted with %d items (footer discarded)",
        len(items),
    )
    logger.warning(
        "[SKELETON][AUDIT] Full item texts written to: %s",
        audit_log_path,
    )

    return data

def extract_items_single_loop_with_deterministic_skeleton(
    text: str,
    skeleton: dict,
    llm_client: LLMClient
) -> List[dict]:
    """
    Extração de itens com 1 chamada ao LLM por item,
    usando segmentação determinística por COFINS
    e prompt single-item.
    """

    skeleton_items = skeleton.get("items", [])
    total_items = len(skeleton_items)

    if total_items == 0:
        logger.warning("[SKELETON] Phase 3: No items in skeleton, returning empty list")
        return []

    logger.warning(
        "[SKELETON] Phase 3: Starting SINGLE-ITEM extraction (%d items)",
        total_items,
    )

    # Normalização defensiva
    text = text.encode("utf-8", errors="replace").decode("utf-8")

    cofins_matches = list(re.finditer(r"cofins", text, re.IGNORECASE))

    if len(cofins_matches) < total_items:
        raise SegmentedExtractionError(
            f"COFINS count ({len(cofins_matches)}) smaller than skeleton items ({total_items})"
        )

    prompt_template = load_prompt_template(
        "skeleton_strategy/single_item_extraction_prompt.txt"
    )

    all_items: List[dict] = []
    cursor = 0

    for idx in range(total_items):
        match = cofins_matches[idx]
        end_idx = match.end()

        item_text = text[cursor:end_idx].strip()
        cursor = end_idx

        if not item_text:
            raise SegmentedExtractionError(
                f"Empty item block extracted at index {idx + 1}"
            )

        prompt = prompt_template.replace("{text}", item_text)
        system_prompt = (
            "You are a receipt item extraction system. "
            "Return only valid JSON."
        )

        logger.warning(
            "[SKELETON] Phase 3: Extracting item %d/%d (single-call mode)",
            idx + 1,
            total_items,
        )

        try:
            content = llm_client.chat(system_prompt, prompt)
            logger.debug(
                "[SKELETON] Phase 3: LLM response for item %d:\n%s",
                idx + 1,
                content,
            )
        except LLMError as e:
            raise SegmentedExtractionError(
                f"Item {idx + 1} extraction failed: {str(e)}"
            )

        try:
            item = json.loads(content)
        except json.JSONDecodeError as e:
            raise SegmentedExtractionError(
                f"Invalid JSON for item {idx + 1}: {str(e)}"
            )

        if not isinstance(item, dict):
            raise SegmentedExtractionError(
                f"Item {idx + 1} is not a JSON object"
            )

        REQUIRED_FIELDS = {
            "item",
            "quantidade",
            "valor_unitario",
            "valor_total",
            "desconto",
            "ean",
        }

        missing = REQUIRED_FIELDS - item.keys()
        if missing:
            raise SegmentedExtractionError(
                f"Item {idx + 1} missing required fields: {missing}"
            )

        all_items.append(item)

        logger.warning(
            "[SKELETON] Phase 3: Item %d extracted successfully",
            idx + 1,
        )

    logger.warning(
        "[SKELETON] Phase 3 completed: Extracted %d items (single-item strategy)",
        len(all_items),
    )

    return all_items


def extract_items_paginated_with_deterministic_skeleton(
    text: str, skeleton: dict, llm_client: LLMClient
) -> List[dict]:
    skeleton_items = skeleton.get("items", [])
    total_items = len(skeleton_items)

    if total_items == 0:
        logger.warning("[SKELETON] Phase 3: No items in skeleton, returning empty list")
        return []

    # --------------------------------------------------
    # NOVO: extração determinística dos textos dos itens
    # --------------------------------------------------

    # Normalização defensiva (encoding / OCR sujo)
    text = text.encode("utf-8", errors="replace").decode("utf-8")

    # Cada item corresponde a um COFINS (menos o footer já descartado no skeleton)
    cofins_matches = list(re.finditer(r"cofins", text, re.IGNORECASE))

    if len(cofins_matches) < total_items:
        raise SegmentedExtractionError(
            f"COFINS count ({len(cofins_matches)}) smaller than skeleton items ({total_items})"
        )

    item_texts = []
    cursor = 0

    for idx in range(total_items):
        match = cofins_matches[idx]
        end_idx = match.end()

        block_text = text[cursor:end_idx].strip()

        if not block_text:
            raise SegmentedExtractionError(
                f"Empty item block extracted at index {idx + 1}"
            )

        item_texts.append(block_text)
        cursor = end_idx

    # --------------------------------------------------
    # Paginação e extração via LLM (inalterado)
    # --------------------------------------------------

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

        # Cada item já está corretamente fatiado
        batch_input = build_delimited_batch_input(batch_item_texts)

        batch_items = extract_items_from_batch(
            batch_input, batch_size, llm_client
        )

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
