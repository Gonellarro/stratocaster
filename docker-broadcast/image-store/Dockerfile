FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir flask werkzeug gunicorn paho-mqtt
COPY . .
EXPOSE 5000
CMD ["gunicorn", "-w", "1", "--threads", "4", "-b", "0.0.0.0:5000", "app:app"]
