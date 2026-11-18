---
title: Example Grafana dashboard
weight: 10
---

`examples/grafana/build_dashboard.py` generates the dashboard JSON. Pass the datasource UIDs of your stack:

```sh
python3 examples/grafana/build_dashboard.py --prom <prom-uid> --loki <loki-uid> --tempo <tempo-uid> > dashboard.json
# upload: POST /api/dashboards/db with {"dashboard": <dashboard.json>, "overwrite": true}
```

For CircleCI Server, also pass `--app-url` so the links point at your installation. The dashboard needs the [Alloy example](../ship-with-alloy/) data, and the CircleCI spans for the span panels.

## Fleet dashboard

![The CircleCI runner fleet dashboard: pipeline performance, fleet right now, host health, jobs per host and recent jobs](../../images/fleet-dashboard.png)

*The runner fleet dashboard (uid `cci-runner-fleet`), from a small test fleet.*

Rows, top to bottom:

- **Pipeline performance** (CircleCI spans). Workflows, success rate, median and P95 wall time, workflows by result, slowest jobs (median, P95, max) and recent workflows with links. Tested on Grafana Cloud Tempo with TraceQL metrics.
- **Fleet right now.** Busy and idle runners, hosts reporting, and a table of what each runner is doing (job, project, running for), from the busy gauge.
- **Host health** per instance: CPU, IO wait, memory, disk, network and load, with job starts as annotations.
- **Jobs per host.** Jobs started per host, job results from the task-agent log and from CircleCI spans, failed jobs over time (a spike on one host is a wedged worker) and live step activity from the task-agent journal.
- **Recent jobs.** Which host ran what.

Job, workflow and pipeline IDs link to the CircleCI UI (`build_url`, `workflow_url`, `pipeline_url`). **Drill into this job** opens the job-detail dashboard for that job.

## Job-detail dashboard

`examples/grafana/build_job_dashboard.py` generates it (uid `cci-runner-job`). Open it from the fleet dashboard, or with `?var-job_id=<id>&var-trace_id=<pipeline id without dashes>&var-cgroup=<wrapper cgroup>&var-instance=<instance id>` plus a time range.

![The job-detail dashboard: where and when the job ran, its result, the full trace, steps slowest first, and the CPU and memory it used](../../images/job-detail-dashboard.png)

*The job-detail dashboard for one job.*

- **Where and when it ran**, from the wrapper, and the **result**, from the CircleCI job span.
- **The full trace timeline**: pipeline, workflow, job and steps.
- **Steps, slowest first**, from step spans.
- **Live step progress** as it happened, from the task-agent log on the host (experimental).
- **Job CPU and memory** of the runner's service cgroup, from cAdvisor via the Alloy example.
- **CPU time** of the job (`cpu_user_ms`, `cpu_sys_ms`) from the wrapper.
- **Host metrics** during the job window.

More dashboards (runner detail, resource class detail) are being added to `examples/grafana/`.
