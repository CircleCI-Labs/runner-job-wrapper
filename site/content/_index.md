---
title: CircleCI runner job wrapper
---

## What you need

Only the first group is required. The wrapper works with nothing else.

| | What | Notes |
|---|---|---|
| **Required** | The wrapper script `bin/circleci-job-wrapper` and a `command_prefix` entry in the runner config | Machine runner 3.1.11 or later, on Linux |
| **Required** | A log directory the runner user can write | Default `/var/log/circleci-job-wrapper` |
| **Recommended** | The boot-time host cache systemd unit | Gives every job its EC2 identity without a metadata call per job. IMDS must be enabled, and IMDSv2 works |
| **Recommended** | The logrotate config | Rotates `jobs.jsonl` daily |
| **Recommended** | The operator file `/etc/circleci-job-wrapper/wrapper.env` with `CCI_RESOURCE_CLASS` | The runner does not tell the wrapper its resource class |
| **Optional** | CircleCI org OpenTelemetry export | Spans for job and step timing and the job result. The wrapper adds the host |
| **Optional** | Prometheus busy gauge (`CCI_JOBLOG_PROM_DIR`) | A live busy or idle view per runner |
| **Optional** | HTTP sink (`CCI_JOBLOG_HTTP_URL`) | POST every event to an endpoint |
| **Optional** | A shipper: the Grafana Alloy example, the Datadog Agent, Vector, Fluent Bit and others | Moves `jobs.jsonl` to your backend |
| **Optional, experimental** | The task-agent journal pipeline | Live step progress and the job result per host. The internal log format may change |
| **Optional** | The example Grafana dashboard | Needs Alloy, Grafana Cloud or similar |

## What is tested

The project is pre-release (0.x). If a page claims more than this table shows, please open an issue.

| What | Status | How it is checked |
|---|---|---|
| Wrapper core | Tested | A real machine runner 3.1.14 on an Ubuntu 24.04 EC2 host with two runner agents. 62 bats tests, shellcheck clean |
| Grafana Alloy example | Tested | Shipped to Grafana Cloud |
| Example Grafana dashboard | Tested | Built from the Alloy data above |
| Task-agent journal pipeline | Experimental | Works today. It reads an internal log format that may change between runner versions |
| Datadog Agent | Documented, not tested | The steps follow Datadog's documentation |
| CircleCI Server, Windows, macOS, container runner | Not tested, not supported | Machine runner on Linux only |
