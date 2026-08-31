# Agent Memory Server — production container
#
# IMPORTANT: the default `pip install torch` pulls ~2.5GB of NVIDIA CUDA
# libraries that are useless on a CPU server. We install the CPU-only build
# instead, which takes the image from ~3GB to well under 1GB and makes deploys
# minutes faster. That single index-url is the difference between a $5 box
# working and not.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.hfcache

WORKDIR /app

# CPU-only torch first, then everything else.
COPY requirements.txt .
RUN pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple \
        -r requirements.txt

COPY . .

# Bake the embedding model into the image so the first request isn't slow and
# the container doesn't depend on HuggingFace being reachable at runtime.
# (Skip by setting EMBEDDINGS_PROVIDER=openai and removing this line.)
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('all-MiniLM-L6-v2')" || \
    echo "model prefetch skipped (will download at first run)"

# Memories and ledger live here — mount a VOLUME so they survive redeploys.
# Without this, every deploy wipes your customers' data and your revenue history.
RUN mkdir -p /app/data
VOLUME ["/app/data"]

# Listen on all interfaces so the host can route to us.
ENV HOST=0.0.0.0 \
    PORT=8402
EXPOSE 8402

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD python -c "import urllib.request,os; \
        urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\",\"8402\")}/health')" || exit 1

CMD ["python", "serve.py"]
