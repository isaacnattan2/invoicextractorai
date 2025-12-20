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
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables (only required for Online mode):
   ```bash
   export OPENAI_API_KEY="your-openai-api-key"
   ```

## LLM Provider Options

The application supports two LLM providers for transaction extraction:

### Offline Mode (Default - Recommended for Privacy)

Uses Ollama running locally on your machine. No data leaves your computer.

**Requirements:**
1. Install Ollama from https://ollama.ai
2. Pull the required model:
   ```bash
   ollama pull llama3.1:8b
   ```
3. Ensure Ollama is running at http://localhost:11434

**Privacy:** When using Offline mode, all document text is processed locally. No external API calls are made.

### Online Mode (OpenAI)

Uses OpenAI's gpt-4o-mini model via API.

**Requirements:**
- Set the `OPENAI_API_KEY` environment variable

**Note:** Document text is sent to OpenAI's servers for processing.

## Running the Application

Start the development server:

```bash
uvicorn app.main:app --reload
```

The application will be available at http://localhost:8000

## End-to-End Flow

The application processes PDF invoices through the following pipeline:

1. **PDF Upload**: User uploads a PDF credit card invoice through the web interface
2. **Provider Selection**: User selects Offline (Ollama) or Online (OpenAI) LLM provider
3. **Text Extraction**: The system extracts text from the PDF using pdfplumber
4. **AI Processing**: The selected LLM analyzes the text and extracts individual transactions
5. **Excel Generation**: Extracted transactions are formatted into an Excel spreadsheet
6. **Download**: The Excel file is automatically downloaded to the user's device

## Usage

### Via Web Interface

1. Open your browser and navigate to http://localhost:8000
2. Select the LLM provider (Offline or Online)
3. Select a PDF credit card invoice using the file input
4. Click "Extract & Download Excel"
5. The Excel file with extracted transactions will be downloaded automatically

### Via API (curl)

Upload a PDF using offline mode (default):

```bash
curl -X POST "http://localhost:8000/upload" \
  -F "file=@/path/to/your/invoice.pdf" \
  -F "provider=offline" \
  --output transactions.xlsx
```

Upload a PDF using online mode (OpenAI):

```bash
curl -X POST "http://localhost:8000/upload" \
  -F "file=@/path/to/your/invoice.pdf" \
  -F "provider=online" \
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
| Bank | Identified bank/card issuer |

## Error Handling

- **400 Bad Request**: Invalid file type (non-PDF) or PDF with no extractable text
- **500 Internal Server Error**: LLM API errors or processing failures

## Requirements

- Python 3.11
- Text-based PDF invoices (scanned/image PDFs are not supported)
- For Offline mode: Ollama with llama3.1:8b model
- For Online mode: OpenAI API key
