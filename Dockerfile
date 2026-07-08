FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variables for Playwright to store browsers in a known location
ENV PLAYWRIGHT_BROWSERS_PATH=/app/playwright-browsers

# Install Playwright Chromium browser and all its required system dependencies
RUN playwright install chromium && playwright install-deps chromium

# Copy the rest of the application files
COPY . .

# Expose port (Railway injects $PORT at runtime)
EXPOSE 8080

# Run the application (python reads PORT env var internally)
CMD ["python", "main.py"]
