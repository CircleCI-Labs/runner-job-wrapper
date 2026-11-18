---
title: Ship with Grafana Alloy
weight: 2
---

[`examples/alloy/config.alloy`](https://github.com/CircleCI-Labs/runner-job-wrapper/blob/main/examples/alloy/config.alloy) ships the wrapper events, the optional task-agent journal lines and host metrics to any OTLP/HTTP endpoint. It is tested with Grafana Cloud. The [end-to-end guide]({{< relref "/docs/get-started/set-up-end-to-end.md#5-install-and-configure-the-shipper" >}}) walks through the install. Its blocks:

1. **File tail to Loki over OTLP.** `local.file_match` and `loki.source.file` tail `jobs.jsonl`. `loki.process` promotes `event`, `resource_class`, `runner` and `instance_id` to labels. Job and workflow IDs stay in the JSON body, queried with `| json`. `otelcol.receiver.loki` and `otelcol.processor.transform` turn the stream into OTLP logs named `circleci-job-wrapper`.
2. **Journal pipeline (optional, experimental).** `loki.source.journal` reads the runner units' journal. The task agent writes JSON lines there. `loki.process` keeps only `Runner started execution`, `step start`, `step end` and `Reporting task end.` (each has a `job-id`) and labels them `event=task_start|step_start|step_end|task_end`, `log_type=task_agent` and `instance_id`. This gives near-real-time step progress and the job result per host. It is an internal format and may change between runner versions. Edit `matches` to list your runner units.
3. **Host metrics.** `prometheus.exporter.unix` with its `textfile` collector pointed at `CCI_JOBLOG_PROM_DIR`, scraped every 15 s into `otelcol.receiver.prometheus`.
4. **Per-job CPU and memory (cAdvisor).** `prometheus.exporter.cadvisor` reads cgroup CPU, memory and disk IO. `prometheus.relabel` keeps only the `/system.slice/circleci-runner*.service` cgroups and a few series, and copies the cgroup into a `cgroup` label. Each runner agent runs one job at a time, so this is per-job usage. Join it with the wrapper's `cgroup` field.
5. **EC2 identity.** `otelcol.processor.resourcedetection` with the `ec2` and `system` detectors sets `host.id` (the instance ID) on logs and metrics.
6. **`instance_id` on metrics.** `otelcol.processor.transform "metrics"` copies `host.id` into an `instance_id` datapoint attribute, so metrics join with the wrapper's `instance_id`.
7. **Export.** `otelcol.exporter.otlphttp` with `otelcol.auth.basic`.

## Environment

For example in `/etc/default/alloy`:

| Variable | Meaning |
|---|---|
| `OTLP_ENDPOINT` | OTLP/HTTP base URL. For Grafana Cloud, the stack's region gateway, `https://otlp-gateway-<region>.grafana.net/otlp` |
| `OTLP_USERNAME` | Grafana Cloud instance (stack) ID |
| `OTLP_PASSWORD` | Access token with write scope. Never commit it |
| `EC2_INSTANCE_ID` | This host's instance ID, used for the journal lines. Write it at install time from IMDSv2 (`/latest/meta-data/instance-id`) |

## Permissions

The `alloy` user needs read access to `jobs.jsonl`: add it to the runner's group. The journal pipeline also needs membership of `systemd-journal`. The textfile directory must be readable by `alloy` too.

## CircleCI spans to Grafana

Send CircleCI's OpenTelemetry spans to the same stack with CircleCI's exporter API (`POST /api/v2/otel/exporters`):

- Endpoint: the gateway URL above with `/v1/traces` appended.
- Protocol: `http`.
- Header: `Authorization: Basic <base64(stackid:token)>`.

The spans then land in Tempo, with `com.circleci.job.id` matching the wrapper's `job_id`.
