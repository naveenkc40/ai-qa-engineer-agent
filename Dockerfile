FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./

RUN python -m pip install --no-cache-dir \
    -r requirements.txt \
    -r requirements-dev.txt

COPY . .

CMD ["python", "app.py"]
