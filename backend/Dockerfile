FROM python:3.12-slim

WORKDIR /app

# tesseract-ocr — бинарник, который использует pytesseract (см.
# requirements.txt); tesseract-ocr-rus — казахстанские счета обычно на
# русском, без языкового пакета OCR не распознает кириллические ключевые
# слова ("сумма", "потребление"), только цифры.
# build-essential — компилятор C++ для CmdStan (нужен Prophet, см. ниже).
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-rus \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Prophet считает через CmdStan (C++), который cmdstanpy компилирует при
# первом использовании. Делаем это на этапе сборки образа, а не при первом
# запросе к /forecast — иначе первый прогноз в демо висел бы минуты и мог
# упасть без компилятора. Кешируется в слое образа.
RUN python -c "import cmdstanpy; cmdstanpy.install_cmdstan()"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
