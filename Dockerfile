FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && groupadd -g 10001 appgroup \
    && useradd -u 10001 -g appgroup -m appuser \
    && rm -rf /var/lib/apt/lists/*

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

RUN mkdir -p /var/log/swiftdeploy \
    && chown -R appuser:appgroup /app /var/log/swiftdeploy

USER 10001:10001

EXPOSE 3000

CMD ["gunicorn", "--bind", "0.0.0.0:3000", "--workers", "1", "--access-logfile", "-", "--error-logfile", "-", "main:app"]
