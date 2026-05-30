FROM python:3.12-slim

RUN pip install --no-cache-dir python-socks
COPY probe.py /probe.py
ENTRYPOINT ["python", "/probe.py"]
