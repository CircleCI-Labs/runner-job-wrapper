---
title: Example Grafana dashboard
weight: 9
---

`examples/grafana/build_dashboard.py` generates the dashboard JSON. Pass the datasource UIDs of your stack:

```sh
python3 examples/grafana/build_dashboard.py --prom <prom-uid> --loki <loki-uid> --tempo <tempo-uid> > dashboard.json
# upload: POST /api/dashboards/db with {"dashboard": <dashboard.json>, "overwrite": true}
```

For CircleCI Server, also pass `--app-url` so the links point at your installation. The dashboard needs the [Alloy example](../ship-with-alloy/) data, and the CircleCI spans for the span panels.

## Panels

- **Fleet now.** Busy and idle runners, hosts reporting, and a table of what each runner is doing (job, project, running for), from the busy gauge.
- **Host health** per instance: CPU, IO wait, memory, disk, network and load, with job starts as annotations.
- **Jobs per host**, from wrapper events.
- **Job results per host**, from the task agent's "Reporting task end." line, and job results from CircleCI spans.
- **Failed jobs over time per host.** A spike on one host is a wedged worker.
- **Live step activity**, from the task-agent journal.
- **Recent jobs.** Which host ran what, with a drill-down link per job. Job, workflow and pipeline IDs link to the CircleCI UI (`build_url`, `workflow_url`, `pipeline_url`).
- **Per-job drill-down** (`$job_id`). Where and when it ran, the result, steps slowest first (from spans), and host CPU and IO wait during the job window.
