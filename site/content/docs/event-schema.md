---
title: Event schema
weight: 3
---

The wrapper writes one JSON object per line (schema version 1), UTF-8. Each line is written with a single append and stays well under 4 KiB, so concurrent appends from many runner agents do not interleave.

All identifiers are strings, and a missing value is `""`, so every line has the same keys. `job_end` additionally has `agent_exit_code`, `duration_ms`, `start_ms`, `end_ms` and `agent_status`.

| Field | Source |
|---|---|
| `schema` (number), `event`, `ts` | `job_start` or `job_end`. `ts` is RFC 3339 UTC with milliseconds |
| `job_id` | `CIRCLE_WORKFLOW_JOB_ID` (fallback `CIRCLE_JOB_ID`). The join key: equals `com.circleci.job.id` on CircleCI spans |
| `job_name`, `job_number` | `CIRCLE_JOB`, `CIRCLE_BUILD_NUM` |
| `workflow_id`, `pipeline_id` | `CIRCLE_WORKFLOW_ID`, `CIRCLE_PIPELINE_ID` |
| `pipeline_number` | `CIRCLE_PIPELINE_NUMBER`. The runner does not provide it, so it is normally empty |
| `workflow_url`, `pipeline_url` | `<base>/workflow/<workflow_id>` and `<base>/pipeline/<pipeline_id>`. The base is `CCI_JOBLOG_APP_URL` |
| `project`, `org` | `CIRCLE_PROJECT_REPONAME`, `CIRCLE_PROJECT_USERNAME` |
| `org_id`, `project_id` | `CIRCLE_ORGANIZATION_ID`, `CIRCLE_PROJECT_ID` |
| `branch`, `sha`, `build_url`, `node_index` | `CIRCLE_BRANCH`, `CIRCLE_SHA1`, `CIRCLE_BUILD_URL` (the job link), `CIRCLE_NODE_INDEX` |
| `pr_number` | `CIRCLE_PR_NUMBER`. The runner does not provide it, so it is normally empty |
| `hostname` | The host's name |
| `instance_id`, `instance_type`, `availability_zone`, `region`, `private_ip`, `ami_id` | EC2 instance identity document. Empty off EC2 |
| `runner_name`, `resource_class` | See [Configuration](../configuration/) |
| `wrapper_pid`, `agent_pid` (numbers) | The wrapper and the task agent process |
| extra fields | `CCI_JOBLOG_EXTRA_FIELDS` |
| `agent_exit_code`, `duration_ms`, `start_ms`, `end_ms` (numbers), `agent_status` | `job_end` only. `start_ms` and `end_ms` are epoch milliseconds |

`agent_status` is `completed` (the agent exited 0), `agent_error`, or `cancelled` (the wrapper received `TERM`, `INT` or `HUP`). It describes the agent process, not the job result. See [How it works](../how-it-works/#agent_status-is-not-the-job-result).

Only the variables listed here are ever read. The environment is never dumped and the agent's command line is never logged. The `CIRCLE_*` names are read defensively, and any that the runner does not provide are empty.

## Example

```json
{"schema":1,"event":"job_start","ts":"2026-11-18T20:31:55.456Z","job_id":"5b1e0c1a-0000-4000-8000-000000000001","job_name":"build","job_number":"1234","workflow_id":"7f3d0000-0000-4000-8000-000000000002","workflow_url":"https://app.circleci.com/workflow/7f3d0000-0000-4000-8000-000000000002","pipeline_id":"a1b20000-0000-4000-8000-000000000003","pipeline_url":"https://app.circleci.com/pipeline/a1b20000-0000-4000-8000-000000000003","pipeline_number":"","project":"example-repo","org":"example-org","org_id":"c0de0000-0000-4000-8000-000000000004","project_id":"d00d0000-0000-4000-8000-000000000005","branch":"main","sha":"0123456789abcdef0123456789abcdef01234567","build_url":"https://app.circleci.com/jobs/1234","node_index":"0","pr_number":"","hostname":"ip-10-0-1-23","instance_id":"i-0123456789abcdef0","instance_type":"c7g.xlarge","availability_zone":"us-east-1b","region":"us-east-1","private_ip":"10.0.1.23","ami_id":"ami-0abc1234def567890","runner_name":"runner-1","resource_class":"my-org/linux-large","wrapper_pid":1656458,"agent_pid":1656459,"team":"infra","pool":"bazel"}
{"schema":1,"event":"job_end","ts":"2026-11-18T20:31:55.758Z","job_id":"5b1e0c1a-0000-4000-8000-000000000001","job_name":"build","...":"(same fields as job_start)","team":"infra","pool":"bazel","agent_exit_code":0,"duration_ms":302,"start_ms":1795033915456,"end_ms":1795033915758,"agent_status":"completed"}
```

The `"...":` key in the second line only abbreviates this page. Real lines repeat all fields.
