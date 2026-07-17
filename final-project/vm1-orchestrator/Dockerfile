FROM python:3.11-slim

WORKDIR /app

COPY shared/ ./shared/
COPY vm1-orchestrator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY vm1-orchestrator/ .

RUN useradd -m -u 1001 factory
USER factory

EXPOSE 8000
HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
