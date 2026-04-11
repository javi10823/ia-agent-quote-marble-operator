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

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run entrypoint as root to fix volume permissions, then start app as appuser
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["su", "-s", "/bin/sh", "appuser", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 3"]
