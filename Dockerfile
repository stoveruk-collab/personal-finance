FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml setup.py ./
COPY src ./src
COPY config ./config

RUN pip install --no-cache-dir -e .

ENV HOST=0.0.0.0
ENV PORT=8080

CMD ["sh", "-c", "python -m uvicorn personal_finance.web.app:app --host ${HOST:-0.0.0.0} --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips '*'"]
