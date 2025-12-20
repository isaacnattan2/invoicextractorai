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
