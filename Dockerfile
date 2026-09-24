FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir -U pyrogram==2.0.106 tgcrypto uvloop
COPY sparta_bot.py .
ENV PYTHONUNBUFFERED=1
CMD ["python", "-u", "sparta_bot.py"]
