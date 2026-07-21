FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir flask werkzeug gunicorn
COPY . .
EXPOSE 5000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
