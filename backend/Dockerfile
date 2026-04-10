FROM python:3.12-slim

WORKDIR /app

# System deps for numpy, scipy, matplotlib
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gfortran libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY backend/ backend/
COPY src/ src/
COPY datasets/ datasets/
COPY EDA_RULES.txt ./

# Create sessions dir
RUN mkdir -p sessions

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
