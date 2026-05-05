package swiftdeploy.canary

default allow := false

error_rate_ok if {
    input.metrics.error_rate <= input.limits.max_error_rate
}

p99_latency_ok if {
    input.metrics.p99_latency_ms <= input.limits.max_p99_latency_ms
}

allow if {
    input.context == "pre_promote"
    error_rate_ok
    p99_latency_ok
}

error_rate_reason := msg if {
    not error_rate_ok
    msg := sprintf(
        "Error rate %.4f exceeds allowed maximum %.4f",
        [input.metrics.error_rate, input.limits.max_error_rate],
    )
}

latency_reason := msg if {
    not p99_latency_ok
    msg := sprintf(
        "P99 latency %.2fms exceeds allowed maximum %.2fms",
        [input.metrics.p99_latency_ms, input.limits.max_p99_latency_ms],
    )
}

reasons contains error_rate_reason if {
    not error_rate_ok
}

reasons contains latency_reason if {
    not p99_latency_ok
}

reasons contains "Canary safety policy passed" if {
    allow
}

decision := {
    "domain": "canary",
    "question": "pre_promote",
    "allow": allow,
    "reasons": reasons,
}
