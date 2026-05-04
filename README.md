# SwiftDeploy

SwiftDeploy is a declarative deployment lifecycle tool for containerized services. It uses a single `manifest.yaml` as the source of truth, generates runtime configuration from templates, manages Docker Compose lifecycle operations, and supports stable/canary promotion without manually editing generated files.

The project demonstrates how a DevOps tool can turn a simple deployment manifest into a working stack made up of an application service, Nginx reverse proxy, Docker Compose configuration, health checks, structured logs, and controlled rollout workflows.

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

```bash
python ./swiftdeploy init
```

This ensures the manifest remains the single source of truth.

---

## Project Requirements Covered

SwiftDeploy satisfies the Stage 4A task requirements as follows:

| Requirement | Implementation |
|---|---|
| Declarative manifest | `manifest.yaml` defines service, Nginx, network, mode, version, and log volume settings |
| Generated config files | `docker-compose.yml` and `nginx.conf` are generated from Jinja-style templates |
| CLI tool | `swiftdeploy` provides `init`, `validate`, `deploy`, `promote`, and `teardown` subcommands |
| Stable/canary mode | The same app image runs with `MODE=stable` or `MODE=canary` |
| Canary header | Canary mode adds `X-Mode: canary` to responses |
| Chaos endpoint | `/chaos` supports slow, error, and recover modes in canary mode only |
| Health checks | `/healthz` returns liveness information and uptime |
| Nginx reverse proxy | Nginx is the only public entry point on the configured port |
| No direct app exposure | App service uses `expose`, not host `ports` |
| Nginx error JSON | 502, 503, and 504 return structured JSON errors |
| Structured access logs | Logs use the required `$time_iso8601 | $status | ${request_time}s | $upstream_addr | $request` format |
| Docker Compose lifecycle | Stack is started, restarted, promoted, and removed by the CLI |
| Non-root app container | App runs as UID/GID `10001:10001` |
| Capability dropping | Containers drop Linux capabilities with `cap_drop: ALL` |
| Image size requirement | App image is built from `python:3.12-slim` and verified under 300MB |
| Manifest regeneration test | `teardown --clean` removes generated configs; `init` regenerates them |

---

## Architecture

SwiftDeploy follows this flow:

```text
manifest.yaml
     |
     v
swiftdeploy CLI
     |
     v
templates/
     |----------------------|
     v                      v
docker-compose.yml       nginx.conf
     |                      |
     |                      v
     |                  Nginx reverse proxy
     |                      |
     v                      v
Docker Compose network -> App service
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

The app container is not exposed directly to the host. All traffic must pass through Nginx.

---

## Repository Structure

```text
swiftdeploy/
├── app/
│   ├── main.py
│   └── requirements.txt
├── templates/
│   ├── docker-compose.yml.tpl
│   └── nginx.conf.tpl
├── screenshots/
│   ├── 01_templates_docker_compose_tpl.png
│   ├── 02_templates_nginx_conf_tpl.png
│   ├── 03_init_generation.png
│   ├── 04_validate_all_pass.png
│   ├── 05_deploy_success.png
│   ├── 06_root_endpoint_response.png
│   ├── 07_canary_and_headers.png
│   └── 08_nginx_logs_clean.png
├── .gitignore
├── Dockerfile
├── README.md
├── manifest.yaml
└── swiftdeploy
```

Generated files are deliberately excluded from Git:

```text
docker-compose.yml
nginx.conf
```

They are produced by the CLI and should not be treated as manually maintained source files.

---

## Manifest Design

The manifest defines the deployment intent.

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
  contact: "admin@gbadedata.com"

network:
  name: swiftdeploy-net
  driver_type: bridge

logs:
  volume_name: swiftdeploy-logs
```

The required base fields are preserved:

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

Additional fields are included to support versioning, rollout mode, restart policy, proxy timeout, contact metadata, and log volume naming.

---

## Application Service

The application is a Python HTTP service running inside the Docker image:

```text
swift-deploy-1-node:latest
```

It exposes three endpoints.

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

### `POST /chaos`

Chaos mode is only active in canary mode.

Supported payloads:

```json
{ "mode": "slow", "duration": 2 }
```

Simulates latency by delaying subsequent requests.

```json
{ "mode": "error", "rate": 0.5 }
```

Simulates intermittent HTTP 500 responses.

```json
{ "mode": "recover" }
```

Clears any active chaos behaviour.

In stable mode, `/chaos` is blocked intentionally.

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

```bash
python ./swiftdeploy init
```

Expected output:

```text
[PASS] Loaded manifest.yaml
[PASS] Generated docker-compose.yml
[PASS] Generated nginx.conf
```

---

### `validate`

Runs five pre-flight checks:

1. `manifest.yaml` exists and is valid YAML
2. Required fields are present and non-empty
3. Docker image exists locally
4. Nginx host port is free
5. Generated `nginx.conf` is syntactically valid

Command:

```bash
python ./swiftdeploy validate
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

Runs `init`, validates the stack, starts Docker Compose, and waits for health checks to pass.

Command:

```bash
python ./swiftdeploy deploy
```

Expected output:

```text
[PASS] Docker Compose stack started
[PASS] Health check passed: mode=stable, version=1.0.0
```

The command waits up to 60 seconds for `/healthz` to become healthy.

---

### `promote canary`

Switches service mode to canary.

Command:

```bash
python ./swiftdeploy promote canary
```

What it does:

1. Updates `manifest.yaml` in-place
2. Regenerates `docker-compose.yml`
3. Recreates the app container only
4. Confirms the new mode through `/healthz`

Expected output:

```text
[PASS] Updated manifest.yaml mode to canary
[PASS] Regenerated docker-compose.yml
[PASS] Restarted service container only
[PASS] Promotion confirmed through /healthz: mode=canary
```

Verify canary headers:

```bash
curl -i http://127.0.0.1:8080/healthz
```

Expected headers:

```http
X-Mode: canary
X-Deployed-By: swiftdeploy
```

---

### `promote stable`

Switches service mode back to stable.

Command:

```bash
python ./swiftdeploy promote stable
```

Expected output:

```text
[PASS] Updated manifest.yaml mode to stable
[PASS] Regenerated docker-compose.yml
[PASS] Restarted service container only
[PASS] Promotion confirmed through /healthz: mode=stable
```

---

### `teardown`

Stops and removes the stack.

Command:

```bash
python ./swiftdeploy teardown
```

Expected output:

```text
[PASS] Removed containers, networks, and volumes
```

---

### `teardown --clean`

Stops the stack and deletes generated configuration files.

Command:

```bash
python ./swiftdeploy teardown --clean
```

Expected output:

```text
[PASS] Removed containers, networks, and volumes
[PASS] Deleted generated file: docker-compose.yml
[PASS] Deleted generated file: nginx.conf
```

This proves that generated files are disposable and can be recreated from the manifest.

---

## Generated Configuration

`swiftdeploy init` generates two files.

### `docker-compose.yml`

Generated from:

```text
templates/docker-compose.yml.tpl
```

It defines:

- app service
- Nginx service
- shared Docker network
- named log volume
- health checks
- environment variables
- restart policies
- capability restrictions

The app service uses `expose`, not host `ports`, so it is not directly reachable from the host.

### `nginx.conf`

Generated from:

```text
templates/nginx.conf.tpl
```

It defines:

- Nginx listener port
- reverse proxy to the app
- timeout settings
- structured logging
- JSON error responses
- `X-Deployed-By` response header
- upstream `X-Mode` header forwarding

---

## Security and Runtime Hardening

SwiftDeploy applies several runtime security controls.

### Non-root execution

The app runs as:

```yaml
user: "10001:10001"
```

Nginx runs as:

```yaml
user: "101:101"
```

### Capability reduction

Both containers drop Linux capabilities:

```yaml
cap_drop:
  - ALL
```

### No privilege escalation

Both services use:

```yaml
security_opt:
  - no-new-privileges:true
```

### No direct service exposure

The app does not publish a host port.

Correct:

```yaml
expose:
  - "3000"
```

The only public entry point is Nginx on the configured host port.

---

## Nginx Behaviour

Nginx listens on the manifest-defined port:

```yaml
nginx:
  port: 8080
```

Generated config:

```nginx
server {
    listen 8080;
}
```

### Headers

Nginx adds:

```http
X-Deployed-By: swiftdeploy
```

The app adds this in canary mode:

```http
X-Mode: canary
```

Nginx forwards the upstream header.

### Error responses

Nginx returns JSON bodies for upstream failure codes:

```json
{
  "error": "bad gateway",
  "code": 502,
  "service": "swiftdeploy",
  "contact": "admin@gbadedata.com"
}
```

Similar JSON responses are defined for 503 and 504.

### Access log format

Required format:

```text
$time_iso8601 | $status | ${request_time}s | $upstream_addr | $request
```

Example output:

```text
2026-05-04T03:04:50+00:00 | 200 | 0.001s | 172.18.0.2:3000 | GET / HTTP/1.1
2026-05-04T03:04:50+00:00 | 200 | 0.001s | 172.18.0.2:3000 | GET /healthz HTTP/1.1
```

---

## Docker and Docker Compose Behaviour

The generated Compose file ensures:

- app and Nginx share the configured network
- Nginx depends on app health
- service environment variables are injected from the manifest
- restart policy is controlled by the manifest
- named volume is mounted for logs
- app has a `/healthz` health check
- Nginx has a `/healthz` proxy health check
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
Docker Desktop
PowerShell on Windows
```

---

## Local Setup

Clone the repository:

```bash
git clone https://github.com/gbadedata/swiftdeploy.git
cd swiftdeploy
```

Create a virtual environment.

PowerShell:

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

### 6. Promote to canary

```powershell
python .\swiftdeploy promote canary
curl.exe -i http://127.0.0.1:8080/healthz
```

### 7. Promote back to stable

```powershell
python .\swiftdeploy promote stable
curl.exe -i http://127.0.0.1:8080/healthz
```

### 8. View Nginx logs

```powershell
docker logs swiftdeploy-nginx --tail 10
```

### 9. Clean up

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

Expected result: response delay of about two seconds.

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

The CLI implements the required five validation checks.

### 1. Manifest exists and is valid YAML

The CLI fails if `manifest.yaml` is missing or invalid.

### 2. Required fields are present and non-empty

Required fields include:

```text
services.image
services.port
services.mode
services.version
services.restart_policy
nginx.image
nginx.port
nginx.proxy_timeout
nginx.contact
network.name
network.driver_type
logs.volume_name
```

### 3. Docker image exists locally

The CLI checks the image with Docker before deployment.

### 4. Nginx port is free

The CLI checks that the configured Nginx port is not already bound on the host.

### 5. Generated Nginx configuration is syntactically valid

The CLI validates `nginx.conf` using the Nginx container image.

The renderer explicitly writes generated files as UTF-8 without BOM to avoid Nginx syntax errors on Windows.

---

## Evidence and Screenshots

The `screenshots/` folder contains submission evidence.

| Screenshot | Purpose |
|---|---|
| `01_templates_docker_compose_tpl.png` | Shows Docker Compose template starts correctly |
| `02_templates_nginx_conf_tpl.png` | Shows Nginx template starts correctly and uses stdout/stderr logs |
| `03_init_generation.png` | Shows config generation from manifest |
| `04_validate_all_pass.png` | Shows all validation checks passing |
| `05_deploy_success.png` | Shows successful stable deployment |
| `06_root_endpoint_response.png` | Shows root endpoint response |
| `07_canary_and_headers.png` | Shows canary promotion and required headers |
| `08_nginx_logs_clean.png` | Shows structured Nginx access logs |

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

### Nginx reports `unknown directive ï»¿events`

This means a UTF-8 BOM was written at the start of `nginx.conf`.

SwiftDeploy avoids this by rendering output with byte-level UTF-8 encoding in the CLI. Do not manually rewrite `nginx.conf`; regenerate it:

```powershell
python .\swiftdeploy teardown --clean
python .\swiftdeploy init
```

---

### Inline JSON fails in PowerShell

Use JSON files and `--data-binary` rather than inline escaped JSON.

---

### Generated files are missing

Run:

```powershell
python .\swiftdeploy init
```

Generated files are intentionally excluded from Git and can always be recreated.

---

## Design Decisions

### Manifest as source of truth

The manifest defines deployment intent. Generated files are artifacts, not source files. This allows deterministic regeneration and reduces manual drift.

### Templates instead of handwritten configs

Templates make the relationship between manifest values and generated runtime files explicit. This is closer to real-world infrastructure tooling such as Helm, Terraform templating, and deployment generators.

### App and Nginx separated

The app owns business behaviour. Nginx owns ingress, headers, error formatting, timeouts, and access logging.

### Single app worker

The app uses one Gunicorn worker to keep chaos state deterministic during local testing. With multiple workers, in-memory chaos state could be updated in one worker while requests are served by another, causing inconsistent behaviour.

### Generated files excluded from Git

`docker-compose.yml` and `nginx.conf` are excluded because the grader should be able to delete and regenerate them using `swiftdeploy init`.

### Non-root and least privilege

Containers run as non-root users, drop capabilities, and disable privilege escalation. This reflects container hardening best practices.

---

## Cleanup

Stop the stack and remove generated files:

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

Regenerate:

```powershell
python .\swiftdeploy init
```

---

## Final Notes

SwiftDeploy is intentionally local-first. The task does not require AWS or domain deployment, so the implementation avoids unnecessary cloud dependencies and keeps the grading path reproducible on any Docker-enabled machine.

The key grading condition is preserved:

```text
manifest.yaml is the single source of truth
```

The stack can be destroyed, generated files can be removed, and the complete runtime configuration can be recreated by running:

```powershell
python .\swiftdeploy init
```
