---
title: Example Grafana dashboard
weight: 1
---

`examples/grafana/build_dashboard.py` generates the dashboard JSON. Pass the datasource UIDs of your stack:

```sh
python3 examples/grafana/build_dashboard.py --prom <prom-uid> --loki <loki-uid> --tempo <tempo-uid> > dashboard.json
# upload: POST /api/dashboards/db with {"dashboard": <dashboard.json>, "overwrite": true}
```

For CircleCI Server, also pass `--app-url` so the links point at your installation. The dashboard needs the [Alloy example]({{< relref "/docs/send-the-data/ship-with-alloy.md" >}}) data, and the CircleCI spans for the span panels.

## Fleet dashboard

![The CircleCI runner fleet dashboard: pipeline performance, fleet right now, host health, jobs per host and recent jobs](../../../images/fleet-dashboard.png)

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

![The job-detail dashboard: where and when the job ran, its result, the full trace, steps slowest first, and the CPU and memory it used](../../../images/job-detail-dashboard.png)

*The job-detail dashboard for one job.*

- **Where and when it ran**, from the wrapper, and the **result**, from the CircleCI job span.
- **The full trace timeline**: pipeline, workflow, job and steps.
- **Steps, slowest first**, from step spans.
- **Live step progress** as it happened, from the task-agent log on the host (experimental).
- **Job CPU and memory** of the runner's service cgroup, from cAdvisor via the Alloy example.
- **CPU time** of the job (`cpu_user_ms`, `cpu_sys_ms`) from the wrapper.
- **Host metrics** during the job window.

More dashboards (runner detail, resource class detail) are being added to `examples/grafana/`.

## Runner detail dashboard

`examples/grafana/build_runner_dashboards.py runner` generates it (uid `cci-runner-detail`). Click any runner name in the other dashboards, or open it with `?var-runner=<runner name>`. The `cgroup` and `instance` variables fill in from the runner's busy gauge.

![The runner detail dashboard: status, jobs taken, failures, busy time, CPU time, the runner's CPU and memory, host metrics, and every job it ran](../../../images/runner-dashboard.png)

- **Summary:** status now, jobs taken, failed jobs, share of time busy, CPU time used by its jobs, and median job duration.
- **Running now:** the current job, with links to CircleCI and to the job-detail dashboard.
- **Resources:** the runner service's own CPU and memory (cAdvisor, its cgroup), its busy/idle state, and the host's CPU, IO wait and memory.
- **Jobs this runner took:** jobs over time, results over time (task agent log, experimental), duration per job, and a table of every job, newest first, linked to CircleCI and to the job-detail dashboard.

Failed-job counts come from the task agent's journal line, matched to the runner through its systemd unit (`label_format cg="/system.slice/{{.unit}}"`), so they need the optional journal pipeline in the Alloy example.

## Resource class dashboard

`examples/grafana/build_runner_dashboards.py resource-class` generates it (uid `cci-runner-rc`). Click any resource class in the other dashboards, or open it with `?var-rc=<namespace>/<class>`.

![The resource class dashboard: runners, busy now, utilization, job count and duration percentiles, per-runner load and resources, slowest jobs and recent jobs](../../../images/resource-class-dashboard.png)

- **Summary:** runners, busy now, utilization over the time range, jobs, and median and P95 job duration (CircleCI spans filtered on `com.circleci.resource.class`).
- **Runners in this class:** busy or idle, the current job, and CPU now; each runner links to its detail dashboard.
- **Capacity and load:** busy runners against runners, jobs started per runner, job results, host CPU for the hosts in the class, and CPU and memory per runner.
- **Jobs in this class:** slowest jobs (median, P95, max) and recent jobs.

Queue depth and wait time per class are not in these dashboards: CircleCI's spans don't carry them. The fleet API (`GET /api/v3/runner/fleets`, or `circleci runner fleet list`) returns running and queued counts per class if you want to poll them.

## Upload all four

```bash
for d in fleet job runner resource-class; do
  case $d in
    fleet) python3 examples/grafana/build_dashboard.py ;;
    job) python3 examples/grafana/build_job_dashboard.py ;;
    *) python3 examples/grafana/build_runner_dashboards.py "$d" ;;
  esac > "$d.json"
  jq -n --slurpfile d "$d.json" '{dashboard: $d[0], overwrite: true}' |
    curl -s -H "Authorization: Bearer $GRAFANA_TOKEN" -H 'Content-Type: application/json' \
      -X POST "$GRAFANA_URL/api/dashboards/db" -d @-
done
```

All four accept `--prom`, `--loki`, `--tempo` (data source UIDs) and `--app-url` (CircleCI UI base, for CircleCI Server).
