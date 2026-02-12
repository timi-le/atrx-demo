FROM python:3.11-slim-buster

# System Setup
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off

WORKDIR /app

# Install System Deps (needed for git and numpy)
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Dependencies using PIP (Simpler/Faster)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy Source Code
COPY . .

# Run the Bot
CMD ["python", "src/main.py"]