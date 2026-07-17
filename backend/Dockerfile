FROM python:3.12-slim

WORKDIR /app

# tesseract-ocr — бинарник, который использует pytesseract (см.
# requirements.txt); tesseract-ocr-rus — казахстанские счета обычно на
# русском, без языкового пакета OCR не распознает кириллические ключевые
# слова ("сумма", "потребление"), только цифры.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
