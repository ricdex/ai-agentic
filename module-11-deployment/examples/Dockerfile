FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias primero (para aprovechar cache de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código del agente
COPY agent/ ./agent/

# Usuario no-root
RUN useradd -m -u 1001 agentuser && chown -R agentuser:agentuser /app
USER agentuser

# Health check — el worker expone un endpoint HTTP mínimo
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8081/health')" || exit 1

# Variables de entorno esperadas (inyectadas por ECS/Cloud Run desde Secrets Manager)
ENV ANTHROPIC_API_KEY=""
ENV REDIS_URL=""
ENV GITHUB_TOKEN=""
ENV TEST_RUNNER_URL=""
ENV LOG_LEVEL="INFO"

CMD ["python", "-m", "agent.worker"]
