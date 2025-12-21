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
3. **Queue**: The invoice is added to the processing queue
4. **Text Extraction**: The system extracts text from the PDF using pdfplumber
5. **AI Processing**: The selected LLM analyzes the text and extracts individual transactions
6. **Excel Generation**: Extracted transactions are formatted into an Excel spreadsheet
7. **Download**: The Excel file becomes available for download from the queue

## Processing Queue

The application includes a processing queue that allows you to upload multiple invoices and track their progress. The queue is displayed below the upload form.

### Real-Time Updates (Server-Sent Events)

Job status updates are delivered via Server-Sent Events (SSE), which means the UI updates in real time without polling or page reloads. When you upload a PDF, the job immediately appears in the queue and its status, progress, and actions update automatically as processing progresses.

Key benefits of SSE:
- No page reloads required - the file input is never cleared by background updates
- Instant status updates as jobs progress through each stage
- Multiple uploads can be tracked simultaneously
- Browser automatically reconnects if the connection drops

### Job Status

Each uploaded invoice can have one of the following statuses:

| Status | Description |
|--------|-------------|
| WAITING | Invoice is queued but processing has not started yet |
| PROCESSING | PDF text has been extracted and LLM is analyzing the content |
| COMPLETED | Excel file has been generated and is ready for download |
| ERROR | Processing failed - error message is displayed |
| CANCELLED | User manually stopped the processing |

### Progress Stages

Progress is tracked in coarse stages:
- 0% - Uploaded and queued
- 20% - PDF text extracted
- 50% - Waiting for LLM response
- 80% - Parsing and validating LLM response
- 100% - Excel file ready

### Offline vs Online Processing

**Offline (Ollama)**: Processing happens locally on your machine. This is slower (especially for the first request) but keeps all data private. Typical processing time: 30-120 seconds depending on document size and hardware.

**Online (OpenAI)**: Processing uses OpenAI's cloud API. This is faster but sends document text to external servers. Typical processing time: 5-15 seconds.

### Cancellation

You can cancel any job that is in WAITING or PROCESSING status by clicking the Cancel button. Cancelled jobs cannot be resumed - you will need to upload the file again.

## Usage

### Via Web Interface

1. Open your browser and navigate to http://localhost:8000
2. Select the LLM provider (Offline or Online)
3. Select a PDF credit card invoice using the file input
4. Click "Upload & Process"
5. Monitor progress in the Processing Queue table
6. Click "Download" when the job is completed

### Via API (curl)

Upload a PDF (returns immediately, processes in background):

```bash
curl -X POST "http://localhost:8000/upload" \
  -F "file=@/path/to/your/invoice.pdf" \
  -F "provider=offline"
```

List all jobs:

```bash
curl "http://localhost:8000/jobs"
```

Download completed Excel file:

```bash
curl "http://localhost:8000/jobs/{job_id}/download" --output transactions.xlsx
```

Cancel a job:

```bash
curl -X POST "http://localhost:8000/jobs/{job_id}/cancel"
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
