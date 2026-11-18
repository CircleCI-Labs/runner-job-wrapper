---
title: Join data with CircleCI OpenTelemetry
weight: 6
---

CircleCI's own OpenTelemetry job, step and task spans carry `com.circleci.resource.class` and `com.circleci.job.status`, but no runner or host identity. They are sent when each job finishes. The wrapper and the host agents add the where and the live view. Everything joins on two keys: `job_id` and `instance_id`.

| Source | Carries | Join key |
|---|---|---|
| Wrapper events (`jobs.jsonl`) | `job_id`, `workflow_id`, `instance_id`, `runner_name`, `resource_class`, start and end | `job_id` = `CIRCLE_WORKFLOW_JOB_ID` |
| CircleCI spans (OTLP exporter) | Job result (`com.circleci.job.status`), resource class, step spans and durations | `com.circleci.job.id` = `job_id` |
| Host metrics (Alloy unix exporter, textfile busy gauge) | CPU, memory, disk, network, busy or idle per runner | `instance_id` label |
| Task-agent journal (optional, experimental) | Step start and end, the job result as the host sees it, in near real time | `job-id` = `job_id`, plus `instance_id` |

```text
 job_id ----------+--> wrapper events ---+
                  +--> CircleCI spans ---+--> one job: where, when, result, steps
                  +--> task-agent log ---+
 instance_id -----+--> host metrics -----+--> what the host was doing meanwhile
```

To receive the spans, set up the OpenTelemetry export of your CircleCI organization with CircleCI's exporter API (`POST /api/v2/otel/exporters`). See [Ship with Grafana Alloy](../ship-with-alloy/#circleci-spans-to-grafana) for a worked example, and CircleCI's documentation for the current API.
