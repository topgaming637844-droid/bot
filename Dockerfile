FROM python:3.11-slim

# Install system dependencies for Playwright and FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    ffmpeg \
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
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variables for Playwright to store browsers in a known location
ENV PLAYWRIGHT_BROWSERS_PATH=/app/playwright-browsers

# Install Playwright Chromium browser binaries during the build phase
RUN playwright install chromium

# Copy the rest of the application files
COPY . .

# Expose port
EXPOSE 8080

# Run the application
CMD ["python", "main.py"]
