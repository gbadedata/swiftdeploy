# SwiftDeploy

SwiftDeploy is a declarative deployment lifecycle tool for containerized services. It uses a single `manifest.yaml` as the source of truth, generates runtime configuration from templates, manages Docker Compose lifecycle operations, enforces environment policy through Open Policy Agent, and supports stable/canary promotion with observable, auditable control flow.

The project demonstrates how a DevOps tool can turn a simple deployment manifest into a working stack made up of an application service, Nginx reverse proxy, OPA policy sidecar, health checks, Prometheus metrics, structured logs, and controlled rollout workflows - where no deployment or promotion can proceed unless policy explicitly permits it.

---

## Table of Contents

- [Overview](#overview)
- [Project Requirements Covered](#project-requirements-covered)
- [Architecture](#architecture)
- [Repository Structure](#repository-structure)
- [Manifest Design](#manifest-design)
- [Application Service](#application-service)
- [CLI Subcommands](#cli-subcommands)
- [Generated Configuration](#generated-configuration)
- [Policy Engine](#policy-engine)
- [Observability](#observability)
- [Audit Trail](#audit-trail)
- [Security and Runtime Hardening](#security-and-runtime-hardening)
- [Nginx Behaviour](#nginx-behaviour)
- [Docker and Docker Compose Behaviour](#docker-and-docker-compose-behaviour)
- [Prerequisites](#prerequisites)
- [Local Setup](#local-setup)
- [Usage Walkthrough](#usage-walkthrough)
- [Chaos Testing](#chaos-testing)
- [Validation Checks](#validation-checks)
- [Evidence and Screenshots](#evidence-and-screenshots)
- [Troubleshooting](#troubleshooting)
- [Design Decisions](#design-decisions)
- [Cleanup](#cleanup)

---

## Overview

Most deployment tasks require manually writing Docker Compose files, Nginx configuration, and deployment scripts. SwiftDeploy reverses that workflow.

Instead of hand-writing runtime configuration, the user edits only:

```text
manifest.yaml
```

The `swiftdeploy` CLI then derives everything else:

```text
docker-compose.yml
nginx.conf
```

Those generated files are intentionally treated as disposable artifacts. They can be deleted and recreated at any time by running:

```powershell
python ./swiftdeploy init
```

This ensures the manifest remains the single source of truth.

Beyond generation, SwiftDeploy acts as a policy-gated control plane. Before any deployment or promotion executes, the CLI queries Open Policy Agent and will refuse to proceed if the environment does not meet the defined safety standards. Every decision, every mode change, and every policy violation is recorded in an append-only audit trail.

---

## Project Requirements Covered

SwiftDeploy satisfies the Stage A and Stage B task requirements as follows:

| Requirement | Implementation |
|---|---|
| Declarative manifest | `manifest.yaml` defines service, Nginx, OPA, network, policy limits, and audit settings |
| Generated config files | `docker-compose.yml` and `nginx.conf` are generated from Jinja-style templates |
| CLI tool | `swiftdeploy` provides `init`, `validate`, `deploy`, `promote`, `teardown`, `status`, and `audit` subcommands |
| Stable/canary mode | The same app image runs with `MODE=stable` or `MODE=canary` |
| Canary header | Canary mode adds `X-Mode: canary` to every response |
| Chaos endpoint | `/chaos` supports slow, error, and recover modes in canary mode only |
| Health checks | `/healthz` returns liveness information and uptime in seconds |
| Prometheus metrics | `/metrics` exposes request counters, latency histograms, uptime, mode, and chaos state |
| Nginx reverse proxy | Nginx is the only public entry point on the configured port |
| No direct app exposure | App service uses `expose`, not host `ports` |
| Nginx error JSON | 502, 503, and 504 return structured JSON errors |
| Structured access logs | Logs use the required `$time_iso8601 | $status | ${request_time}s | $upstream_addr | $request` format |
| OPA policy sidecar | OPA runs as an isolated container, unreachable via the Nginx port |
| Infrastructure policy | Blocks deployment if disk free is below threshold or CPU load exceeds limit |
| Canary safety policy | Blocks promotion if error rate or P99 latency exceeds configured limits |
| Pre-deploy gate | CLI queries OPA before starting the stack — hard block on failure |
| Pre-promote gate | CLI scrapes `/metrics`, calculates error rate and P99 latency, queries OPA before promotion |
| Policy reasoning | Every OPA decision carries explicit reasoning surfaced to the operator |
| OPA failure handling | Each distinct OPA failure mode produces a different human-readable outcome |
| Live status dashboard | `swiftdeploy status` shows real-time req/s, error rate, P99 latency, and policy compliance |
| Audit trail | Every lifecycle event appended to `history.jsonl` |
| Audit report | `swiftdeploy audit` generates `audit_report.md` with timeline and violations table |
| Docker Compose lifecycle | Stack is started, restarted, promoted, and removed by the CLI |
| Non-root containers | App runs as `10001:10001`, Nginx as `101:101`, OPA with dropped capabilities |
| Capability dropping | All containers use `cap_drop: ALL` and `no-new-privileges:true` |
| Image size requirement | App image is built from `python:3.12-slim` and verified under 300MB |
| Manifest regeneration | `teardown --clean` removes generated configs; `init` regenerates them exactly |

---

## Architecture

SwiftDeploy follows this flow:

```text
manifest.yaml
     |
     v
swiftdeploy CLI
     |
     |---> OPA policy check (pre-deploy / pre-promote)
     |          |
     |          v
     |     policies/*.rego + policy_limits from manifest
     |
     v
templates/
     |----------------------|
     v                      v
docker-compose.yml       nginx.conf
     |                      |
     |                      v
     |                  Nginx reverse proxy (public: port 8080)
     |                      |
     v                      v
Docker Compose network -> App service (internal: port 3000)
                        -> OPA sidecar  (internal: port 8181, host loopback only)
```

Runtime request flow:

```text
Client
  |
  v
Nginx on localhost:8080
  |
  v
App service on internal Docker network port 3000
```

Policy decision flow:

```text
swiftdeploy CLI
  |
  v
POST http://127.0.0.1:8181/v1/data/swiftdeploy/<domain>/decision
  |
  v
OPA evaluates Rego policy against input
  |
  v
{ "allow": true/false, "reasons": [...] }
  |
  v
CLI surfaces reasoning and proceeds or blocks
```

The app container is not exposed directly to the host. All traffic must pass through Nginx. OPA is bound only to the host loopback interface and is not reachable via the Nginx port.

---

## Repository Structure

```text
swiftdeploy/
├── app/
│   ├── main.py                    # Flask API with /metrics, /healthz, /chaos
│   └── requirements.txt           # Pinned Python dependencies
├── policies/
│   ├── infrastructure.rego        # Pre-deploy: disk and CPU policy
│   └── canary.rego                # Pre-promote: error rate and latency policy
├── templates/
│   ├── docker-compose.yml.tpl     # Compose template including OPA service
│   └── nginx.conf.tpl             # Nginx template with headers and error handling
├── screenshots/
│   ├── 01_validate_all_pass.png
│   ├── 02_deploy_success.png
│   ├── 03_canary_and_headers.png
│   ├── 04_generated_configs.png
│   ├── 05_nginx_logs_clean.png
│   ├── 06_policy_hard_gate.png
│   ├── 07_status_chaos.png
│   ├── 08_promote_blocked.png
│   ├── 09_promote_stable_clean.png
│   └── 10_audit_report.png
├── audit/
│   └── .gitkeep                   # Directory preserved for audit output
├── .gitignore
├── Dockerfile
├── README.md
├── manifest.yaml
└── swiftdeploy                    # CLI entry point
```

Generated files are deliberately excluded from Git:

```text
docker-compose.yml
nginx.conf
history.jsonl
audit_report.md
```

They are produced by the CLI and should not be treated as manually maintained source files.

---

## Manifest Design

The manifest defines the complete deployment intent, including policy limits and audit settings.

```yaml
services:
  image: swift-deploy-1-node:latest
  port: 3000
  mode: stable
  version: "1.0.0"
  restart_policy: unless-stopped

nginx:
  image: nginx:latest
  port: 8080
  proxy_timeout: 10
  contact: o.odimayo@gbadedata.com

opa:
  image: openpolicyagent/opa:latest
  port: 8181
  policies_dir: policies
  decision_timeout_seconds: 5

network:
  name: swiftdeploy-net
  driver_type: bridge

logs:
  volume_name: swiftdeploy-logs

policy_limits:
  infrastructure:
    min_disk_free_gb: 10
    max_cpu_load: 2.0
  canary:
    max_error_rate: 0.01
    max_p99_latency_ms: 500
    evaluation_window_seconds: 30

audit:
  history_file: history.jsonl
  report_file: audit_report.md
```

The required base fields from Stage A are preserved unchanged:

```yaml
services:
  image: swift-deploy-1-node:latest
  port: 3000

nginx:
  image: nginx:latest
  port: 8080

network:
  name: swiftdeploy-net
  driver_type: bridge
```

The `policy_limits` section is the only place threshold values are defined. Rego policies read these values from `input.limits` at evaluation time — nothing is hardcoded inside the policy files themselves.

---

## Application Service

The application is a Python Flask service running inside the Docker image:

```text
swift-deploy-1-node:latest
```

It exposes four endpoints.

### `GET /`

Returns a welcome response with deployment metadata:

```json
{
  "message": "Welcome to SwiftDeploy",
  "mode": "stable",
  "version": "1.0.0",
  "timestamp": "2026-05-04T03:09:05.482280+00:00"
}
```

### `GET /healthz`

Returns service health and uptime:

```json
{
  "status": "ok",
  "mode": "stable",
  "version": "1.0.0",
  "uptime_seconds": 12.34,
  "timestamp": "2026-05-04T03:09:05.482280+00:00"
}
```

### `GET /metrics`

Returns runtime metrics in Prometheus text format. Tracked metrics include:

| Metric | Type | Labels | Description |
|---|---|---|---|
| `http_requests_total` | Counter | method, path, status_code | Total HTTP requests served |
| `http_request_duration_seconds` | Histogram | method, path | Request latency with standard buckets |
| `app_uptime_seconds` | Gauge | — | Seconds since process start |
| `app_mode` | Gauge | — | 0 = stable, 1 = canary |
| `chaos_active` | Gauge | — | 0 = none, 1 = slow, 2 = error |

### `POST /chaos`

Chaos mode is only active in canary mode. In stable mode, this endpoint returns 403.

Supported payloads:

```json
{ "mode": "slow", "duration": 2 }
```

Simulates latency by sleeping N seconds before responding to subsequent requests.

```json
{ "mode": "error", "rate": 0.5 }
```

Simulates intermittent HTTP 500 responses at the specified probability.

```json
{ "mode": "recover" }
```

Clears any active chaos behaviour and resets the chaos gauge to 0.

---

## CLI Subcommands

The `swiftdeploy` script is the deployment control plane.

### `init`

Reads `manifest.yaml` and generates:

```text
docker-compose.yml
nginx.conf
```

Command:

```powershell
python .\swiftdeploy init
```

Expected output:

```text
[PASS] Loaded manifest.yaml
[PASS] Generated docker-compose.yml
[PASS] Generated nginx.conf
```

---

### `validate`

Runs five pre-flight checks before any deployment is attempted:

1. `manifest.yaml` exists and is valid YAML
2. Required fields are present and non-empty
3. Docker image exists locally
4. Nginx host port is free
5. Generated `nginx.conf` is syntactically valid

Command:

```powershell
python .\swiftdeploy validate
```

Expected output:

```text
[PASS] manifest.yaml exists and is valid YAML
[PASS] All required fields are present and non-empty
[PASS] Docker image exists locally: swift-deploy-1-node:latest
[PASS] Nginx port is free on host: 8080
[PASS] Generated nginx.conf is syntactically valid
```

Validation exits non-zero if any check fails.

---

### `deploy`

Runs `init`, validates the stack, queries OPA for infrastructure policy approval, starts Docker Compose, and waits for health checks to pass. If OPA denies the deployment, the stack is not started and the policy reasoning is printed to the operator.

Command:

```powershell
python .\swiftdeploy deploy
```

Expected output (policy passing):

```text
[PASS] Loaded manifest.yaml
[PASS] Generated docker-compose.yml
[PASS] Generated nginx.conf
[PASS] manifest.yaml exists and is valid YAML
[PASS] All required fields are present and non-empty
[PASS] Docker image exists locally: swift-deploy-1-node:latest
[PASS] Nginx port is free on host: 8080
[PASS] Generated nginx.conf is syntactically valid
[POLICY][PASS] infrastructure.pre_deploy
 - Infrastructure policy passed
[PASS] Docker Compose stack started
[PASS] Health check passed: mode=stable, version=1.0.0
```

Expected output (policy blocking):

```text
[POLICY][FAIL] infrastructure.pre_deploy
 - Disk free 2GB is below required minimum 10GB
 - CPU load 3.20 exceeds allowed maximum 2.00
[FAIL] Deployment blocked by policy.
```

The command waits up to 60 seconds for `/healthz` to become healthy.

---

### `promote canary`

Switches service mode to canary without a policy check. Canary is an experimental mode — the gate applies when returning to stable.

Command:

```powershell
python .\swiftdeploy promote canary
```

What it does:

1. Updates `manifest.yaml` in-place
2. Regenerates `docker-compose.yml` with `MODE=canary`
3. Recreates only the app container
4. Confirms the new mode through `/healthz`

Expected output:

```text
[PASS] Updated manifest.yaml mode to canary
[PASS] Regenerated docker-compose.yml
[PASS] Restarted service container only
[PASS] Promotion confirmed through /healthz: mode=canary
```

Verify canary headers:

```powershell
curl.exe -i http://127.0.0.1:8080/healthz
```

Expected headers:

```http
X-Mode: canary
X-Deployed-By: swiftdeploy
```

---

### `promote stable`

Switches service mode back to stable. Before executing, the CLI scrapes `/metrics`, calculates the current error rate and P99 latency over all observed requests, and queries OPA's canary safety policy. If the canary is unhealthy, promotion is blocked and the reasoning is surfaced.

Command:

```powershell
python .\swiftdeploy promote stable
```

Expected output (canary healthy):

```text
[POLICY][PASS] canary.pre_promote
 - Canary safety policy passed
[PASS] Updated manifest.yaml mode to stable
[PASS] Regenerated docker-compose.yml
[PASS] Restarted service container only
[PASS] Promotion confirmed through /healthz: mode=stable
```

Expected output (canary unhealthy):

```text
[POLICY][FAIL] canary.pre_promote
 - Error rate 0.380952 exceeds allowed maximum 0.01
[FAIL] Promotion blocked by policy.
```

---

### `teardown`

Stops and removes the stack, including containers, networks, and volumes.

Command:

```powershell
python .\swiftdeploy teardown
```

Expected output:

```text
[PASS] Removed containers, networks, and volumes
```

---

### `teardown --clean`

Stops the stack and deletes generated configuration files.

Command:

```powershell
python .\swiftdeploy teardown --clean
```

Expected output:

```text
[PASS] Removed containers, networks, and volumes
[PASS] Deleted generated file: docker-compose.yml
[PASS] Deleted generated file: nginx.conf
```

This proves that generated files are disposable and can be recreated from the manifest alone.

---

### `status`

Scrapes `/metrics`, calculates real-time req/s and P99 latency, queries both OPA policy domains independently, and prints a live dashboard. Every scrape is appended to `history.jsonl` for the audit trail.

Command (single scrape):

```powershell
python .\swiftdeploy status --once
```

Command (continuous, refreshes every 2 seconds):

```powershell
python .\swiftdeploy status
```

Command (custom interval):

```powershell
python .\swiftdeploy status --interval 5
```

Expected output:

```text
SwiftDeploy Status
==================
Timestamp: 2026-05-06T23:12:26.328363+00:00
Mode: canary
Chaos: error
Req/s: 0.00
Error rate: 38.10%
P99 latency: 5.00ms
Uptime: 128.42s

Policy Compliance
-----------------
[PASS] infrastructure.pre_deploy
  - Infrastructure policy passed
[FAIL] canary.pre_promote
  - Error rate 0.380952 exceeds allowed maximum 0.01
```

Press `Ctrl+C` to stop the continuous dashboard.

---

### `audit`

Parses `history.jsonl` and generates `audit_report.md`. The report contains a deployment timeline and a dedicated violations section listing every policy failure with its timestamp, domain, and reasoning.

Command:

```powershell
python .\swiftdeploy audit
```

Expected output:

```text
[PASS] Generated audit_report.md
```

The report renders correctly as GitHub Flavored Markdown and can be viewed directly on GitHub.

---

## Generated Configuration

`swiftdeploy init` generates two files from templates.

### `docker-compose.yml`

Generated from:

```text
templates/docker-compose.yml.tpl
```

It defines:

- `app` service with health check on `/healthz`
- `nginx` service depending on app health, publishing port 8080
- `opa` service bound to `127.0.0.1:8181` only — not reachable via Nginx
- shared Docker network for internal service communication
- named volume for log persistence
- environment variables injected from manifest values
- restart policy, capability restrictions, and non-root users for all services

The app service uses `expose`, not host `ports`, so it is not directly reachable from the host machine.

### `nginx.conf`

Generated from:

```text
templates/nginx.conf.tpl
```

It defines:

- Nginx listener on the manifest-defined port
- reverse proxy to the app service on the internal Docker network
- proxy timeout from manifest
- structured access logging in the required format
- JSON error responses for 502, 503, and 504
- `X-Deployed-By: swiftdeploy` response header on all requests
- forwarding of upstream `X-Mode` header from the app

---

## Policy Engine

SwiftDeploy uses Open Policy Agent as an isolated policy sidecar. The CLI never makes allow/deny decisions itself — all decision logic lives exclusively in Rego policy files.

### Architecture principle

Each policy domain owns exactly one question and one set of data it cares about. The CLI queries each domain independently. A change to one domain's policy never requires touching another.

| Domain | Question | Input data | Blocks |
|---|---|---|---|
| `infrastructure` | `pre_deploy` | Disk free GB, CPU load, configured limits | `deploy` |
| `canary` | `pre_promote` | Error rate, P99 latency ms, configured limits | `promote stable` |

### Infrastructure policy (`policies/infrastructure.rego`)

Evaluated before every deployment. Sends host stats and configured limits to OPA.

Rules:

- Disk free must be >= `policy_limits.infrastructure.min_disk_free_gb`
- CPU load must be <= `policy_limits.infrastructure.max_cpu_load`

Every decision includes a `reasons` array. On failure, each reason names the specific metric and threshold that was violated. On pass, reasons confirm the policy passed.

### Canary safety policy (`policies/canary.rego`)

Evaluated before promoting from canary back to stable. Sends observed metrics scraped from `/metrics` and configured limits to OPA.

Rules:

- Error rate must be <= `policy_limits.canary.max_error_rate`
- P99 latency must be <= `policy_limits.canary.max_p99_latency_ms`

### Threshold configuration

All threshold values are defined in `manifest.yaml` under `policy_limits`. Rego files read them from `input.limits`. Changing a threshold requires only editing the manifest — no Rego files need to be touched.

### OPA failure handling

The CLI handles every distinct OPA failure mode with a specific, human-readable outcome:

| Failure mode | Output |
|---|---|
| OPA container not reachable | `OPA unavailable at http://127.0.0.1:8181` |
| OPA request timed out | `OPA decision timed out after 5s` |
| OPA returned non-200 | `OPA returned HTTP 503: ...` |
| OPA response was not JSON | `OPA returned non-JSON response` |
| OPA result missing | `OPA response did not include a decision result` |

In all failure cases the operation is blocked — the CLI never proceeds when OPA is unreachable.

### OPA isolation

The OPA container is published only to the host loopback interface:

```yaml
ports:
  - "127.0.0.1:8181:8181"
```

Nginx has no route to port 8181. The OPA API is not accessible via the Nginx port under any circumstances.

---

## Observability

### `/metrics` endpoint

The app exposes Prometheus-format metrics at `/metrics`. The status command scrapes this endpoint directly — no external Prometheus server is required.

Example output:

```text
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",path="/",status_code="200"} 30.0
http_requests_total{method="GET",path="/",status_code="500"} 12.0

# HELP http_request_duration_seconds HTTP request latency in seconds
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{le="0.005",method="GET",path="/"} 42.0
...

# HELP app_uptime_seconds Application uptime in seconds
# TYPE app_uptime_seconds gauge
app_uptime_seconds 210.91

# HELP app_mode Application mode: 0=stable, 1=canary
# TYPE app_mode gauge
app_mode 1.0

# HELP chaos_active Chaos state: 0=none, 1=slow, 2=error
# TYPE chaos_active gauge
chaos_active 2.0
```

### Real-time status dashboard

`swiftdeploy status` calculates the following from raw Prometheus samples:

- **Req/s** - change in `http_requests_total` since the previous scrape divided by elapsed seconds
- **Error rate** - 5xx responses as a fraction of all non-health, non-metrics requests
- **P99 latency** - derived from histogram bucket counts using linear interpolation to find the 99th percentile bound

Health check and metrics paths are excluded from error rate and latency calculations to avoid skewing results.

---

## Audit Trail

Every significant lifecycle event is appended to `history.jsonl` as a JSON object with a UTC timestamp, event type, and event data.

Recorded event types:

| Event type | Triggered by |
|---|---|
| `deploy` | Successful `swiftdeploy deploy` |
| `mode_change` | Successful `swiftdeploy promote` |
| `policy_violation` | Any OPA FAIL during deploy or promote |
| `pre_promote_policy_check` | Every `promote stable` attempt |
| `status_scrape` | Every `swiftdeploy status` scrape |
| `metrics_failure` | Failed `/metrics` scrape during promote |

### Generating the audit report

```powershell
python .\swiftdeploy audit
```

The generated `audit_report.md` contains:

- **Summary** - total event count, mode/deploy event count, and violation count
- **Timeline** - table of all deploy and mode change events with timestamps and summaries
- **Policy Violations** - table of every policy failure with timestamp, domain, question, and full reasoning

---

## Security and Runtime Hardening

SwiftDeploy applies several runtime security controls across all containers.

### Non-root execution

The app runs as:

```yaml
user: "10001:10001"
```

Nginx runs as:

```yaml
user: "101:101"
```

OPA runs with dropped capabilities and no-new-privileges.

### Capability reduction

All containers drop Linux capabilities:

```yaml
cap_drop:
  - ALL
```

### No privilege escalation

All services use:

```yaml
security_opt:
  - no-new-privileges:true
```

### No direct service exposure

The app does not publish a host port:

```yaml
expose:
  - "3000"
```

The OPA container is published only to the host loopback interface:

```yaml
ports:
  - "127.0.0.1:8181:8181"
```

The only public entry point is Nginx on port 8080.

---

## Nginx Behaviour

Nginx listens on the manifest-defined port:

```yaml
nginx:
  port: 8080
```

### Headers

Nginx adds to every response:

```http
X-Deployed-By: swiftdeploy
```

In canary mode, the app adds:

```http
X-Mode: canary
```

Nginx forwards this header from the upstream response.

### Error responses

Nginx returns structured JSON bodies for upstream failure codes:

```json
{
  "error": "bad gateway",
  "code": 502,
  "service": "swiftdeploy",
  "contact": "o.odimayo@gbadedata.com"
}
```

Equivalent responses are defined for 503 and 504.

### Access log format

```text
$time_iso8601 | $status | ${request_time}s | $upstream_addr | $request
```

Example output:

```text
2026-05-06T23:04:50+00:00 | 200 | 0.001s | 172.18.0.2:3000 | GET / HTTP/1.1
2026-05-06T23:04:50+00:00 | 200 | 0.001s | 172.18.0.2:3000 | GET /healthz HTTP/1.1
```

---

## Docker and Docker Compose Behaviour

The generated Compose file ensures:

- `app`, `nginx`, and `opa` share the configured internal network
- `nginx` depends on `app` health before starting
- service environment variables (`MODE`, `APP_VERSION`, `APP_PORT`) are injected from manifest values
- restart policy is controlled by the manifest
- named volume is mounted for log persistence
- `app` has a `/healthz` health check
- `nginx` has a `/healthz` proxy health check
- `opa` has a health check using `opa eval true`
- app is not directly exposed to the host

Injected app environment:

```yaml
environment:
  MODE: "stable"
  APP_VERSION: "1.0.0"
  APP_PORT: "3000"
```

---

## Prerequisites

Required locally:

- Docker Desktop
- Docker Compose plugin
- Python 3.12+
- Git
- PowerShell, Bash, or another terminal

This project was developed and tested with:

```text
Python 3.13.11
Docker Desktop 29.2.1
Docker Compose v5.0.2
PowerShell on Windows
```

---

## Local Setup

Clone the repository:

```powershell
git clone https://github.com/gbadedata/swiftdeploy.git
cd swiftdeploy
```

Create a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install CLI dependencies:

```powershell
python -m pip install --upgrade pip
pip install pyyaml jinja2 requests
```

Build the app image:

```powershell
docker build -t swift-deploy-1-node:latest .
```

Verify image size:

```powershell
docker images swift-deploy-1-node:latest
```

The image must be under 300MB.

---

## Usage Walkthrough

### 1. Generate configuration

```powershell
python .\swiftdeploy init
```

### 2. Validate the deployment

```powershell
python .\swiftdeploy validate
```

### 3. Deploy the stack

```powershell
python .\swiftdeploy deploy
```

### 4. Test the root endpoint

```powershell
curl.exe http://127.0.0.1:8080/
```

### 5. Test health

```powershell
curl.exe http://127.0.0.1:8080/healthz
```

### 6. View live metrics

```powershell
curl.exe http://127.0.0.1:8080/metrics
```

### 7. Check status and policy compliance

```powershell
python .\swiftdeploy status --once
```

### 8. Promote to canary

```powershell
python .\swiftdeploy promote canary
curl.exe -i http://127.0.0.1:8080/healthz
```

### 9. Inject chaos and observe policy failure

```powershell
@'
{"mode":"error","rate":0.5}
'@ | Set-Content -Encoding ascii chaos-error.json

curl.exe -X POST http://127.0.0.1:8080/chaos -H "Content-Type: application/json" --data-binary "@chaos-error.json"

1..20 | ForEach-Object { curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:8080/ }

python .\swiftdeploy status --once
```

### 10. Attempt promotion — observe policy block

```powershell
python .\swiftdeploy promote stable
```

### 11. Recover and promote cleanly

```powershell
@'
{"mode":"recover"}
'@ | Set-Content -Encoding ascii chaos-recover.json

curl.exe -X POST http://127.0.0.1:8080/chaos -H "Content-Type: application/json" --data-binary "@chaos-recover.json"

docker compose restart app
Start-Sleep -Seconds 15
1..30 | ForEach-Object { curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:8080/ }

python .\swiftdeploy promote stable
```

### 12. Generate the audit report

```powershell
python .\swiftdeploy audit
```

### 13. View Nginx logs

```powershell
docker logs swiftdeploy-nginx --tail 10
```

### 14. Clean up

```powershell
python .\swiftdeploy teardown --clean
```

---

## Chaos Testing

PowerShell can corrupt inline JSON quoting when calling `curl.exe`. For reliable testing, use JSON files.

Promote to canary first:

```powershell
python .\swiftdeploy promote canary
```

### Slow mode

```powershell
@'
{ "mode": "slow", "duration": 2 }
'@ | Set-Content -Encoding ascii chaos-slow.json

curl.exe -X POST http://127.0.0.1:8080/chaos `
  -H "Content-Type: application/json" `
  --data-binary "@chaos-slow.json"

curl.exe -w "`nTotal time: %{time_total}s`n" http://127.0.0.1:8080/
```

Expected result: response delay of approximately two seconds.

### Error mode

```powershell
@'
{ "mode": "error", "rate": 0.5 }
'@ | Set-Content -Encoding ascii chaos-error.json

curl.exe -X POST http://127.0.0.1:8080/chaos `
  -H "Content-Type: application/json" `
  --data-binary "@chaos-error.json"

1..10 | ForEach-Object { curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:8080/ }
```

Expected result: mixed `200` and `500` responses.

After injecting errors, run the status dashboard to see the canary policy fail in real time:

```powershell
python .\swiftdeploy status --once
```

### Recover

```powershell
@'
{ "mode": "recover" }
'@ | Set-Content -Encoding ascii chaos-recover.json

curl.exe -X POST http://127.0.0.1:8080/chaos `
  -H "Content-Type: application/json" `
  --data-binary "@chaos-recover.json"
```

Remove temporary test files:

```powershell
Remove-Item chaos-*.json -ErrorAction SilentlyContinue
```

---

## Validation Checks

The CLI implements five pre-flight checks. All must pass before deployment proceeds.

### 1. Manifest exists and is valid YAML

The CLI fails if `manifest.yaml` is missing, empty, or not parseable as YAML.

### 2. Required fields are present and non-empty

Required fields include:

```text
services.image         services.port          services.mode
services.version       services.restart_policy
nginx.image            nginx.port             nginx.proxy_timeout     nginx.contact
opa.image              opa.port               opa.policies_dir        opa.decision_timeout_seconds
network.name           network.driver_type
logs.volume_name
policy_limits.infrastructure                  policy_limits.canary
audit.history_file     audit.report_file
```

### 3. Docker image exists locally

The CLI checks the image with `docker image inspect` before deployment.

### 4. Nginx port is free

The CLI checks that the configured Nginx port is not already bound on the host.

### 5. Generated Nginx configuration is syntactically valid

The CLI validates `nginx.conf` by running `nginx -t` inside a temporary Nginx container. A host mapping for the `app` upstream name is added for the validation context so DNS resolution does not require the full stack to be running.

---

## Evidence and Screenshots

The `screenshots/` folder contains submission evidence for both Stage A and Stage B.

| Screenshot | Stage | Purpose |
|---|---|---|
| `01_validate_all_pass.png` | A | All five validation checks passing |
| `02_deploy_success.png` | A | Successful stable deployment with health check |
| `03_canary_and_headers.png` | A | Canary promotion, `X-Mode: canary`, `X-Deployed-By: swiftdeploy` |
| `04_generated_configs.png` | A | Generated `docker-compose.yml` and `nginx.conf` contents |
| `05_nginx_logs_clean.png` | A | Nginx access logs in required structured format |
| `06_policy_hard_gate.png` | B | Deploy blocked by infrastructure policy — disk threshold exceeded |
| `07_status_chaos.png` | B | Status dashboard showing chaos active and canary policy failing |
| `08_promote_blocked.png` | B | Promotion to stable blocked by canary safety policy |
| `09_promote_stable_clean.png` | B | Clean promotion after chaos recovery — policy passes |
| `10_audit_report.png` | B | Generated audit report with timeline and violations table |

---

## Troubleshooting

### Port 8080 already in use

If validation fails with:

```text
[FAIL] Nginx port is already bound on host: 8080
```

Stop the running stack:

```powershell
python .\swiftdeploy teardown --clean
```

Check for active listeners:

```powershell
netstat -ano | findstr :8080
```

`TIME_WAIT` entries are not usually a problem. Active `LISTENING` entries are.

---

### OPA unavailable during deploy or promote

If the CLI reports:

```text
OPA unavailable at http://127.0.0.1:8181
```

Check that OPA started correctly:

```powershell
docker logs swiftdeploy-opa
```

OPA is started automatically by `swiftdeploy deploy`. If running promote independently after a teardown, start the stack first.

---

### Promotion blocked after chaos recovery

The Prometheus error counter persists for the lifetime of the app process. Restarting the app container resets the counters:

```powershell
docker compose restart app
Start-Sleep -Seconds 15
1..30 | ForEach-Object { curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:8080/ }
python .\swiftdeploy promote stable
```

---

### Nginx reports `unknown directive events` with BOM characters

This means a UTF-8 BOM was written at the start of `nginx.conf`. Regenerate it:

```powershell
python .\swiftdeploy teardown --clean
python .\swiftdeploy init
```

The CLI renderer writes generated files as clean UTF-8 bytes without BOM.

---

### Inline JSON fails in PowerShell

Use JSON files and `--data-binary` rather than inline escaped JSON strings. PowerShell quote handling corrupts JSON when passed directly to `curl.exe`.

---

### Generated files are missing

Run:

```powershell
python .\swiftdeploy init
```

Generated files are intentionally excluded from Git and can always be recreated from the manifest and templates.

---

## Design Decisions

### Manifest as single source of truth

The manifest defines deployment intent. Generated files are artifacts, not source files. This allows deterministic regeneration and reduces manual drift. `docker-compose.yml` and `nginx.conf` can be deleted and `swiftdeploy init` can be run to restore them exactly.

### Templates instead of handwritten configs

Templates make the relationship between manifest values and generated runtime files explicit. This is closer to real-world infrastructure tooling such as Helm, Terraform templating, and deployment generators.

### OPA as an isolated sidecar, not an embedded library

The decision logic lives in Rego files, not in Python. This means policies can be updated without touching the CLI. Each domain - infrastructure and canary - owns its own policy file, its own question, and its own set of input data. A change to the canary policy cannot accidentally affect the infrastructure check.

### Thresholds in manifest, not in Rego

Hardcoding limits inside Rego files makes them environment-specific and harder to tune. By putting all threshold values in `manifest.yaml` under `policy_limits`, the same policy files work across any environment with different limits - without editing Rego.

### Pre-promote gate on `promote stable`, not `promote canary`

Promoting to canary is an intentional experiment. The safety gate applies on the return journey — when promoting back to stable - because that is when the operator needs to prove the canary was healthy before widening the blast radius.

### Non-blocking Slack-style alerting via history.jsonl

Rather than integrating a notification service, every event is written to `history.jsonl`. This is the audit source of truth. The `audit` command reads it and renders a report. External alerting systems can tail this file independently.

### Single app worker

The app uses one Gunicorn worker to keep chaos state deterministic during local testing. With multiple workers, in-memory chaos state could be updated in one worker while requests are served by another, causing inconsistent error rates and unpredictable policy outcomes.

### Generated files excluded from Git

`docker-compose.yml`, `nginx.conf`, `history.jsonl`, and `audit_report.md` are excluded because they are runtime artifacts. The source of truth is the manifest and the templates. Committing generated files creates drift risk and makes the manifest redundant.

### OPA not exposed through Nginx

OPA is bound to `127.0.0.1:8181` only. It shares the internal Docker network with the app and Nginx but is not reachable from the public Nginx port. This prevents the policy API from being queried or manipulated from outside the stack.

---

## Cleanup

Stop the stack and remove all generated files:

```powershell
python .\swiftdeploy teardown --clean
```

Verify generated files were deleted:

```powershell
Test-Path .\docker-compose.yml
Test-Path .\nginx.conf
```

Expected:

```text
False
False
```

Regenerate at any time:

```powershell
python .\swiftdeploy init
```

---

## Final Notes

SwiftDeploy is intentionally local-first. The task does not require AWS or domain deployment, so the implementation avoids unnecessary cloud dependencies and keeps the grading path reproducible on any Docker-enabled machine.

The key conditions are preserved:

```text
manifest.yaml is the single source of truth
OPA is the only decision-maker - the CLI never allows or denies itself
Generated files are disposable and fully reproducible
No deployment or promotion proceeds without explicit policy approval
```

## Blog Post

A full technical deep dive covering both Stage A and Stage B — the design, the policy engine, the chaos testing, and the lessons learned — is published at:

**https://dev.to/gbadedata/from-broken-repo-to-policy-gated-deployment-platform-building-swiftdeploy-from-scratch-2nmo**

The stack can be destroyed, generated files can be removed, and the complete runtime configuration - including the OPA sidecar, policy evaluation, metrics, and audit trail - can be recreated by running:

```powershell
python .\swiftdeploy init
python .\swiftdeploy deploy
```
