---
title: Set it up end to end
weight: 1
---

This guide takes you from nothing to a dashboard where you pick a CircleCI job and see its trace, its steps, the host it ran on and the CPU it used. Do the stages in order. Each ends with a check, so you know it worked before you go on.

Stages 1 to 3 are the wrapper alone, and are enough to get host identity on every job. Stages 4 to 7 add CircleCI spans, a shipper and the dashboards.

```text
 runner --command_prefix--> wrapper --> jobs.jsonl --> Alloy --> Grafana Cloud (Loki, Mimir)
 CircleCI OpenTelemetry export (org level) -----------------> Grafana Cloud (Tempo)
 host and cgroup metrics ------> Alloy ---------------------> Grafana Cloud (Mimir)
```

{{< callout type="warning" >}}
This is a CircleCI Labs project, not an official CircleCI product. Pages mark what is tested and what is not.
{{< /callout >}}

## 1. Prerequisites

- A CircleCI **machine runner 3.1.11 or later on Linux**. Tested with 3.1.14 on Ubuntu 24.04.
- **Organization admin** rights in CircleCI, to add an OpenTelemetry exporter (stage 4).
- On EC2, the **instance metadata service (IMDS) enabled**. IMDSv2 works. Off EC2 the EC2 fields stay empty and nothing else changes.
- `bash` 4 or later, `curl`, and shell access with `sudo` to the runner host.
- For stages 4 to 7: a Grafana Cloud stack (or another OTLP backend) and a Grafana access token.

Check it worked:

```sh
systemctl status circleci-runner --no-pager | head -5
TOKEN=$(curl -s -X PUT -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' http://169.254.169.254/latest/api/token)
curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id
```

Expected: the runner is active, and the last command prints an instance ID such as `i-0123456789abcdef0`.

## 2. Install the wrapper

On every host that runs a runner agent, from a checkout of this repository. Replace `circleci` with the account and group your runner runs as.

```sh
# the wrapper
sudo install -m 0755 bin/circleci-job-wrapper /usr/local/bin/circleci-job-wrapper
sudo install -d -m 0775 -o root -g circleci /var/log/circleci-job-wrapper

# boot-time host cache (EC2 identity without a metadata call per job)
sudo install -m 0644 systemd/circleci-job-wrapper-hostcache.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now circleci-job-wrapper-hostcache.service

# daily log rotation
sudo install -m 0644 logrotate/circleci-job-wrapper /etc/logrotate.d/circleci-job-wrapper

# operator file: parsed, never sourced
sudo install -d /etc/circleci-job-wrapper
sudo tee /etc/circleci-job-wrapper/wrapper.env >/dev/null <<'ENV'
CCI_RESOURCE_CLASS=my-org/linux-large
CCI_JOBLOG_PROM_DIR=/run/circleci-job-wrapper/prom
CCI_JOBLOG_PROM_JOB_ID=1
ENV
```

- `CCI_RESOURCE_CLASS` is your resource class. The runner does not tell the wrapper, so set it here.
- `CCI_JOBLOG_PROM_DIR` turns on the Prometheus busy gauge (a live busy or idle view per runner). Optional, but the fleet dashboard uses it.
- `CCI_JOBLOG_PROM_JOB_ID=1` adds `job_id` and `workflow_id` labels to the gauge, one series per job. Fine for small fleets. Optional.

Check it worked:

```sh
systemctl is-active circleci-job-wrapper-hostcache.service
grep instance_id /run/circleci-job-wrapper/host.env
bash -n /usr/local/bin/circleci-job-wrapper && echo ok
```

Expected: `active`, an `instance_id=` line, and `ok`.

More detail: [Install](../install/), [Configuration](../configuration/).

## 3. Configure the runner

Add the prefix to `/etc/circleci-runner/circleci-runner-config.yaml`:

```yaml
runner:
  command_prefix: ["/usr/local/bin/circleci-job-wrapper"]
```

Restart the runner, then run any job on it.

```sh
sudo systemctl restart circleci-runner
tail -n2 /var/log/circleci-job-wrapper/jobs.jsonl | jq -c '{event,job_id,trace_id,runner_name,instance_id,resource_class,agent_status}'
```

Expected: a `job_start` and a `job_end` line for your job, with your instance ID and resource class.

Check it worked: both events are present and `job_id` is a UUID. If the file is empty, see [Troubleshooting](../troubleshooting/).

## 4. Turn on CircleCI's OpenTelemetry export

The wrapper knows the host. CircleCI knows the job result, the steps and their timing. You get those as OpenTelemetry spans, from an exporter you add once per organization. It needs organization admin rights, and CircleCI supports up to 5 exporters per organization. Spans are sent when each job finishes.

If your collector restricts source IPs, allow CircleCI's core IPs. List them with `dig core.knownips.circleci.com`. Grafana Cloud needs no allow-list.

Official documentation: [OpenTelemetry integration](https://circleci.com/docs/guides/integration/open-telemetry-integration/) and the [API reference](https://circleci.com/docs/api/v2/#tag/OTel).

### Grafana Cloud values

| Setting | Value |
|---|---|
| Endpoint | `https://otlp-gateway-<region>.grafana.net/otlp/v1/traces` |
| Protocol | `http` |
| Header | `Authorization: Basic <base64 of instance-id:token>` |

Build the header value with `printf '%s' '<instance-id>:<token>' | base64 -w0`.

{{< callout type="info" >}}
`<region>` is the region of your **stack**. Take it from your data source URLs or from the OTLP tile of your stack. It is not necessarily the region embedded in the token.
{{< /callout >}}

### Option A: the CircleCI UI

1. Open **Organization settings**, then **OpenTelemetry Configuration**.
2. Choose **Add exporter**.
3. Pick the protocol (`http`), enter the endpoint, and add the header.
4. Save.

### Option B: the API

Use an organization admin personal API token.

```sh
curl -sS -X POST https://circleci.com/api/v2/otel/exporters \
  -H "Circle-Token: $CIRCLECI_TOKEN" -H 'Content-Type: application/json' \
  -d '{
    "org_id": "<your-org-id>",
    "endpoint": "https://otlp-gateway-<region>.grafana.net/otlp/v1/traces",
    "protocol": "http",
    "headers": {"Authorization": "Basic <base64 of instance-id:token>"}
  }'
```

### Datadog and other OTLP backends

Any backend that takes OTLP over HTTP works the same way: use its OTLP traces endpoint, protocol `http`, and the header it documents for authentication. For Datadog, that means an Agent or Collector that accepts OTLP, with its API key header. This is not tested here.

### What spans you get

| Span | What it covers |
|---|---|
| pipeline | The pipeline run |
| workflow | One workflow of the pipeline |
| job | One job |
| task | The task that executes the job |
| step | One step, named `Step: <name>`, with its duration and `com.circleci.task.result` |

Attributes you will use:

- `com.circleci.job.id`: equals the wrapper's `job_id`. This is the join key.
- `com.circleci.job.status`: the job result.
- `com.circleci.resource.class`: the resource class.
- `vcs.ref.head.name`: the branch.
- The **trace ID** is the pipeline ID without dashes. It equals the wrapper's `trace_id`.

The spans carry **no CPU or memory and no host identity**. The wrapper adds the host and the job's CPU time, and the shipper in stage 5 adds host and cgroup metrics.

Check it worked: run a job, wait for it to finish, then in Grafana open **Explore**, pick your Tempo data source and run this TraceQL query:

```text
{ span.com.circleci.job.id != "" }
```

Expected: spans for your job. If nothing shows, re-check the region and the header, and the exporter list in **OpenTelemetry Configuration**.

## 5. Install and configure the shipper

The shipper moves `jobs.jsonl`, host metrics and per-job CPU and memory to your backend. This guide uses Grafana Alloy, the tested example. The Datadog Agent is [documented but not tested](../ship-with-datadog/).

Install Alloy by following Grafana's instructions, then:

```sh
# env file of the alloy service, for example /etc/default/alloy
sudo tee -a /etc/default/alloy >/dev/null <<'ENV'
OTLP_ENDPOINT=https://otlp-gateway-<region>.grafana.net/otlp
OTLP_USERNAME=<instance-id>
OTLP_PASSWORD=<access-token>
EC2_INSTANCE_ID=<this host's instance id>
ENV
sudo chmod 0640 /etc/default/alloy

# let alloy read the log, the textfile directory and the journal
sudo usermod -aG circleci,systemd-journal alloy

sudo install -m 0644 examples/alloy/config.alloy /etc/alloy/config.alloy
sudo systemctl restart alloy
```

Replace `circleci` with the runner's group. The endpoint here has no `/v1/traces`: Alloy exports logs and metrics, not traces. Never commit the token.

What each block of `examples/alloy/config.alloy` does:

1. **Wrapper events.** Tails `jobs.jsonl`, promotes `event`, `resource_class`, `runner` and `instance_id` to labels and sends the lines as OTLP logs.
2. **Task-agent journal (optional, experimental).** Keeps four log messages from the runner units for live step progress and the host-side job result.
3. **Host metrics.** `prometheus.exporter.unix` for CPU, memory, disk and network, plus the busy gauge textfile.
4. **cAdvisor block.** `prometheus.exporter.cadvisor` reads cgroup CPU and memory. A relabel rule keeps only the `/system.slice/circleci-runner*.service` cgroups and a few series. Each runner agent runs one job at a time, so its service cgroup is per-job CPU and memory over time. The wrapper's `cgroup` field joins to it.
5. **EC2 identity.** `resourcedetection` sets `host.id`, and a transform copies it into an `instance_id` attribute on metrics.
6. **Export.** OTLP over HTTP with basic auth.

Check it worked:

```sh
sudo systemctl is-active alloy
sudo journalctl -u alloy -n 20 --no-pager | grep -i error || echo "no errors"
```

Then in Grafana **Explore**, Loki: `{service_name="circleci-job-wrapper"}` shows job events. In Prometheus, `circleci_runner_busy` and `container_cpu_usage_seconds_total{cgroup=~"/system.slice/circleci-runner.*"}` return series.

More detail: [Ship with Grafana Alloy](../ship-with-alloy/).

## 6. Import the dashboards

Generate the dashboard JSON with the UIDs of your data sources. Find them under **Connections, Data sources** (the UID is in the URL).

```sh
python3 examples/grafana/build_dashboard.py --prom <prom-uid> --loki <loki-uid> --tempo <tempo-uid> > dashboard.json
python3 examples/grafana/build_job_dashboard.py --prom <prom-uid> --loki <loki-uid> --tempo <tempo-uid> > job-dashboard.json
```

For CircleCI Server add `--app-url https://<your-circleci-host>` so links open your installation.

Import them either way:

- **UI:** Dashboards, New, Import, upload each JSON file.
- **API:**

  ```sh
  jq -n --slurpfile d dashboard.json '{dashboard: $d[0], overwrite: true}' |
    curl -sS -X POST "$GRAFANA_URL/api/dashboards/db" \
      -H "Authorization: Bearer $GRAFANA_TOKEN" -H 'Content-Type: application/json' -d @-
  ```

  Repeat for `job-dashboard.json`.

More dashboards, such as runner detail and resource class detail, are being added. See the [dashboards page](../example-dashboard/) for the current list.

Check it worked: the **CircleCI runner fleet** dashboard opens, and "Fleet right now" shows your runners.

## 7. Verify the join

1. On the fleet dashboard, open **Recent jobs** and pick a job.
2. Click **Drill into this job**. The job-detail dashboard opens, already filtered to that job.
3. Confirm you see:
   - **Where and when it ran**: the instance, runner, resource class and cgroup, from the wrapper.
   - **The trace**: pipeline, workflow, job and steps, from CircleCI spans.
   - **Steps, slowest first**.
   - **Resources used during this job**: CPU and memory of the runner's cgroup, the job's CPU time, and host metrics.

If the trace panel is empty, the span export (stage 4) is the usual cause: check the exporter, then that `trace_id` in the wrapper event equals the trace ID in Tempo. If the CPU panels are empty, check the cAdvisor block and the `cgroup` value in the event.

You now have the full setup. [Example Grafana dashboards](../example-dashboard/) describes every panel, and [Troubleshooting](../troubleshooting/) covers the common failures.
