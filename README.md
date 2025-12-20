# Invoice Extractor AI

A FastAPI-based application for extracting credit card transactions from PDF invoices using AI-powered semantic extraction and exporting them to Excel.

## Python Version

Python 3.11

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/isaacnattan2/invoicextractorai.git
   cd invoicextractorai
   ```

2. Create a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   windows venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   ```bash
   export OPENAI_API_KEY="your-openai-api-key"
   windows setx OPENAI_API_KEY "your-openai-api-key"
   setx OPENAI_API_KEY "sua_api_key_aqui"
   check echo $env:OPENAI_API_KEY
   ```

## Running the Application

Start the development server:

```bash
uvicorn app.main:app --reload
```

The application will be available at http://localhost:8000

## End-to-End Flow

The application processes PDF invoices through the following pipeline:

1. **PDF Upload**: User uploads a PDF credit card invoice through the web interface
2. **Text Extraction**: The system extracts text from the PDF using pdfplumber
3. **AI Processing**: OpenAI's gpt-4o-mini model analyzes the text and extracts individual transactions
4. **Excel Generation**: Extracted transactions are formatted into an Excel spreadsheet
5. **Download**: The Excel file is automatically downloaded to the user's device

## Usage

### Via Web Interface

1. Open your browser and navigate to http://localhost:8000
2. Select a PDF credit card invoice using the file input
3. Click "Extract & Download Excel"
4. The Excel file with extracted transactions will be downloaded automatically

### Via API (curl)

Upload a PDF and receive an Excel file:

```bash
curl -X POST "http://localhost:8000/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/path/to/your/invoice.pdf" \
  --output transactions.xlsx
```

## Excel Output Format

The generated Excel file contains a "Transactions" sheet with the following columns:

| Column | Description |
|--------|-------------|
| Date | Transaction date (YYYY-MM-DD) |
| Description | Merchant or purchase description |
| Amount | Transaction amount in BRL |
| Installment | Installment info (e.g., "2/6") or empty |
| Currency | Currency code (BRL) |
| Page | PDF page where transaction was found |
| Confidence | AI confidence score (0.0 to 1.0) |

## Error Handling

- **400 Bad Request**: Invalid file type (non-PDF) or PDF with no extractable text
- **500 Internal Server Error**: OpenAI API errors or processing failures

## Requirements

- Python 3.11
- OpenAI API key with access to gpt-4o-mini model
- Text-based PDF invoices (scanned/image PDFs are not supported)
