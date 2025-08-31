# syntax=docker/dockerfile:1
FROM python:3.10-slim

# Install system deps (Graphviz CLI for graphviz/pydot; remove dev headers unless using pygraphviz)
RUN apt-get update && apt-get install -y --no-install-recommends \
    graphviz \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN useradd -m appuser

# Install Python deps
COPY venv_requirements.txt ./requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY . .

# ensure a writable uploads directory
RUN mkdir -p /app/uploads \
    && chown -R appuser:appuser /app


# Runtime config
ENV PYTHONUNBUFFERED=1
EXPOSE 10000

# Healthcheck (adjust /health if your route is different)
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv('PORT','10000')}/health').read()" || exit 1

USER appuser

# Start Flask app with Gunicorn
CMD exec gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120
