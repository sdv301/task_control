"""Извлечение текста из сканированного PDF через OCR."""
import pdfplumber
import io
import sys

pdf_path = r"КЧС 4.pdf"
out_path = r"extracted_text.txt"

# Сначала пробуем pdfplumber
with pdfplumber.open(pdf_path) as pdf:
    texts = []
    for i, page in enumerate(pdf.pages):
        t = page.extract_text(x_tolerance=2, y_tolerance=3)
        if t and len(t.strip()) > 20:
            texts.append(f"=== PAGE {i+1} ===\n{t}")
    
    if texts:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(texts))
        print(f"Готово (pdfplumber)! {len(texts)} страниц -> {out_path}")
        sys.exit(0)

print("pdfplumber не извлёк текст — PDF сканированный.")
print("Пробуем OCR (pytesseract)...")

try:
    import pytesseract
    from pdf2image import convert_from_path
    
    images = convert_from_path(pdf_path, dpi=200)
    print(f"Конвертировано {len(images)} страниц в изображения.")
    
    with open(out_path, "w", encoding="utf-8") as f:
        for i, img in enumerate(images):
            text = pytesseract.image_to_string(img, lang='rus+eng', config='--psm 6')
            f.write(f"=== PAGE {i+1} ===\n{text}\n\n")
            print(f"  Страница {i+1}: {len(text)} символов")
    
    print(f"Готово (OCR)! -> {out_path}")

except ImportError as e:
    print(f"Ошибка: {e}")
    print("Установите: pip install pytesseract pdf2image Pillow")
    print("Также нужен Tesseract OCR: https://github.com/tesseract-ocr/tesseract")
except Exception as e:
    print(f"Ошибка OCR: {e}")
