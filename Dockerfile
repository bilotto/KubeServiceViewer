FROM python:3.8-slim

RUN pip install --no-cache-dir flask kubernetes

WORKDIR /app

COPY . /app

ENV FLASK_APP=app.py

CMD ["python", "app.py"]
