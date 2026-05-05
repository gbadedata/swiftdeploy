package swiftdeploy.infrastructure

default allow := false

disk_ok if {
    input.stats.disk_free_gb >= input.limits.min_disk_free_gb
}

cpu_ok if {
    input.stats.cpu_load <= input.limits.max_cpu_load
}

allow if {
    input.context == "pre_deploy"
    disk_ok
    cpu_ok
}

disk_reason := msg if {
    not disk_ok
    msg := sprintf(
        "Disk free %vGB is below required minimum %vGB",
        [input.stats.disk_free_gb, input.limits.min_disk_free_gb],
    )
}

cpu_reason := msg if {
    not cpu_ok
    msg := sprintf(
        "CPU load %.2f exceeds allowed maximum %.2f",
        [input.stats.cpu_load, input.limits.max_cpu_load],
    )
}

reasons contains disk_reason if {
    not disk_ok
}

reasons contains cpu_reason if {
    not cpu_ok
}

reasons contains "Infrastructure policy passed" if {
    allow
}

decision := {
    "domain": "infrastructure",
    "question": "pre_deploy",
    "allow": allow,
    "reasons": reasons,
}
