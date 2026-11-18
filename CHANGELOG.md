# Changelog

This project follows [Semantic Versioning](https://semver.org/). Before 1.0, a minor release can change behavior, so read this file before you upgrade.

## Unreleased

First version.

### Added

- `bin/circleci-job-wrapper`, a bash `command_prefix` wrapper for CircleCI machine runner 3.1.11 or later. It writes `job_start` and `job_end` events as JSONL and never changes the job.
- Host identity on every event: EC2 instance, type, availability zone, region, private IP and AMI, plus runner name and resource class. A boot-time systemd unit caches the identity.
- CircleCI job, workflow, pipeline, project and organization IDs, and workflow and pipeline links, on every event. `job_id` joins with `com.circleci.job.id` on CircleCI OpenTelemetry spans.
- `start_ms`, `end_ms` and `agent_status` on `job_end`.
- Per-runner state file, optional Prometheus busy gauge (`CCI_JOBLOG_PROM_DIR`) and optional HTTP sink (`CCI_JOBLOG_HTTP_URL`).
- Operator file `/etc/circleci-job-wrapper/wrapper.env` and extra event fields.
- Signal forwarding, a kill switch (`CCI_JOBLOG_DISABLE`) and debug output (`CCI_JOBLOG_DEBUG`).
- Logrotate config.
- Grafana Alloy example for wrapper events, host metrics and an experimental task-agent journal pipeline. Tested with Grafana Cloud.
- Example Grafana dashboard generator.
- Datadog Agent instructions (documented, not tested).
- bats test suite (62 tests) and a CircleCI pipeline.
- Docs site at https://circleci-labs.github.io/runner-job-wrapper/.
