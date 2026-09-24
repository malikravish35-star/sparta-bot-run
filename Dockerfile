FROM python:3.11-slim
WORKDIR /app
# kurigram = maintained pyrogram fork (naya MTProto layer).
# purani pyrogram naye media ko "MessageMediaUnsupported" bana deti thi.
RUN pip install --no-cache-dir -U kurigram==2.2.26 tgcrypto uvloop
COPY sparta_bot.py .
ENV PYTHONUNBUFFERED=1
CMD ["python", "-u", "sparta_bot.py"]
