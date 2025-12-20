from io import BytesIO

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas.pdf import UploadResponse
from app.services.pdf_extractor import PDFExtractionError, extract_text_from_pdf

router = APIRouter()


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only PDF files are accepted."
        )

    contents = await file.read()
    file_stream = BytesIO(contents)

    try:
        extracted = extract_text_from_pdf(file_stream)
    except PDFExtractionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    total_characters = sum(len(page.text) for page in extracted.pages)

    return UploadResponse(
        message="PDF processed successfully",
        filename=file.filename,
        num_pages=len(extracted.pages),
        total_characters=total_characters
    )
