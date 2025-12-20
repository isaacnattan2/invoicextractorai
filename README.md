# Invoice Extractor AI

A FastAPI-based application for extracting data from PDF invoices.

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

## Running the Application

Start the development server:

```bash
uvicorn app.main:app --reload
```

The application will be available at http://localhost:8000

## Usage

1. Open your browser and navigate to http://localhost:8000
2. Select a PDF file using the file input
3. Click the Upload button to submit the file

## Manual Testing

### Test PDF Upload via curl

Test with a text-based PDF:

```bash
curl -X POST "http://localhost:8000/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/path/to/your/invoice.pdf"
```

Expected successful response:

```json
{
  "message": "PDF processed successfully",
  "filename": "invoice.pdf",
  "num_pages": 1,
  "total_characters": 1234
}
```

### Test Error Cases

Test with non-PDF file (should return 400):

```bash
curl -X POST "http://localhost:8000/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/path/to/image.png"
```

Test with image-based PDF (should return 400 with message about no extractable text)
