# Dockerfile for Assembly Backend

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV APP_ENV=production
ENV APP_MODE=web

# Create a non-root user and group
RUN groupadd -r assembly && useradd -r -g assembly assembly

# Set the working directory
WORKDIR /app

# Install system dependencies (no Postgres: web is stateless, desktop uses SQLite)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt uvicorn

# Copy the application code
COPY . .

# Change ownership of the app directory to the non-root user
RUN chown -R assembly:assembly /app

# Switch to the non-root user
USER assembly

# Expose the port the app runs on
EXPOSE 8000

# Health check using the new /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start the application. Uvicorn will handle graceful shutdown signals (SIGINT/SIGTERM)
# and trigger the FastAPI lifespan shutdown events.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
