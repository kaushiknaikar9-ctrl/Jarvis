# JARVIS Cloud Run Dockerfile with Arete-19B support
# Uses Python 3.12 slim for better compatibility
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    PYTHONPATH=/app \
    MODEL_CACHE_DIR=/app/models \
    CLOUD_DEPLOYMENT=true

# Install system dependencies for audio and model loading
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    portaudio19-dev \
    libportaudio2 \
    libatlas3-base \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r jarvis && useradd -r -g jarvis jarvis

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/logs /app/tmp /app/models && chown -R jarvis:jarvis /app

# Switch to non-root user
USER jarvis

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/status || exit 1

# Run the application with gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "backend:app"]