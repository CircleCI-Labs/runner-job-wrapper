#!/usr/bin/env python3
"""Generate the 'CircleCI job detail' Grafana dashboard JSON (uid cci-runner-job).

Open it with ?var-job_id=<id>&var-trace_id=<pipeline id without dashes>
&var-cgroup=<wrapper cgroup>&var-instance=<instance id>&from=<start ms>&to=<end ms>.
The fleet dashboard's "Drill into this job" links fill these in.
"""
import argparse, json

ap = argparse.ArgumentParser()
ap.add_argument("--prom", default="grafanacloud-prom")
ap.add_argument("--loki", default="grafanacloud-logs")
ap.add_argument("--tempo", default="grafanacloud-traces")
ap.add_argument("--app-url", default="https://app.circleci.com")
a = ap.parse_args()
PROM = {"type": "prometheus", "uid": a.prom}
LOKI = {"type": "loki", "uid": a.loki}
TEMPO = {"type": "tempo", "uid": a.tempo}
APP = a.app_url.rstrip("/")
SEL = '{service_name="circleci-job-wrapper"}'

panels, pid, y = [], [1], [0]


def add(p, w, h, x):
    pid[0] += 1
    p["id"] = pid[0]
    p["gridPos"] = {"h": h, "w": w, "x": x, "y": y[0]}
    panels.append(p)


def nl(h):
    y[0] += h


def row(t):
    add({"type": "row", "title": t, "collapsed": False, "panels": []}, 24, 1, 0)
    nl(1)


def link(title, url, blank=True):
    return {"title": title, "url": url, "targetBlank": blank}


def links_on(field, *ls):
    return {"matcher": {"id": "byName", "options": field}, "properties": [{"id": "links", "value": list(ls)}]}


def hide(regex):
    return {"matcher": {"id": "byRegexp", "options": regex}, "properties": [{"id": "custom.hidden", "value": True}]}


def traceql(q, ref="A"):
    return {"datasource": TEMPO, "queryType": "traceql", "query": q, "refId": ref, "limit": 50, "spss": 100,
            "tableType": "spans", "streaming": False}


TEMPO_FLAT = [{"id": "merge", "options": {}},
              {"id": "organize", "options": {"excludeByName": {"traceService": True, "traceName": True, "spanID": True},
                                             "renameByName": {"traceIdHidden": "trace_id", "com.circleci.job.id": "job_id", "com.circleci.job.name": "job_name",
                                                              "com.circleci.job.status": "job result", "com.circleci.workflow.id": "workflow_id",
                                                              "com.circleci.workflow.name": "workflow", "com.circleci.resource.class": "resource_class",
                                                              "com.circleci.task.result": "step result", "name": "span"}}}]

row("Job $job_id")
add({"type": "table", "title": "Where and when it ran (wrapper)", "datasource": LOKI,
     "targets": [{"datasource": LOKI, "refId": "A", "expr": '%s | json | job_id="$job_id" | event="job_end"' % SEL}],
     "transformations": [{"id": "extractFields", "options": {"source": "Line", "format": "json", "replace": True}},
                         {"id": "filterFieldsByName", "options": {"include": {"names": [
                             "job_name", "runner_name", "instance_id", "instance_type", "availability_zone", "resource_class",
                             "duration_ms", "cpu_user_ms", "cpu_sys_ms", "branch", "workflow_id", "pipeline_id", "build_url", "cgroup"]}}}],
     "fieldConfig": {"defaults": {}, "overrides": [
         {"matcher": {"id": "byRegexp", "options": "duration_ms|cpu_user_ms|cpu_sys_ms"}, "properties": [{"id": "unit", "value": "ms"}]},
         links_on("job_name", link("Open job in CircleCI", "${__data.fields.build_url}")),
         links_on("workflow_id", link("Open workflow in CircleCI", APP + "/workflow/${__value.raw}")),
         links_on("pipeline_id", link("Open pipeline in CircleCI", APP + "/pipeline/${__value.raw}")),
         hide("build_url")]}}, 24, 4, 0)
nl(4)
add({"type": "table", "title": "Job result (CircleCI span)", "datasource": TEMPO,
     "description": "Click trace_id to load the span timeline below if it is empty.",
     "targets": [traceql('{ name =~ "Job:.*" && span.com.circleci.job.id = "$job_id" } | select(span.com.circleci.job.name, span.com.circleci.job.status, span.com.circleci.resource.class, span.com.circleci.workflow.name, span.com.circleci.workflow.id)')],
     "transformations": TEMPO_FLAT,
     "fieldConfig": {"defaults": {}, "overrides": [
         {"matcher": {"id": "byName", "options": "job result"}, "properties": [
             {"id": "mappings", "value": [{"type": "value", "options": {"success": {"color": "green"}, "failed": {"color": "red"}, "canceled": {"color": "orange"}}}]},
             {"id": "custom.cellOptions", "value": {"type": "color-text"}}]},
         links_on("trace_id", link("Show this trace below", "/d/cci-runner-job/circleci-job-detail?var-job_id=$job_id&var-trace_id=${__value.raw}&var-cgroup=$cgroup&var-instance=$instance&${__url_time_range}", False)),
         links_on("job_name", link("Open job in CircleCI", APP + "/workflow/${__data.fields.workflow_id}/job/${__data.fields.job_id}")),
         links_on("workflow_id", link("Open workflow in CircleCI", APP + "/workflow/${__value.raw}")),
         hide("Start time|Name")]}}, 24, 5, 0)
nl(5)

row("Spans: pipeline > workflow > job > steps (CircleCI OpenTelemetry)")
add({"type": "traces", "title": "Trace $trace_id", "datasource": TEMPO,
     "targets": [{"datasource": TEMPO, "queryType": "traceql", "query": "$trace_id", "refId": "A"}]}, 24, 14, 0)
nl(14)
add({"type": "table", "title": "Steps, slowest first", "datasource": TEMPO,
     "targets": [traceql('{ name =~ "Step:.*" && span.com.circleci.job.id = "$job_id" } | select(span.com.circleci.task.result)')],
     "transformations": TEMPO_FLAT,
     "fieldConfig": {"defaults": {}, "overrides": [{"matcher": {"id": "byName", "options": "duration"}, "properties": [{"id": "unit", "value": "ns"}]},
                                                   hide("trace_id|job_id")]},
     "options": {"sortBy": [{"displayName": "duration", "desc": True}]}}, 12, 8, 0)
add({"type": "table", "title": "Step progress as it happened (task agent log on the host)", "datasource": LOKI,
     "description": "Experimental: the task agent's own log lines, collected from the runner journal. Seconds behind real time.",
     "targets": [{"datasource": LOKI, "refId": "A", "expr": '%s | log_type="task_agent" | json | job_id="$job_id"' % SEL}],
     "transformations": [{"id": "extractFields", "options": {"source": "Line", "format": "json", "replace": True}},
                         {"id": "filterFieldsByName", "options": {"include": {"names": ["time", "msg", "step", "step-id", "step_type", "exit_code", "duration", "result"]}}},
                         {"id": "organize", "options": {"renameByName": {"duration": "duration_ms"}}}],
     "fieldConfig": {"defaults": {}, "overrides": [{"matcher": {"id": "byName", "options": "duration_ms"}, "properties": [{"id": "unit", "value": "ms"}]}]},
     "options": {"sortBy": [{"displayName": "time", "desc": False}]}}, 12, 8, 12)
nl(8)

row("Resources used during this job")
CG = 'cgroup=~"$cgroup", cgroup=~"/system.slice/circleci-runner.*"'
INST = 'instance_id=~"$instance", instance_id!=""'
ts = [
    ("Job CPU (cores), runner service cgroup", 'sum by (cgroup) (rate(container_cpu_usage_seconds_total{%s}[$__rate_interval]))' % CG, "short", "{{cgroup}}"),
    ("Job memory (working set), runner service cgroup", 'sum by (cgroup) (container_memory_working_set_bytes{%s})' % CG, "bytes", "{{cgroup}}"),
    ("Host CPU busy % (all jobs on the host)", '100 * (1 - avg by (instance_id) (rate(node_cpu_seconds_total{mode="idle",%s}[$__rate_interval])))' % INST, "percent", "{{instance_id}}"),
    ("Host IO wait %", '100 * avg by (instance_id) (rate(node_cpu_seconds_total{mode="iowait",%s}[$__rate_interval]))' % INST, "percent", "{{instance_id}}"),
    ("Host memory used %", '100 * (1 - node_memory_MemAvailable_bytes{%s} / node_memory_MemTotal_bytes{%s})' % (INST, INST), "percent", "{{instance_id}}"),
]
add({"type": "stat", "title": "CPU time used by the job (wrapper, from rusage)", "datasource": LOKI,
     "targets": [{"datasource": LOKI, "refId": "A", "expr": '%s | log_type="wrapper" | json | job_id="$job_id" | event="job_end"' % SEL}],
     "transformations": [{"id": "extractFields", "options": {"source": "Line", "format": "json", "replace": True}},
                         {"id": "filterFieldsByName", "options": {"include": {"names": ["duration_ms", "cpu_user_ms", "cpu_sys_ms"]}}},
                         {"id": "convertFieldType", "options": {"conversions": [{"targetField": "duration_ms", "destinationType": "number"},
                                                                                {"targetField": "cpu_user_ms", "destinationType": "number"},
                                                                                {"targetField": "cpu_sys_ms", "destinationType": "number"}]}}],
     "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "/.*/"}, "colorMode": "none", "graphMode": "none", "textMode": "value_and_name"},
     "fieldConfig": {"defaults": {"unit": "ms"}, "overrides": []}}, 8, 7, 16)
for i, (t, e, u, lg) in enumerate(ts):
    add({"type": "timeseries", "title": t, "datasource": PROM,
         "targets": [{"datasource": PROM, "refId": "A", "expr": e, "legendFormat": lg}],
         "fieldConfig": {"defaults": {"unit": u, "min": 0, "custom": {"fillOpacity": 15}}, "overrides": []}}, 8, 7, [0, 8, 0, 8, 16][i])
    if i in (1, 4):
        nl(7)

dash = {"uid": "cci-runner-job", "title": "CircleCI job detail", "tags": ["circleci", "runner"], "timezone": "browser",
        "schemaVersion": 39, "time": {"from": "now-3h", "to": "now"},
        "links": [{"title": "Runner fleet", "type": "link", "url": "/d/cci-runner-fleet/circleci-runner-fleet", "icon": "dashboard"}],
        "templating": {"list": [
            {"name": "job_id", "label": "Job ID", "type": "textbox", "query": "", "current": {"text": "", "value": ""}},
            {"name": "trace_id", "label": "Trace ID", "type": "textbox", "query": "", "current": {"text": "", "value": ""}},
            {"name": "cgroup", "label": "Runner cgroup", "type": "textbox", "query": ".+", "current": {"text": ".+", "value": ".+"}},
            {"name": "instance", "label": "EC2 instance", "type": "textbox", "query": ".+", "current": {"text": ".+", "value": ".+"}}]},
        "annotations": {"list": [{"name": "Job start/end", "datasource": LOKI, "enable": True, "iconColor": "green",
                                  "expr": '%s | json | job_id="$job_id"' % SEL, "titleFormat": "{{event}}", "textFormat": "{{job_name}} on {{runner_name}}"}]},
        "panels": panels}
print(json.dumps(dash, indent=1))
