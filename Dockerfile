
ARG DOCKER_REG
FROM ${DOCKER_REG:-}python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONIOENCODING=utf-8

WORKDIR /home/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirror-pypi.runflare.com/simple --upgrade pip \
    && pip install --no-cache-dir -i https://mirror-pypi.runflare.com/simple -r requirements.txt

COPY ./app/ /home/app/
COPY ./docker-entrypoint.sh /tmp/docker-entrypoint.sh

RUN chmod +x /tmp/docker-entrypoint.sh

ENTRYPOINT ["bash", "/tmp/docker-entrypoint.sh"]