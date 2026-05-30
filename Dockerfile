FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && pip install --no-cache-dir requests \
    && rm -rf /var/lib/apt/lists/*

COPY src/ /app/src/

CMD ["python", "-u", "src/strategy_one.py"]1~FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && pip install --no-cache-dir requests \
    && rm -rf /var/lib/apt/lists/*

COPY src/ /app/src/

CMD ["python", "-u", "src/strategy_one.py"]1~FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && pip install --no-cache-dir requests \
    && rm -rf /var/lib/apt/lists/*

COPY src/ /app/src/

CMD ["python", "-u", "src/strategy_one.py"]
