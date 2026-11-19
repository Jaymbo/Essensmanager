FROM python:3.12-slim

WORKDIR /srv
ENV PYTHONUNBUFFERED=1 EM_DB_PATH=/data/app.db

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN mkdir -p /data
VOLUME /data
EXPOSE 8010

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
