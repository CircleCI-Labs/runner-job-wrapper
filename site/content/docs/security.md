---
title: Security
weight: 11
---

To report a vulnerability, read [SECURITY.md](https://github.com/CircleCI-Labs/runner-job-wrapper/blob/main/SECURITY.md).

## What the wrapper reads and writes

- **Allow-list only.** The wrapper reads fixed `CIRCLE_*` names, the host identity and the operator settings. Tokens (`CIRCLE_TOKEN` and similar), the environment and the agent's arguments are never read into a log call.
- **The runner config** is read only to find `runner.name`. The auth token line is not kept, logged or used. `/proc/<parent>/cmdline` is read only to find the `--config` path.
- **Operator files and the cache** are parsed as `key=value`, never `source`d.
- **The task token** stays on the agent's stdin. The wrapper never reads or redirects it, and all helper commands run with `</dev/null`.
- **Job-controlled text** (branch names, job names) is escaped and length-capped (256 bytes by default, never splitting a UTF-8 character). A line that is still over 3800 bytes is replaced by a minimal one.
- **The HTTP header** travels to curl on stdin, never in `ps`. The IMDS token is short-lived (60 s) and used only for the request. Use HTTPS for the sink.
- **The job** keeps its environment, umask and process group.

## What you should decide

- **The log is world-readable by default** (`0644`, as created by the first writer) and contains project, branch and user-controlled strings. Restrict the directory if that matters.
- **`/run/circleci-job-wrapper` is sticky and mode 1777**, like `/tmp`, so runner users cannot delete each other's state files or replace the root-owned `host.env`. Tighten it (for example 0775 with a `Group=`) if all runners share one account.
- **Signal forwarding** is what lets the agent shut down cleanly, because the runner sends `SIGTERM` to the wrapper only. Set `CCI_JOBLOG_FORWARD_SIGNALS=0` only if you must.
- **Extra fields** skip keys that look like secrets, but only the operator should write the operator file.
