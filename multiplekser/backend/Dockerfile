FROM python:3.12-slim

WORKDIR /app

# libglib2.0-0 - wymagane przez opencv-python-headless (deskew, ocr/image.py, 2026-09-14) na
# tym minimalnym obrazie bazowym - bez niego "import cv2" konczy sie ImportError
# (libgthread-2.0.so.0 not found), mimo ze wariant "headless" nie potrzebuje samego libGL.
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
