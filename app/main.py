import os
import random
import time
from datetime import datetime, timezone

from flask import Flask, Response, g, jsonify, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)


app = Flask(__name__)

START_TIME = time.monotonic()

MODE = os.getenv("MODE", "stable").lower()
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
APP_PORT = int(os.getenv("APP_PORT", "3000"))

CHAOS_STATE = {
    "mode": "off",
    "duration": 0,
    "error_rate": 0.0,
}


HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)

APP_UPTIME_SECONDS = Gauge(
    "app_uptime_seconds",
    "Application uptime in seconds",
)

APP_MODE = Gauge(
    "app_mode",
    "Application mode: 0=stable, 1=canary",
)

CHAOS_ACTIVE = Gauge(
    "chaos_active",
    "Chaos state: 0=none, 1=slow, 2=error",
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def update_runtime_metrics():
    APP_UPTIME_SECONDS.set(round(time.monotonic() - START_TIME, 2))
    APP_MODE.set(1 if MODE == "canary" else 0)

    if CHAOS_STATE["mode"] == "slow":
        CHAOS_ACTIVE.set(1)
    elif CHAOS_STATE["mode"] == "error":
        CHAOS_ACTIVE.set(2)
    else:
        CHAOS_ACTIVE.set(0)


@app.before_request
def before_request():
    g.request_started_at = time.monotonic()

    if request.path == "/metrics":
        return None

    if MODE != "canary":
        return None

    if request.path == "/chaos":
        return None

    if CHAOS_STATE["mode"] == "slow":
        time.sleep(float(CHAOS_STATE["duration"]))

    if CHAOS_STATE["mode"] == "error":
        if random.random() < float(CHAOS_STATE["error_rate"]):
            return jsonify({
                "error": "chaos error injected",
                "mode": MODE,
                "version": APP_VERSION,
                "timestamp": utc_now(),
            }), 500

    return None


@app.after_request
def after_request(response):
    if MODE == "canary":
        response.headers["X-Mode"] = "canary"

    path = request.path
    method = request.method
    status_code = str(response.status_code)

    duration = time.monotonic() - getattr(
        g,
        "request_started_at",
        time.monotonic(),
    )

    HTTP_REQUESTS_TOTAL.labels(
        method=method,
        path=path,
        status_code=status_code,
    ).inc()

    HTTP_REQUEST_DURATION_SECONDS.labels(
        method=method,
        path=path,
    ).observe(duration)

    update_runtime_metrics()

    return response


@app.get("/")
def index():
    return jsonify({
        "message": "Welcome to SwiftDeploy",
        "mode": MODE,
        "version": APP_VERSION,
        "timestamp": utc_now(),
    })


@app.get("/healthz")
def healthz():
    return jsonify({
        "status": "ok",
        "mode": MODE,
        "version": APP_VERSION,
        "uptime_seconds": round(time.monotonic() - START_TIME, 2),
        "timestamp": utc_now(),
    })


@app.get("/metrics")
def metrics():
    update_runtime_metrics()
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.post("/chaos")
def chaos():
    if MODE != "canary":
        return jsonify({
            "error": "chaos endpoint is only active in canary mode",
            "mode": MODE,
        }), 403

    payload = request.get_json(silent=True) or {}
    requested_mode = payload.get("mode")

    if requested_mode == "slow":
        duration = payload.get("duration")

        if not isinstance(duration, (int, float)) or duration < 0:
            return jsonify({
                "error": "duration must be a non-negative number",
            }), 400

        CHAOS_STATE["mode"] = "slow"
        CHAOS_STATE["duration"] = duration
        CHAOS_STATE["error_rate"] = 0.0
        update_runtime_metrics()

        return jsonify({
            "status": "chaos enabled",
            "mode": "slow",
            "duration": duration,
        })

    if requested_mode == "error":
        rate = payload.get("rate")

        if not isinstance(rate, (int, float)) or rate < 0 or rate > 1:
            return jsonify({
                "error": "rate must be a number between 0 and 1",
            }), 400

        CHAOS_STATE["mode"] = "error"
        CHAOS_STATE["duration"] = 0
        CHAOS_STATE["error_rate"] = rate
        update_runtime_metrics()

        return jsonify({
            "status": "chaos enabled",
            "mode": "error",
            "rate": rate,
        })

    if requested_mode == "recover":
        CHAOS_STATE["mode"] = "off"
        CHAOS_STATE["duration"] = 0
        CHAOS_STATE["error_rate"] = 0.0
        update_runtime_metrics()

        return jsonify({
            "status": "recovered",
            "mode": "off",
        })

    return jsonify({
        "error": "unsupported chaos mode",
        "allowed_modes": ["slow", "error", "recover"],
    }), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=APP_PORT)
