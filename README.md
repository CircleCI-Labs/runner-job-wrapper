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
  name and resource class on every event.
* Best effort only: every logging failure is swallowed. No `jq`, no daemon, no
  Python; bash 4+ and POSIX utilities (`date`, `curl`, `mkdir`, `mv`, `rm`).
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

with the job's built-in environment (`CIRCLE_*`) added to the environment, the
task token on stdin, and (on cancel) signals sent to the process group. The
wrapper:

1. starts the task agent as a child (`<&0`, so stdin is the very same pipe),
2. then, while the job already runs, resolves host identity and writes
   `job_start` plus the state file (start-up cost for the job is one `fork`),
3. waits for the child, forwarding `SIGTERM`/`SIGINT`/`SIGHUP` to it if the
   wrapper itself is signalled,
4. writes `job_end` (`status` = `success`, `failed`, or `cancelled` when a
   signal was received), removes the state file, and exits with the child's
   exit code (`128+n` for a signalled child).

Every helper command the wrapper runs has `</dev/null`, so it can never steal
the task token from the agent's stdin.

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
Give each its own identity with `CCI_RUNNER_NAME` in its service environment
(for example `Environment=CCI_RUNNER_NAME=runner-2` in a systemd drop-in); see
[Runner name](#runner-name).

Run the tests with `make check` (shellcheck + bats; needs `bats`, `jq`,
`python3`, `curl`; `strace` and `iconv` are used when present).

## Configuration

All settings are environment variables of the runner process (they reach the
wrapper because the runner passes its environment on), or `KEY=value` lines in
the operator file (`CCI_JOBLOG_CONF`, only for the three keys marked *file*).
The environment wins over the file.

| Variable | Default | Meaning |
|---|---|---|
| `CCI_JOBLOG_FILE` | `/var/log/circleci-job-wrapper/jobs.jsonl` | JSONL output file; directory is created if missing; skipped silently if unwritable |
| `CCI_JOBLOG_STATE_DIR` | `/run/circleci-job-wrapper` | Directory for `<runner>.json` current-job files |
| `CCI_JOBLOG_STATE_ON_END` | `remove` | `remove` deletes the state file at job end; `idle` rewrites it as `{"state":"idle",...}` |
| `CCI_JOBLOG_HOST_CACHE` | `/run/circleci-job-wrapper/host.env` | Host identity cache (`key=value`) |
| `CCI_JOBLOG_CONF` | `/etc/circleci-job-wrapper/wrapper.env` | Operator file (`CCI_RESOURCE_CLASS`, `CCI_RUNNER_NAME`, `CCI_JOBLOG_EXTRA_FIELDS`). Parsed, never sourced |
| `CCI_JOBLOG_IMDS_URL` | `http://169.254.169.254` | Metadata endpoint (override for tests) |
| `CCI_RUNNER_CONFIG` | parent's `--config`, else `/etc/circleci-runner/circleci-runner-config.yaml` | Runner config to read `runner.name` from |
| `CCI_RUNNER_NAME` | from runner config | Runner name; wins over the config file (*file*) |
| `CCI_RESOURCE_CLASS` | empty | Resource class (*file*) |
| `CCI_JOBLOG_EXTRA_FIELDS` | empty | `k=v,k=v`, merged into every event as strings (*file*). Reserved names and keys containing `token`, `secret`, `passw`, `credential`, `auth`, `apikey` are skipped; 128 bytes per value |
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
environment instead. `resolve_runner_and_class` in the script has a marked
`HOOK` for reading it from a `CIRCLE_*` built-in should one turn out to carry
it.

## Event schema (version 1)

One JSON object per line, UTF-8, each written with a single append (lines are
well under 4 KiB, so concurrent appends from many runner agents do not
interleave). All identifiers are strings, and a missing value is `""`, so every
line has the same keys. `job_end` additionally has `exit_code`, `duration_ms`
and `status`.

| Field | Source |
|---|---|
| `schema` (number), `event`, `ts` | `job_start` or `job_end`; RFC 3339 UTC with milliseconds |
| `job_id` | `CIRCLE_WORKFLOW_JOB_ID` (fallback `CIRCLE_JOB_ID`) |
| `job_name`, `job_number` | `CIRCLE_JOB`, `CIRCLE_BUILD_NUM` |
| `workflow_id`, `pipeline_id`, `pipeline_number` | `CIRCLE_WORKFLOW_ID`, `CIRCLE_PIPELINE_ID`, `CIRCLE_PIPELINE_NUMBER` |
| `project`, `org` | `CIRCLE_PROJECT_REPONAME`, `CIRCLE_PROJECT_USERNAME` |
| `branch`, `sha`, `build_url`, `node_index`, `pr_number` | `CIRCLE_BRANCH`, `CIRCLE_SHA1`, `CIRCLE_BUILD_URL`, `CIRCLE_NODE_INDEX`, `CIRCLE_PR_NUMBER` |
| `hostname` | the host's name |
| `instance_id`, `instance_type`, `availability_zone`, `region`, `private_ip`, `ami_id` | EC2 instance identity document (empty off EC2) |
| `runner_name`, `resource_class` | see above |
| `wrapper_pid`, `agent_pid` (numbers) | the wrapper and the task agent process |
| extra fields | `CCI_JOBLOG_EXTRA_FIELDS` |
| `exit_code`, `duration_ms` (numbers), `status` | `job_end` only. `status`: `success` (exit 0), `failed`, `cancelled` (the wrapper received TERM/INT/HUP) |

Only the variables listed here are ever read: the environment is never dumped
and the agent's command line is never logged. The `CIRCLE_*` names are read
defensively; any that the runner does not provide are simply empty.

```json
{"schema":1,"event":"job_start","ts":"2026-11-18T20:31:55.456Z","job_id":"5b1e0c1a-0000-4000-8000-000000000001","job_name":"build","job_number":"1234","workflow_id":"7f3d0000-0000-4000-8000-000000000002","pipeline_id":"a1b20000-0000-4000-8000-000000000003","pipeline_number":"567","project":"example-repo","org":"example-org","branch":"main","sha":"0123456789abcdef0123456789abcdef01234567","build_url":"https://app.circleci.com/jobs/1234","node_index":"0","pr_number":"","hostname":"ip-10-0-1-23","instance_id":"i-0123456789abcdef0","instance_type":"c7g.xlarge","availability_zone":"us-east-1b","region":"us-east-1","private_ip":"10.0.1.23","ami_id":"ami-0abc1234def567890","runner_name":"runner-1","resource_class":"example-org/linux-large","wrapper_pid":1656458,"agent_pid":1656459,"team":"infra","pool":"bazel"}
{"schema":1,"event":"job_end","ts":"2026-11-18T20:31:55.758Z","job_id":"5b1e0c1a-0000-4000-8000-000000000001","job_name":"build","...":"(same fields as job_start)","team":"infra","pool":"bazel","exit_code":0,"duration_ms":302,"status":"success"}
```

(`"...":` above is only an abbreviation for this document; real lines repeat
all fields.)

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
* A `SIGTERM` that reaches both processes (the runner signals the process
  group) is also forwarded once by the wrapper, so the agent can see it twice.
  Set `CCI_JOBLOG_FORWARD_SIGNALS=0` if the agent mishandles that.

## Shipping with Grafana Alloy

_TODO: `loki.source.file` on `jobs.jsonl`, JSON parsing and labels._

## Shipping with Datadog Agent

_TODO: `logs:` config with `type: file`, `source`, `service`._

## License

MIT, Copyright (c) CircleCI. See [LICENSE](LICENSE).
