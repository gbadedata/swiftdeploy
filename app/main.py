import os
import random
import time
from datetime import datetime, timezone
from flask import Flask, jsonify, request, g


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


@app.before_request
def apply_chaos():
    g.request_started_at = time.monotonic()

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
                "timestamp": datetime.now(timezone.utc).isoformat()
            }), 500

    return None


@app.after_request
def add_headers(response):
    if MODE == "canary":
        response.headers["X-Mode"] = "canary"
    return response


@app.get("/")
def index():
    return jsonify({
        "message": "Welcome to SwiftDeploy",
        "mode": MODE,
        "version": APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


@app.get("/healthz")
def healthz():
    uptime = round(time.monotonic() - START_TIME, 2)

    return jsonify({
        "status": "ok",
        "mode": MODE,
        "version": APP_VERSION,
        "uptime_seconds": uptime,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


@app.post("/chaos")
def chaos():
    if MODE != "canary":
        return jsonify({
            "error": "chaos endpoint is only active in canary mode",
            "mode": MODE
        }), 403

    payload = request.get_json(silent=True) or {}
    requested_mode = payload.get("mode")

    if requested_mode == "slow":
        duration = payload.get("duration")

        if not isinstance(duration, (int, float)) or duration < 0:
            return jsonify({
                "error": "duration must be a non-negative number"
            }), 400

        CHAOS_STATE["mode"] = "slow"
        CHAOS_STATE["duration"] = duration
        CHAOS_STATE["error_rate"] = 0.0

        return jsonify({
            "status": "chaos enabled",
            "mode": "slow",
            "duration": duration
        })

    if requested_mode == "error":
        rate = payload.get("rate")

        if not isinstance(rate, (int, float)) or rate < 0 or rate > 1:
            return jsonify({
                "error": "rate must be a number between 0 and 1"
            }), 400

        CHAOS_STATE["mode"] = "error"
        CHAOS_STATE["duration"] = 0
        CHAOS_STATE["error_rate"] = rate

        return jsonify({
            "status": "chaos enabled",
            "mode": "error",
            "rate": rate
        })

    if requested_mode == "recover":
        CHAOS_STATE["mode"] = "off"
        CHAOS_STATE["duration"] = 0
        CHAOS_STATE["error_rate"] = 0.0

        return jsonify({
            "status": "recovered",
            "mode": "off"
        })

    return jsonify({
        "error": "unsupported chaos mode",
        "allowed_modes": ["slow", "error", "recover"]
    }), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=APP_PORT)
