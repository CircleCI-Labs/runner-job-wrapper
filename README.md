# circleci-job-wrapper

A small, dependency-free bash wrapper for the CircleCI **machine runner**
`command_prefix` setting. For every job it records what ran, where, and for how
long, as one JSON object per line (JSONL), and keeps a per-runner "what is this
runner doing right now" state file. It never changes the job: the task agent
runs as a normal child, stdin is untouched, and the exit status is returned
exactly.

* Output: `job_start` / `job_end` events appended to a JSONL file (primary
  contract), optionally POSTed to an HTTP endpoint.
* Host identity (EC2 instance id, type, AZ, region, private IP, AMI), runner
  name and resource class on every event. This is what CircleCI's own
  OpenTelemetry job spans lack: they carry no runner or host identity.
* Optional Prometheus textfile with a per-runner busy gauge.
* Best effort only: every logging failure is swallowed. No `jq`, no daemon, no
  Python; bash 4+ and POSIX utilities (`date`, `curl`, `mkdir`, `mv`, `rm`).
  Measured overhead is about 6 ms per job (the agent is spawned before any
  telemetry runs).
* Silent unless `CCI_JOBLOG_DEBUG` is set.

## How `command_prefix` invokes it

With

```yaml
runner:
  command_prefix: ["/usr/local/bin/circleci-job-wrapper"]
```

the runner executes

```
/usr/local/bin/circleci-job-wrapper <task-agent-path> <agent args...>
```

with the job's built-in environment (`CIRCLE_*`) added to the environment and
the task token on stdin. The wrapper:

1. starts the task agent as a child (`<&0`, so stdin is the very same pipe),
2. then, while the job already runs, resolves host identity and writes
   `job_start` plus the state file (start-up cost for the job is one `fork`),
3. waits for the child, forwarding `SIGTERM`/`SIGINT`/`SIGHUP` to it if the
   wrapper itself is signalled,
4. writes `job_end` (`agent_status` = `completed`, `agent_error`, or
   `cancelled` when a signal was received), removes the state file, and exits
   with the child's exit code (`128+n` for a signalled child).

Every helper command the wrapper runs has `</dev/null`, so it can never steal
the task token from the agent's stdin.

**`agent_status` is not the job result.** The task agent exits 0 even when the
job fails or is cancelled from the UI, so `completed` only means the agent
process exited 0. Take the job result from the CircleCI span
(`com.circleci.job.status`) or, on the host, from the task agent's own
"Reporting task end." log line (see [Shipping with Grafana
Alloy](#shipping-with-grafana-alloy)). `cancelled` only means the wrapper
received `TERM`/`INT`/`HUP`, for example because the runner is stopping a task.

### Signals

When the runner stops a task it sends `SIGTERM` to the `command_prefix`
process only (not the process group), and `SIGKILL` to the whole process group
after 10 s (immediately with `enable_unsafe_retries`). So:

* signal forwarding (default on) is required, otherwise the agent never sees
  the `SIGTERM`;
* if the agent has not exited within 10 s the wrapper is killed too and
  `job_end` is lost; consumers should tolerate a `job_start` without a
  `job_end`;
* a cancel from the CircleCI UI is handled by the agent itself (exit 0, no
  signal), so it shows as `completed`.

### Environment the runner provides

Verified on machine runner 3.1.14, these built-in variables reach the
`command_prefix` process (names only):

`CIRCLE_BRANCH` `CIRCLE_BUILD_NUM` `CIRCLE_BUILD_URL` `CIRCLE_JOB`
`CIRCLE_NODE_INDEX` `CIRCLE_NODE_TOTAL` `CIRCLE_ORGANIZATION_ID`
`CIRCLE_PIPELINE_ID` `CIRCLE_PROJECT_ID` `CIRCLE_PROJECT_REPONAME`
`CIRCLE_PROJECT_USERNAME` `CIRCLE_REPOSITORY_URL` `CIRCLE_SHA1`
`CIRCLE_USERNAME` `CIRCLE_WORKFLOW_ID` `CIRCLE_WORKFLOW_JOB_ID`
`CIRCLE_WORKFLOW_WORKSPACE_ID`

There is no resource class, no pipeline number and no PR number, so those event
fields stay empty unless you supply them (resource class: see [Resource
class](#resource-class)).

## Install

```sh
# 1. the wrapper
sudo install -m 0755 bin/circleci-job-wrapper /usr/local/bin/circleci-job-wrapper

# 2. directories (the runner user must be able to write both)
sudo install -d -m 0775 -o root -g circleci /var/log/circleci-job-wrapper
sudo install -d -m 1777 /run/circleci-job-wrapper        # or let systemd do it, see step 3

# 3. boot-time host identity cache (optional but recommended)
sudo install -m 0644 systemd/circleci-job-wrapper-hostcache.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now circleci-job-wrapper-hostcache.service

# 4. log rotation
sudo install -m 0644 logrotate/circleci-job-wrapper /etc/logrotate.d/circleci-job-wrapper

# 5. runner config (/etc/circleci-runner/circleci-runner-config.yaml), then restart the runner
#    runner:
#      command_prefix: ["/usr/local/bin/circleci-job-wrapper"]
```

Replace `circleci` with the account/group your runner service runs as. The
hostcache unit creates `/run/circleci-job-wrapper` (sticky, mode 1777, so that
runner accounts can write state files but cannot replace the root-owned
`host.env`) and `/var/log/circleci-job-wrapper` (0775, add a `Group=` in a
drop-in to match the runner group).

Several runner agents on one host share the same wrapper, log file and cache.
This was tested with two systemd units (`circleci-runner` and
`circleci-runner-b`), each with its own `-c` config file and `runner.name`: the
wrapper reads the name from the parent's `-c`/`--config` argument, so nothing
more is needed, and events from both interleave safely. Set `CCI_RUNNER_NAME`
in a unit's environment only to override that; see [Runner name](#runner-name).

Run the tests with `make check` (shellcheck + bats; needs `bats`, `jq`,
`python3`, `curl`; `strace` and `iconv` are used when present).

## Configuration

All settings are environment variables of the runner process (they reach the
wrapper because the runner passes its environment on), or `KEY=value` lines in
the operator file (`CCI_JOBLOG_CONF`, only for the five keys marked *file*,
which supplies defaults). The environment wins over the file.

| Variable | Default | Meaning |
|---|---|---|
| `CCI_JOBLOG_FILE` | `/var/log/circleci-job-wrapper/jobs.jsonl` | JSONL output file; directory is created if missing; skipped silently if unwritable |
| `CCI_JOBLOG_STATE_DIR` | `/run/circleci-job-wrapper` | Directory for `<runner>.json` current-job files |
| `CCI_JOBLOG_STATE_ON_END` | `remove` | `remove` deletes the state file at job end; `idle` rewrites it as `{"state":"idle",...}` |
| `CCI_JOBLOG_HOST_CACHE` | `/run/circleci-job-wrapper/host.env` | Host identity cache (`key=value`) |
| `CCI_JOBLOG_CONF` | `/etc/circleci-job-wrapper/wrapper.env` | Operator file (`CCI_RESOURCE_CLASS`, `CCI_RUNNER_NAME`, `CCI_JOBLOG_EXTRA_FIELDS`, `CCI_JOBLOG_PROM_DIR`, `CCI_JOBLOG_PROM_JOB_ID`). Parsed, never sourced |
| `CCI_JOBLOG_IMDS_URL` | `http://169.254.169.254` | Metadata endpoint (override for tests) |
| `CCI_RUNNER_CONFIG` | parent's `--config`, else `/etc/circleci-runner/circleci-runner-config.yaml` | Runner config to read `runner.name` from |
| `CCI_RUNNER_NAME` | from runner config | Runner name; wins over the config file (*file*) |
| `CCI_RESOURCE_CLASS` | empty | Resource class (*file*) |
| `CCI_JOBLOG_EXTRA_FIELDS` | empty | `k=v,k=v`, merged into every event as strings (*file*). Reserved names and keys containing `token`, `secret`, `passw`, `credential`, `auth`, `apikey` are skipped; 128 bytes per value |
| `CCI_JOBLOG_APP_URL` | `https://app.circleci.com` | Base for `workflow_url` and `pipeline_url`; set it for CircleCI Server |
| `CCI_JOBLOG_PROM_DIR` | empty (off) | Write `<dir>/<runner>.prom`, a Prometheus textfile with the busy gauge (*file*); see [Busy gauge](#busy-gauge) |
| `CCI_JOBLOG_PROM_JOB_ID` | empty | `1` adds a `job_id` label to the busy gauge (*file*). One series per job: fine for small fleets, high cardinality otherwise |
| `CCI_JOBLOG_HTTP_URL` | empty (off) | POST every event here (background, `--max-time 2`) |
| `CCI_JOBLOG_HTTP_HEADER` | empty | One extra header, e.g. `Authorization: Bearer ...` (passed to curl on stdin, not visible in `ps`) |
| `CCI_JOBLOG_FORWARD_SIGNALS` | `1` | `0` stops the wrapper forwarding `TERM`/`INT`/`HUP` to the agent |
| `CCI_JOBLOG_DISABLE` | empty | Non-empty: `exec` the agent directly, no telemetry (kill switch) |
| `CCI_JOBLOG_DEBUG` | empty | Non-empty: diagnostics on stderr (never secrets, never agent arguments) |

### Runner name

In order: `CCI_RUNNER_NAME`; the operator file; the `name:` key directly under
the top-level `runner:` key of the runner config (`CCI_RUNNER_CONFIG`, else the
`--config <file>` argument of the parent runner process, else
`/etc/circleci-runner/circleci-runner-config.yaml`). The config is scanned with
a tiny parser that only extracts that one value; the file's `api:` /
auth-token lines are never stored, logged, or used. With no name the state file
is called `pid-<runner pid>.json`.

### Resource class

The runner config does not contain the resource class (the token maps to it),
so the wrapper takes it from `CCI_RESOURCE_CLASS`, or the operator file:

```sh
# /etc/circleci-job-wrapper/wrapper.env   (one file per host; not sourced)
CCI_RESOURCE_CLASS=my-org/linux-large
CCI_JOBLOG_EXTRA_FIELDS=team=infra,pool=bazel
```

With several runners of different resource classes on one host, set
`CCI_RESOURCE_CLASS` and `CCI_RUNNER_NAME` in each runner's service
environment instead. The runner passes no resource class in the job
environment (see above); `resolve_runner_and_class` in the script has a marked
`HOOK` for reading it from a `CIRCLE_*` variable should a future runner
provide one.

## Event schema (version 1)

One JSON object per line, UTF-8, each written with a single append (lines are
well under 4 KiB, so concurrent appends from many runner agents do not
interleave). All identifiers are strings, and a missing value is `""`, so every
line has the same keys. `job_end` additionally has `agent_exit_code`,
`duration_ms`, `start_ms`, `end_ms` and `agent_status`.

| Field | Source |
|---|---|
| `schema` (number), `event`, `ts` | `job_start` or `job_end`; RFC 3339 UTC with milliseconds |
| `job_id` | `CIRCLE_WORKFLOW_JOB_ID` (fallback `CIRCLE_JOB_ID`). The join key: equals `com.circleci.job.id` on CircleCI's spans |
| `job_name`, `job_number` | `CIRCLE_JOB`, `CIRCLE_BUILD_NUM` |
| `workflow_id`, `pipeline_id` | `CIRCLE_WORKFLOW_ID`, `CIRCLE_PIPELINE_ID` |
| `pipeline_number` | `CIRCLE_PIPELINE_NUMBER`; not provided by the runner, normally empty |
| `workflow_url`, `pipeline_url` | `<base>/workflow/<workflow_id>`, `<base>/pipeline/<pipeline_id>`; base is `CCI_JOBLOG_APP_URL` |
| `project`, `org` | `CIRCLE_PROJECT_REPONAME`, `CIRCLE_PROJECT_USERNAME` |
| `org_id`, `project_id` | `CIRCLE_ORGANIZATION_ID`, `CIRCLE_PROJECT_ID` |
| `branch`, `sha`, `build_url`, `node_index` | `CIRCLE_BRANCH`, `CIRCLE_SHA1`, `CIRCLE_BUILD_URL` (the job link), `CIRCLE_NODE_INDEX` |
| `pr_number` | `CIRCLE_PR_NUMBER`; not provided by the runner, normally empty |
| `hostname` | the host's name |
| `instance_id`, `instance_type`, `availability_zone`, `region`, `private_ip`, `ami_id` | EC2 instance identity document (empty off EC2) |
| `runner_name`, `resource_class` | see above |
| `wrapper_pid`, `agent_pid` (numbers) | the wrapper and the task agent process |
| extra fields | `CCI_JOBLOG_EXTRA_FIELDS` |
| `agent_exit_code`, `duration_ms`, `start_ms`, `end_ms` (numbers; the last two are epoch ms), `agent_status` | `job_end` only. `agent_status`: `completed` (agent exit 0), `agent_error`, `cancelled` (the wrapper received TERM/INT/HUP). Describes the agent process, not the job result (see above) |

Only the variables listed here are ever read: the environment is never dumped
and the agent's command line is never logged. The `CIRCLE_*` names are read
defensively; any that the runner does not provide are simply empty.

```json
{"schema":1,"event":"job_start","ts":"2026-11-18T20:31:55.456Z","job_id":"5b1e0c1a-0000-4000-8000-000000000001","job_name":"build","job_number":"1234","workflow_id":"7f3d0000-0000-4000-8000-000000000002","workflow_url":"https://app.circleci.com/workflow/7f3d0000-0000-4000-8000-000000000002","pipeline_id":"a1b20000-0000-4000-8000-000000000003","pipeline_url":"https://app.circleci.com/pipeline/a1b20000-0000-4000-8000-000000000003","pipeline_number":"","project":"example-repo","org":"example-org","org_id":"c0de0000-0000-4000-8000-000000000004","project_id":"d00d0000-0000-4000-8000-000000000005","branch":"main","sha":"0123456789abcdef0123456789abcdef01234567","build_url":"https://app.circleci.com/jobs/1234","node_index":"0","pr_number":"","hostname":"ip-10-0-1-23","instance_id":"i-0123456789abcdef0","instance_type":"c7g.xlarge","availability_zone":"us-east-1b","region":"us-east-1","private_ip":"10.0.1.23","ami_id":"ami-0abc1234def567890","runner_name":"runner-1","resource_class":"example-org/linux-large","wrapper_pid":1656458,"agent_pid":1656459,"team":"infra","pool":"bazel"}
{"schema":1,"event":"job_end","ts":"2026-11-18T20:31:55.758Z","job_id":"5b1e0c1a-0000-4000-8000-000000000001","job_name":"build","...":"(same fields as job_start)","team":"infra","pool":"bazel","agent_exit_code":0,"duration_ms":302,"start_ms":1795033915456,"end_ms":1795033915758,"agent_status":"completed"}
```

(`"...":` above is only an abbreviation for this document; real lines repeat
all fields.)

### Busy gauge

With `CCI_JOBLOG_PROM_DIR` set (environment or operator file) the wrapper also
writes `<dir>/<runner>.prom`, a Prometheus textfile:

```
circleci_runner_busy{runner,resource_class,instance_id[,job_name,project,job_id]} 1|0
circleci_runner_job_start_time_seconds{...}      # only while busy
```

`job_name` and `project` are present while busy; `CCI_JOBLOG_PROM_JOB_ID=1` adds
`job_id` (one series per job, so use it on small fleets only). Read it with
Alloy's `prometheus.exporter.unix` textfile collector or node_exporter's
`--collector.textfile.directory`.

### State file

`<CCI_JOBLOG_STATE_DIR>/<runner-name-or-pid>.json` (name sanitised to
`[A-Za-z0-9._-]`) is written atomically (temp file + `mv`) at job start and
removed at job end. It has the same fields as `job_start` plus
`"state":"running"` and `"updated_at"`. A wrapper that is `SIGKILL`ed cannot
clean up, so a consumer should treat a file whose `wrapper_pid` is no longer
alive as stale. `/run` is tmpfs, so stale files vanish at reboot.

## EC2 metadata requirements

Instance identity comes from one request to the instance identity document
(`/latest/dynamic/instance-identity/document`).

* The **instance metadata service must be enabled** on the instance. On
  non-EC2 hosts (or with IMDS disabled) the EC2 fields are simply empty and
  nothing else changes.
* **IMDSv2 is recommended** (`HttpTokens=required`). The wrapper does
  `PUT /latest/api/token` first and falls back to IMDSv1 only if that fails,
  so it works either way. Timeouts are 0.3 s connect / 1 s total per request
  and proxies are bypassed.
* A **hop limit of 1** is fine for jobs running on the host: the wrapper runs
  on the host itself. A hop limit of **2** is only needed if the jobs
  themselves (for example containers started by the job) query IMDS.
* **Instance metadata tags** (`InstanceMetadataTags=enabled`) are optional and
  not read by the wrapper. To put tags such as `Team` on every event, read
  them once at boot (`/latest/meta-data/tags/instance/<key>`) and write them to
  `CCI_JOBLOG_EXTRA_FIELDS` in the operator file.
* Identity is cached in `CCI_JOBLOG_HOST_CACHE` (tmpfs by default) together
  with the kernel boot id, so a cache that survives in an image or a new boot
  is ignored. The boot-time unit
  (`circleci-job-wrapper --refresh-host-cache`, 3 attempts) fills it, so no job
  ever queries IMDS. Without the unit, the first job on each boot fills it
  (while it runs, never delaying its start); if the cache cannot be written
  each job queries IMDS itself. A negative result (not on EC2) is cached for
  300 s.

## Logrotate

`logrotate/circleci-job-wrapper` rotates daily, keeps 7 compressed files and
uses `copytruncate`. The wrapper opens the file with `O_APPEND` per event, so
truncating in place is safe for any number of concurrent appenders; at worst
the lines written between logrotate's copy and truncate are lost. `create`
would hand the new file to root and silently stop every runner account from
logging, because the wrapper never fails a job over logging. For lossless
rotation use `create 0664 <runner-user> <runner-group>` instead.

## Security notes

* Allow-list only: fixed `CIRCLE_*` names, the host identity, and operator
  settings. Tokens (`CIRCLE_TOKEN` and similar), the environment and the
  agent's arguments are never read into a log call.
* The runner config is read only to find `runner.name`; the auth token line is
  not kept, logged or used. `/proc/<parent>/cmdline` is read only to find the
  `--config` path.
* Operator files and the cache are parsed as `key=value`, never `source`d.
* The task token stays on the agent's stdin: the wrapper never reads or
  redirects it, and all helper commands run with `</dev/null`.
* Event data is job-controlled text (branch names, job names). It is escaped
  and length-capped (256 bytes by default, never splitting a UTF-8 character),
  and a line that is still over 3800 bytes is replaced by a minimal one.
* The HTTP header travels to curl on stdin, never in `ps`. The IMDS token is
  short-lived (60 s) and used only for the request. Use HTTPS for the sink.
* The wrapper does not change the job's environment, umask or process group.
* The log is world-readable by default (`0644`, as created by the first
  writer) and contains project/branch/user-controlled strings; restrict the
  directory if that matters.
* The runner sends `SIGTERM` to the wrapper only, so forwarding is what lets
  the agent shut down cleanly; the later `SIGKILL` hits the whole process
  group. Set `CCI_JOBLOG_FORWARD_SIGNALS=0` only if you must disable
  forwarding.

## How the data joins up

The wrapper fills the gap in CircleCI's own telemetry: the OpenTelemetry job,
step and task spans carry `com.circleci.resource.class` and
`com.circleci.job.status`, but no runner or host identity. They are sent when
each job finishes. The wrapper and the host agents add the where and the
live view, and everything joins on two keys: `job_id` and `instance_id`.

| Source | Carries | Join key |
|---|---|---|
| Wrapper events (`jobs.jsonl`) | `job_id`, `workflow_id`, `instance_id`, `runner_name`, `resource_class`, start/end | `job_id` = `CIRCLE_WORKFLOW_JOB_ID` |
| CircleCI spans (OTLP exporter) | job result (`com.circleci.job.status`), resource class, step spans and durations | `com.circleci.job.id` = `job_id` |
| Host metrics (Alloy unix exporter, textfile busy gauge) | CPU, memory, disk, network, busy/idle per runner | `instance_id` label |
| Task-agent journal (optional) | step start/end, job result as the host sees it, near real time | `job-id` = `job_id`, plus `instance_id` |

```
 job_id ----------+--> wrapper events ---+
                  +--> CircleCI spans ---+--> one job: where, when, result, steps
                  +--> task-agent log ---+
 instance_id -----+--> host metrics -----+--> what the host was doing meanwhile
```

## Shipping with Grafana Alloy

[`examples/alloy/config.alloy`](examples/alloy/config.alloy) ships the wrapper
events, the optional task-agent journal lines and host metrics to any OTLP/HTTP
endpoint (tested with Grafana Cloud). Its blocks:

1. **File tail to Loki over OTLP.** `local.file_match` and `loki.source.file`
   tail `jobs.jsonl`; `loki.process` promotes `event`, `resource_class`,
   `runner` and `instance_id` to labels (job and workflow ids stay in the JSON
   body, queried with `| json`); `otelcol.receiver.loki` and
   `otelcol.processor.transform` turn the stream into OTLP logs named
   `circleci-job-wrapper`.
2. **Journal pipeline (optional).** `loki.source.journal` reads the runner
   units' journal. The task agent writes JSON lines there; `loki.process` keeps
   only `Runner started execution`, `step start`, `step end` and `Reporting
   task end.` (each has a `job-id`), labels them `event=task_start|step_start|
   step_end|task_end`, `log_type=task_agent` and `instance_id`. This gives
   near-real-time step progress and the job result per host. It is an internal
   format and may change between runner versions. Edit `matches` to list your
   runner units.
3. **Host metrics.** `prometheus.exporter.unix` with its `textfile` collector
   pointed at `CCI_JOBLOG_PROM_DIR`, scraped every 15 s into
   `otelcol.receiver.prometheus`.
4. **EC2 identity.** `otelcol.processor.resourcedetection` with the `ec2` and
   `system` detectors sets `host.id` (the instance id) on logs and metrics.
5. **`instance_id` on metrics.** `otelcol.processor.transform "metrics"` copies
   `host.id` into an `instance_id` datapoint attribute, so metrics join with
   the wrapper's `instance_id`.
6. **Export.** `otelcol.exporter.otlphttp` with `otelcol.auth.basic`.

Environment (for example `/etc/default/alloy`):

| Variable | Meaning |
|---|---|
| `OTLP_ENDPOINT` | OTLP/HTTP base URL; Grafana Cloud: the stack's region gateway `https://otlp-gateway-<region>.grafana.net/otlp` |
| `OTLP_USERNAME` | Grafana Cloud instance (stack) id |
| `OTLP_PASSWORD` | access token with write scope (never commit it) |
| `EC2_INSTANCE_ID` | this host's instance id, used for the journal lines (write it at install time from IMDSv2, `/latest/meta-data/instance-id`) |

Permissions: the `alloy` user needs read access to `jobs.jsonl` (add it to the
runner's group), and membership of `systemd-journal` for the journal pipeline.
The textfile directory must be readable by `alloy` too.

### CircleCI spans to Grafana

Send CircleCI's OpenTelemetry spans to the same stack through CircleCI's
exporter API (`POST /api/v2/otel/exporters`) with:

* endpoint: the gateway URL above with `/v1/traces` appended;
* protocol: `http`;
* header: `Authorization: Basic <base64(stackid:token)>`.

The spans then land in Tempo with `com.circleci.job.id` matching the wrapper's
`job_id`.

## Shipping with Datadog Agent

Documented here, **not tested** in this repository. See Datadog's
[custom log collection](https://docs.datadoghq.com/agent/logs/#custom-log-collection)
and [Prometheus host collection](https://docs.datadoghq.com/integrations/guide/prometheus-host-collection/).

1. Enable logs in `datadog.yaml`: `logs_enabled: true`.
2. Create `/etc/datadog-agent/conf.d/circleci_job_wrapper.d/conf.yaml`:

   ```yaml
   logs:
     - type: file
       path: /var/log/circleci-job-wrapper/jobs.jsonl
       service: circleci-job-wrapper
       source: circleci
   ```

   Datadog parses the JSON automatically into attributes; make `@job_id`,
   `@instance_id` and `@runner_name` facets.
3. Add the `dd-agent` user to the runner's group so it can read the file.
4. Optional: a second `type: journald` source for the runner units, with
   `include_units`, to get the task agent's step and result lines (same
   caveat: internal format).
5. Host metrics come from the Agent's built-in system checks; on EC2 the host
   is identified by its instance id.
6. The busy gauge: point the Agent's OpenMetrics check at node_exporter's
   textfile collector, or build Datadog log-based metrics from `job_start` /
   `job_end`.
7. CircleCI spans reach Datadog through its OTLP intake (the Agent's or a
   Collector's OTLP receiver, or Datadog's OTLP endpoint), using the same
   CircleCI exporter API as above.

## Example dashboard (Grafana)

`examples/grafana/build_dashboard.py` generates the dashboard JSON; pass the
datasource UIDs of your stack:

```sh
python3 examples/grafana/build_dashboard.py --prom <prom-uid> --loki <loki-uid> --tempo <tempo-uid> > dashboard.json
# upload: POST /api/dashboards/db with {"dashboard": <dashboard.json>, "overwrite": true}
```

Panels:

* **Fleet now**: busy and idle runners, hosts reporting, and a table of what
  each runner is doing (job, project, running for), from the busy gauge.
* **Host health** per instance (CPU, IO wait, memory, disk, network, load),
  with job starts as annotations.
* **Jobs per host** (from wrapper events).
* **Job results per host**, from the task agent's "Reporting task end." line, and
  job results from CircleCI spans.
* **Failed jobs over time per host**: a spike on one host is a wedged worker.
* **Live step activity** from the task agent journal.
* **Recent jobs**: which host ran what, with a drill-down link per job. Job,
  workflow and pipeline ids link to the CircleCI UI (`build_url`,
  `workflow_url`, `pipeline_url`).
* **Per-job drill-down** (`$job_id`): where and when it ran, the result, steps
  slowest first (from spans), and host CPU and IO wait during the job window.

## License

MIT, Copyright (c) CircleCI. See [LICENSE](LICENSE).
