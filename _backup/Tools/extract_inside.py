"""Извлечение текста из PDF внутри Docker-контейнера."""
import pdfplumber
import io
import sys

pdf_path = sys.argv[1] if len(sys.argv) > 1 else "/app/uploaded.pdf"
out_path = "/data/extracted_text.txt"

# 1. Пробуем pdfplumber
with pdfplumber.open(pdf_path) as pdf:
    texts = []
    for i, page in enumerate(pdf.pages):
        t = page.extract_text(x_tolerance=2, y_tolerance=3)
        if t and len(t.strip()) > 20:
            texts.append(f"=== PAGE {i+1} ===\n{t}")
    if texts:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(texts))
        print(f"OK pdfplumber: {len(texts)} pages")
        sys.exit(0)

# 2. OCR
print("pdfplumber empty, trying OCR...")
import pytesseract
from pdf2image import convert_from_bytes

with open(pdf_path, "rb") as f:
    data = f.read()

images = convert_from_bytes(data, dpi=200)
with open(out_path, "w", encoding="utf-8") as f:
    for i, img in enumerate(images):
        text = pytesseract.image_to_string(img, lang='rus+eng', config='--psm 6')
        f.write(f"=== PAGE {i+1} ===\n{text}\n\n")
        print(f"  Page {i+1}: {len(text)} chars")

print(f"OK OCR: {len(images)} pages -> {out_path}")
