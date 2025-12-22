import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"


def load_knowledge_for_issuer(issuer: str) -> str:
    """
    Load RAG knowledge content for a specific issuer.
    
    Returns the content of the knowledge file if the issuer is supported,
    otherwise returns an empty string.
    
    Currently supported issuers:
    - itau: loads fatura_itau.MD
    """
    if not issuer:
        return ""
    
    normalized_issuer = issuer.lower().strip()
    
    if normalized_issuer == "itau":
        return _load_knowledge_file("fatura_itau.MD")
    
    return ""


def _load_knowledge_file(filename: str) -> str:
    """
    Load a knowledge file from the knowledge directory.
    
    Returns the file content or empty string if file doesn't exist.
    """
    file_path = KNOWLEDGE_DIR / filename
    
    if not file_path.exists():
        return ""
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except (IOError, OSError):
        logger.exception("Failed to read knowledge file: %s", filename)
        return ""
