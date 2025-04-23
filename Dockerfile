FROM python:3.11-slim

# Install Tesseract and system dependencies
RUN apt-get update && \
    apt-get install -y tesseract-ocr libglib2.0-0 libsm6 libxext6 libxrender-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy all files into the container
COPY . .

# Install Python packages
RUN pip install --upgrade pip && pip install -r requirements.txt

# Run the bot
CMD ["python", "bot.py"]
