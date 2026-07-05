FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends python3-pip libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev libxcb1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PIP_BREAK_SYSTEM_PACKAGES=1
COPY requirements-prod.txt /tmp/requirements-prod.txt
RUN pip3 install --no-cache-dir --no-compile -r /tmp/requirements-prod.txt && \
    pip3 uninstall -y opencv-python opencv-contrib-python && \
    pip3 install --no-cache-dir --no-compile opencv-python-headless && \
    rm /tmp/requirements-prod.txt && \
    find /usr/local/lib/python3*/dist-packages -name '__pycache__' -exec rm -rf {} + 2>/dev/null; \
    find /usr/local/lib/python3*/dist-packages -name '*.pyc' -delete 2>/dev/null; \
    true

COPY . /app/ai-ml/

ENV AI_PORT=5001
EXPOSE 5001

CMD ["python3", "ai-ml/api_server.py"]
