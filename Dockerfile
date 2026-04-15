# ─────────────────────────────────────────────────────────────────────────────
# ANSI X12 Medical Billing Converter — Docker Image
#
# Build:   docker build -t ansi-x12-billing .
# Run:     docker run -p 8501:8501 -v billing_data:/app/data ansi-x12-billing
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# Metadata
LABEL maintainer="IRCM Development Team"
LABEL description="ANSI X12 Medical Billing Converter"
LABEL version="2.0.0"

# Non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# ── System dependencies ────────────────────────────────────────────────────────
# lxml requires libxml2 and libxslt; reportlab requires freetype
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2 \
        libxslt1.1 \
        libfreetype6 \
        libffi-dev \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ────────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir cryptography  # HIPAA mode encryption support

# ── Application code ───────────────────────────────────────────────────────────
COPY . .

# ── Data volume ────────────────────────────────────────────────────────────────
# Mount a persistent volume here to keep the database and CMS cache across restarts
RUN mkdir -p /app/data && chown -R appuser:appuser /app/data
VOLUME ["/app/data"]

# ── Environment ────────────────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Override default paths to use the mounted volume
ENV TEMP_DIR=/app/data/tmp
ENV CACHE_DIR=/app/data/cms_cache
ENV DB_PATH=/app/data/billing.db
ENV AUDIT_LOG_PATH=/app/data/audit.jsonl

# ── Streamlit config ────────────────────────────────────────────────────────────
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Switch to non-root user
USER appuser

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8501/_stcore/health').raise_for_status()" || exit 1

CMD ["python", "-m", "streamlit", "run", "app/main.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.maxUploadSize=200"]
