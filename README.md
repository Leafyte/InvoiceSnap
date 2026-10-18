# InvoiceSnap AI

Scan receipt photos into expenses, review them, and export a CSV. **100% local**: Tesseract reads the image, Gemma (via Ollama) structures the text. No cloud, no paid APIs.

**Stack:** HTML/CSS/JS · Python Flask · Tesseract OCR · Gemma via Ollama

## How it works
1. Upload one or more receipt images.
2. Tesseract extracts the raw text.
3. Gemma returns merchant, date, total and category as JSON.
4. Edit any field in the table, then **Export CSV**.

If Ollama is not running, the app falls back to simple regex rules and flags those rows (amber edge) for review.

## Setup

### 1. Install Tesseract
- **Windows:** install from https://github.com/UB-Mannheim/tesseract/wiki, then set `TESSERACT_CMD="C:\Program Files\Tesseract-OCR\tesseract.exe"` if it isn't on PATH.
- **macOS:** `brew install tesseract`
- **Ubuntu/Debian:** `sudo apt install tesseract-ocr`

### 2. Install Ollama and pull Gemma
Install from https://ollama.com, then:
```bash
ollama pull gemma3:4b
```
(Low on RAM? Use `gemma3:1b`. Then run with `OLLAMA_MODEL=gemma3:1b`.)

### 3. Run the app
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000. The badges at the top show whether Tesseract and Gemma are detected.

## Configuration (environment variables)
| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_MODEL` | `gemma3:4b` | Model used for extraction |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server |
| `TESSERACT_CMD` | (PATH) | Path to the tesseract binary |
| `PORT` | `5000` | Web server port |

## Tips and troubleshooting
- The first scan is slow while Gemma loads into memory; later scans are faster.
- Use sharp, flat, well-lit photos for the best OCR.
- **"Tesseract is not installed"**: install it and/or set `TESSERACT_CMD`.
- **Gemma badge says "not found"**: run `ollama serve` and check `ollama list`.
- Expenses are kept in your browser's localStorage; images are never stored.
- CSV cells starting with `= + - @` are escaped to prevent spreadsheet formula injection.

## Project layout
```
app.py              
Flask backend (OCR, Gemma call, fallback, validation)
templates/index.html
static/style.css, static/app.js
requirements.txt
```
