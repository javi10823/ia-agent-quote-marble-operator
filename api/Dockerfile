FROM python:3.12-slim

# System dependencies for pdf2image and Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libffi-dev \
    libjpeg-dev \
    libpng-dev \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root user
RUN useradd -r -s /bin/false appuser \
    && mkdir -p /app/output /tmp/plans \
    && chown -R appuser:appuser /app /tmp/plans
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
