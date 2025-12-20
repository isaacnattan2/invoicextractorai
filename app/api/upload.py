from io import BytesIO

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.services.excel_generator import generate_excel
from app.services.expense_extractor import ExtractionError, extract_expenses
from app.services.pdf_extractor import PDFExtractionError, extract_text_from_pdf

router = APIRouter()


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only PDF files are accepted."
        )

    contents = await file.read()
    file_stream = BytesIO(contents)

    try:
        extracted_pdf = extract_text_from_pdf(file_stream)
    except PDFExtractionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        extraction_result = extract_expenses(extracted_pdf)
    except ExtractionError as e:
        raise HTTPException(status_code=500, detail=str(e))

    excel_file = generate_excel(extraction_result.transactions)

    filename = "invoice_transactions.xlsx"
    if file.filename:
        base_name = file.filename.rsplit(".", 1)[0]
        filename = f"{base_name}_transactions.xlsx"

    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )
