FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    curl \
    && pip install --no-cache-dir -r requirements.txt \
    && curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-26.1.4.tgz -o /tmp/docker.tgz \
    && tar -xzf /tmp/docker.tgz -C /tmp \
    && mv /tmp/docker/docker /usr/bin/docker \
    && rm -rf /tmp/docker /tmp/docker.tgz \
    && rm -rf /var/lib/apt/lists/*

COPY src/ /app/src/
COPY config/ /app/config/

#CMD ["python", "-u", "src/main.py"]
# Start both scripts simultaneously
CMD python -u src/main.py & python -u src/dashboard.py & wait