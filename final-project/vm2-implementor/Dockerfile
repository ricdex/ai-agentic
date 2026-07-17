FROM python:3.11-slim

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY shared/ ./shared/
COPY vm2-implementor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY vm2-implementor/ .

RUN useradd -m -u 1001 factory
USER factory

CMD ["python", "main.py"]
