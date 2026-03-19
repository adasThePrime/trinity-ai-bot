FROM python:3.14-slim
WORKDIR /app

COPY . .
RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["sh", "-c", "ddgs api --host 127.0.0.1 --port 8000 & sleep 3 && python -m bot"]