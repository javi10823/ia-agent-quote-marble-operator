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

# Create output directory
RUN mkdir -p output

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
