FROM python:3.11-slim-bookworm

# 1. Environment configuration
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# 2. Install Chromium dependencies
# These are essential for running 'nodriver' or 'playwright' in Linux
RUN apt-get update --fix-missing && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    ca-certificates \
    procps \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 3. Working Directory
WORKDIR /app

# 4. Dependency Layering
# Copying requirements first optimizes the Docker build cache
COPY requirements.txt .
RUN pip install -r requirements.txt

# 5. Application Code
COPY . .

# 6. Port and Runtime
# Render uses the $PORT env, but we expose 3000 as a standard
EXPOSE 3000

# Using sh to ensure environment variables like $PORT are expanded
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-3000}"]
