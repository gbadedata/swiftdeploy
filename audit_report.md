# SwiftDeploy Audit Report

Generated: `2026-05-07T00:38:28.722510+00:00`

## Summary

- Total audit events: `6`
- Mode/deploy events: `3`
- Policy violations: `2`

## Timeline

| Timestamp | Event | Summary |
|---|---|---|
| 2026-05-06T23:40:04.560440+00:00 | deploy | `{"mode": "stable", "version": "1.0.0"}` |
| 2026-05-06T23:40:46.121884+00:00 | mode_change | `{"mode": "canary", "health": {"mode": "canary", "status": "ok", "timestamp": "2026-05-06T23:40:45.997349+00:00", "uptime_seconds": 1.45, "version": "1.0.0"}}` |
| 2026-05-06T23:45:32.772920+00:00 | mode_change | `{"mode": "stable", "health": {"mode": "stable", "status": "ok", "timestamp": "2026-05-06T23:45:32.839670+00:00", "uptime_seconds": 1.39, "version": "1.0.0"}}` |

## Policy Violations

| Timestamp | Domain | Question | Reasons |
|---|---|---|---|
| 2026-05-06T23:42:53.521557+00:00 | canary | pre_promote | Error rate 0.380952 exceeds allowed maximum 0.01 |
| 2026-05-06T23:43:18.211802+00:00 | canary | pre_promote | Error rate 0.380952 exceeds allowed maximum 0.01 |

## Notes

This report is generated from `history.jsonl` by `swiftdeploy audit`.