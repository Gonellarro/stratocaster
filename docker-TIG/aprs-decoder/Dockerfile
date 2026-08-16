FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY aprs_decoder.py .
COPY test_aprs_decoder.py .

CMD ["python", "-u", "aprs_decoder.py"]
