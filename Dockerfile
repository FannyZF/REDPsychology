FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg unzip curl \
    fonts-noto-cjk \
    ffmpeg \
    ca-certificates \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | \
    gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] \
    http://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/output/videos \
    /app/output/screenshots \
    /app/output/subtitles \
    /app/output/text \
    /app/data \
    /app/logs \
    /app/data/chrome_profile \
    /app/assets/templates

EXPOSE 8998

ENV TZ=Asia/Shanghai

CMD ["python", "-m", "src.main", "web"]
