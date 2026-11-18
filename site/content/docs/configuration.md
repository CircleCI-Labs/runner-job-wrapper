---
title: Configuration
weight: 3
---

All settings are environment variables of the runner process. They reach the wrapper because the runner passes its environment on. Five of them can also be `KEY=value` lines in the operator file (`CCI_JOBLOG_CONF`), marked *file* below. The file supplies defaults and the environment wins.

| Variable | Default | Meaning |
|---|---|---|
| `CCI_JOBLOG_FILE` | `/var/log/circleci-job-wrapper/jobs.jsonl` | JSONL output file. The directory is created if missing. Skipped silently if unwritable |
| `CCI_JOBLOG_STATE_DIR` | `/run/circleci-job-wrapper` | Directory for the `<runner>.json` current-job files |
| `CCI_JOBLOG_STATE_ON_END` | `remove` | `remove` deletes the state file at job end. `idle` rewrites it as `{"state":"idle",...}` |
| `CCI_JOBLOG_HOST_CACHE` | `/run/circleci-job-wrapper/host.env` | Host identity cache (`key=value`) |
| `CCI_JOBLOG_CONF` | `/etc/circleci-job-wrapper/wrapper.env` | Operator file. Parsed, never sourced |
| `CCI_JOBLOG_IMDS_URL` | `http://169.254.169.254` | Metadata endpoint. Override for tests |
| `CCI_RUNNER_CONFIG` | the parent's `--config`, else `/etc/circleci-runner/circleci-runner-config.yaml` | Runner config to read `runner.name` from |
| `CCI_RUNNER_NAME` | from the runner config | Runner name. Wins over the config file (*file*) |
| `CCI_RESOURCE_CLASS` | empty | Resource class (*file*) |
| `CCI_JOBLOG_EXTRA_FIELDS` | empty | `k=v,k=v`, merged into every event as strings (*file*). Reserved names and keys containing `token`, `secret`, `passw`, `credential`, `auth` or `apikey` are skipped. 128 bytes per value |
| `CCI_JOBLOG_APP_URL` | `https://app.circleci.com` | Base for `workflow_url` and `pipeline_url`. Set it for CircleCI Server |
| `CCI_JOBLOG_PROM_DIR` | empty (off) | Write `<dir>/<runner>.prom`, a Prometheus textfile with the [busy gauge](#busy-gauge) (*file*) |
| `CCI_JOBLOG_PROM_JOB_ID` | empty | `1` adds `job_id` and `workflow_id` labels to the busy gauge (*file*). One series per job: fine for small fleets, high cardinality otherwise |
| `CCI_JOBLOG_HTTP_URL` | empty (off) | POST every event here, in the background, with `--max-time 2` |
| `CCI_JOBLOG_HTTP_HEADER` | empty | One extra header, for example `Authorization: Bearer ...`. Passed to curl on stdin, so it is not visible in `ps` |
| `CCI_JOBLOG_FORWARD_SIGNALS` | `1` | `0` stops the wrapper forwarding `TERM`, `INT` and `HUP` to the agent |
| `CCI_JOBLOG_DISABLE` | empty | Non-empty: `exec` the agent directly, with no telemetry. A kill switch |
| `CCI_JOBLOG_DEBUG` | empty | Non-empty: diagnostics on stderr. Never secrets, never agent arguments |

## Runner name

The wrapper uses the first of these:

1. `CCI_RUNNER_NAME`, or the operator file.
2. The `name:` key directly under the top-level `runner:` key of the runner config. The config is `CCI_RUNNER_CONFIG`, else the `--config <file>` argument of the parent runner process, else `/etc/circleci-runner/circleci-runner-config.yaml`.

A tiny parser extracts only that one value. The `api:` and auth token lines are never stored, logged or used. With no name, the state file is called `pid-<runner pid>.json`.

## Resource class

The runner config does not contain the resource class (the token maps to it), and the runner passes none in the job environment. Set it in the operator file:

```sh
# /etc/circleci-job-wrapper/wrapper.env   (one file per host; not sourced)
CCI_RESOURCE_CLASS=my-org/linux-large
CCI_JOBLOG_EXTRA_FIELDS=team=infra,pool=bazel
```

With several runners of different resource classes on one host, set `CCI_RESOURCE_CLASS` and `CCI_RUNNER_NAME` in each runner's service environment instead. `resolve_runner_and_class` in the script has a marked `HOOK` for reading the class from a `CIRCLE_*` variable, should a future runner provide one.

## Busy gauge

With `CCI_JOBLOG_PROM_DIR` set, the wrapper also writes `<dir>/<runner>.prom`, a Prometheus textfile:

```text
circleci_runner_busy{runner,resource_class,instance_id[,job_name,project,job_id,workflow_id]} 1|0
circleci_runner_job_start_time_seconds{...}      # only while busy
```

`job_name` and `project` are present while busy. `CCI_JOBLOG_PROM_JOB_ID=1` adds `job_id` and `workflow_id`, one series per job, so use it on small fleets only. Read the file with Alloy's `prometheus.exporter.unix` textfile collector or node_exporter's `--collector.textfile.directory`.

## State file

`<CCI_JOBLOG_STATE_DIR>/<runner-name-or-pid>.json` (name sanitised to `[A-Za-z0-9._-]`) is written atomically (temp file and `mv`) at job start and removed at job end. It has the same fields as `job_start`, plus `"state":"running"` and `"updated_at"`.

A wrapper that is `SIGKILL`ed cannot clean up, so treat a file whose `wrapper_pid` is no longer alive as stale. `/run` is tmpfs, so stale files vanish at reboot.

## Logrotate

`logrotate/circleci-job-wrapper` rotates daily, keeps 7 compressed files and uses `copytruncate`. The wrapper opens the file with `O_APPEND` for every event, so truncating in place is safe for any number of concurrent appenders. At worst, the lines written between logrotate's copy and truncate are lost.

`create` would hand the new file to root and silently stop every runner account from logging, because the wrapper never fails a job over logging. For lossless rotation, use `create 0664 <runner-user> <runner-group>` instead.
