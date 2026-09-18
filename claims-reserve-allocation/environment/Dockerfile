FROM python:3.13-slim-bookworm

RUN pip install --no-cache-dir numpy==2.4.6 scipy==1.17.1

WORKDIR /app
COPY . /app

RUN mkdir -p /app/outputs
