FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency definitions first for optimal layer caching
COPY requirements.txt pyproject.toml /app/

# Install dependencies including google-genai
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . /app/

# Install package in editable mode
RUN pip install --no-cache-dir -e .

# Expose default port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Default environment
ENV PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0

# Run OpenAPI REST server with Swagger UI and /openapi.json by default
CMD ["python", "-m", "moodle_mcp", "--mode", "openapi", "--host", "0.0.0.0", "--port", "8000"]
