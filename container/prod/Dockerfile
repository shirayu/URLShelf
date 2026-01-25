# syntax=docker/dockerfile:1

FROM python:3.13-slim

WORKDIR /app

# Copy dependency metadata first for better layer caching
COPY pyproject.toml uv.lock ./

# Create venv and install runtime deps (no dev)
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -U pip uv \
    && /opt/venv/bin/uv export --format requirements-txt --no-dev --output-file /tmp/requirements.txt \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

# Copy app sources
COPY app.py ./app.py
COPY templates ./templates
COPY assets ./assets

# Create data dir and non-root user
RUN useradd -ms /bin/bash appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

USER appuser

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 9432

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:9432", "app:app"]
