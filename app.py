"""InvoiceSnap AI - local receipt scanner: Tesseract OCR + Gemma (Ollama) + Flask."""
import json, os, re
from datetime import datetime

import pytesseract
import requests
from flask import Flask, jsonify, render_template, request
from PIL import Image, ImageOps, UnidentifiedImageError

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")
CATEGORIES = ["Food & Dining", "Groceries", "Transport", "Shopping", "Utilities",
              "Health", "Entertainment", "Travel", "Office", "Other"]
ALLOWED = {"png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB
if os.getenv("TESSERACT_CMD"):
    pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]


class ScanError(Exception):
    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.status = status


def run_ocr(file):
    try:
        img = Image.open(file.stream)
        img.load()
    except (UnidentifiedImageError, OSError):
        raise ScanError("That file is not a readable image.")
    img = ImageOps.exif_transpose(img).convert("L")
    img = ImageOps.autocontrast(img)
    if max(img.size) < 1200:  # upscale small images for better OCR
        img = img.resize((img.width * 2, img.height * 2))
    try:
        text = pytesseract.image_to_string(img, config="--psm 6")
    except pytesseract.TesseractNotFoundError:
        raise ScanError("Tesseract is not installed or not on PATH. See README.", 500)
    if len(text.strip()) < 10:
        raise ScanError("No readable text found. Try a sharper, well-lit photo.", 422)
    return text


PROMPT = """You extract data from receipt OCR text. Reply with JSON only:
{{"merchant": string, "date": "YYYY-MM-DD" or "", "total": number, "category": one of {cats}}}
"total" is the final amount paid (including tax), as a plain number. Use "" or 0 if unknown.

OCR text:
{text}"""


def llm_extract(text):
    r = requests.post(f"{OLLAMA_URL}/api/generate", timeout=180, json={
        "model": MODEL, "stream": False, "format": "json",
        "options": {"temperature": 0},
        "prompt": PROMPT.format(cats=CATEGORIES, text=text[:4000])})
    r.raise_for_status()
    return json.loads(r.json()["response"])


AMOUNT = re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{3})*|\d+)\.\d{2}(?!\d)")
DATE = re.compile(r"\b(\d{1,4})[/\-.](\d{1,2})[/\-.](\d{2,4})\b")
KEYWORDS = {
    "Food & Dining": ["restaurant", "cafe", "coffee", "pizza", "burger", "bar", "kitchen", "bakery"],
    "Groceries": ["mart", "grocery", "supermarket", "fresh", "market", "dmart"],
    "Transport": ["uber", "ola", "fuel", "petrol", "taxi", "metro", "parking"],
    "Health": ["pharmacy", "medical", "clinic", "hospital", "chemist"],
    "Utilities": ["electric", "water", "broadband", "mobile", "recharge"],
    "Travel": ["hotel", "airlines", "flight", "railway", "irctc"],
    "Office": ["stationery", "office", "print"],
}


def heuristic_extract(text):
    """Regex fallback used when Ollama is unavailable."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    merchant = next((l for l in lines if re.search(r"[A-Za-z]{3}", l)), "")
    amounts = [(float(m.group(0).replace(",", "")), l) for l in lines for m in AMOUNT.finditer(l)]
    tot = [a for a, l in amounts if "total" in l.lower() and "sub" not in l.lower()]
    total = max(tot) if tot else (max((a for a, _ in amounts), default=0))
    date = ""
    m = DATE.search(text)
    if m:
        date = f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    low = text.lower()
    cat = next((c for c, ks in KEYWORDS.items() if any(k in low for k in ks)), "Other")
    return {"merchant": merchant, "date": date, "total": total, "category": cat}


def normalize_date(s):
    s = str(s or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return ""


def normalize(d):
    try:
        total = round(float(str(d.get("total", 0)).replace(",", "").replace("$", "").replace("₹", "")), 2)
    except ValueError:
        total = 0.0
    cat = d.get("category")
    return {"merchant": str(d.get("merchant") or "").strip()[:80],
            "date": normalize_date(d.get("date")), "total": total,
            "category": cat if cat in CATEGORIES else "Other"}


@app.get("/")
def index():
    return render_template("index.html", categories=CATEGORIES)


@app.get("/api/health")
def health():
    status = {"tesseract": False, "ollama": False, "model": MODEL}
    try:
        pytesseract.get_tesseract_version()
        status["tesseract"] = True
    except Exception:
        pass
    try:
        tags = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2).json()
        names = [m["name"] for m in tags.get("models", [])]
        status["ollama"] = any(n == MODEL or n.startswith(MODEL + ":") for n in names)
    except Exception:
        pass
    return jsonify(status)


@app.post("/api/scan")
def scan():
    try:
        f = request.files.get("receipt")
        if not f or not f.filename:
            raise ScanError("No file uploaded.")
        if f.filename.rsplit(".", 1)[-1].lower() not in ALLOWED:
            raise ScanError("Unsupported file type. Use PNG, JPG, WEBP, BMP or TIFF.")
        text = run_ocr(f)
        source, warning = "gemma", None
        try:
            data = llm_extract(text)
        except Exception:
            data, source = heuristic_extract(text), "fallback"
            warning = f"Gemma ({MODEL}) was unavailable, so basic rules were used. Check the fields."
        return jsonify({"expense": normalize(data), "source": source, "warning": warning})
    except ScanError as e:
        return jsonify({"error": str(e)}), e.status
    except Exception as e:  # last-resort guard
        app.logger.exception("scan failed")
        return jsonify({"error": "Unexpected error while scanning."}), 500


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "File too large (max 10 MB)."}), 413


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", 5000)), debug=False)
