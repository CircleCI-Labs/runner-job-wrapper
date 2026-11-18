#!/usr/bin/env python3
"""Generate the 'CircleCI runner fleet' Grafana dashboard JSON.

Datasource UIDs are parameters so the same dashboard works on any stack:
  build_dashboard.py --prom UID --loki UID --tempo UID > dashboard.json
"""
import argparse, json

ap = argparse.ArgumentParser()
ap.add_argument("--prom", default="grafanacloud-prom")
ap.add_argument("--loki", default="grafanacloud-logs")
ap.add_argument("--tempo", default="grafanacloud-traces")
ap.add_argument("--app-url", default="https://app.circleci.com", help="CircleCI UI base (change for CircleCI Server)")
a = ap.parse_args()
PROM = {"type": "prometheus", "uid": a.prom}
LOKI = {"type": "loki", "uid": a.loki}
TEMPO = {"type": "tempo", "uid": a.tempo}
APP = a.app_url.rstrip("/")

def link(title, url, blank=True):
    return {"title": title, "url": url, "targetBlank": blank}

def links_on(field, *ls):
    return {"matcher": {"id": "byName", "options": field}, "properties": [{"id": "links", "value": list(ls)}]}

DRILL = "/d/cci-runner-fleet/circleci-runner-fleet?var-job_id=${__value.raw}&from=now-3h&to=now"
SEL = '{service_name="circleci-job-wrapper"}'
TA = SEL + ' | log_type="task_agent"'
INST = 'instance_id=~"$instance", instance_id!=""'

panels, pid, y = [], [1], [0]

def nid():
    pid[0] += 1
    return pid[0]

def row(title):
    panels.append({"type": "row", "title": title, "id": nid(), "collapsed": False,
                   "gridPos": {"h": 1, "w": 24, "x": 0, "y": y[0]}, "panels": []})
    y[0] += 1

def add(p, w, h, x):
    p["id"] = nid()
    p["gridPos"] = {"h": h, "w": w, "x": x, "y": y[0]}
    panels.append(p)

def nl(h):
    y[0] += h

def prom(expr, legend="", instant=False, fmt="time_series", ref="A"):
    t = {"datasource": PROM, "expr": expr, "legendFormat": legend, "refId": ref}
    if instant:
        t.update({"instant": True, "range": False, "format": fmt})
    return t

def loki(expr, ref="A", qtype="range"):
    return {"datasource": LOKI, "expr": expr, "refId": ref, "queryType": qtype}

def traceql(q, ref="A", limit=200, table="spans"):
    return {"datasource": TEMPO, "queryType": "traceql", "query": q, "refId": ref,
            "limit": limit, "spss": 50, "tableType": table, "streaming": False}

TEMPO_FLAT = [{"id": "merge", "options": {}},
              {"id": "organize", "options": {"excludeByName": {"traceIdHidden": True, "traceService": True, "traceName": True, "spanID": True},
                                             "renameByName": {"com.circleci.job.id": "job_id", "com.circleci.job.name": "job_name", "com.circleci.job.status": "job result",
                                                              "com.circleci.resource.class": "resource_class", "com.circleci.workflow.id": "workflow_id", "com.circleci.workflow.name": "workflow", "com.circleci.task.result": "step result", "name": "span"}}}]

JOB_LINK = [{"title": "Drill into this job",
             "url": "/d/cci-runner-fleet/circleci-runner-fleet?var-job_id=${__data.fields.job_id}&var-instance=${__data.fields.instance_id}&from=${__data.fields.start_ms}&to=${__data.fields.end_ms}"},
            {"title": "Open job in CircleCI", "url": "${__data.fields.build_url}", "targetBlank": True}]

# ---------------------------------------------------------------- live fleet
row("Fleet right now (wrapper busy gauge)")
add({"type": "stat", "title": "Busy runners", "datasource": PROM,
     "targets": [prom('sum(circleci_runner_busy{%s})' % INST, instant=True)],
     "options": {"colorMode": "background", "graphMode": "none"},
     "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": "green"}}, "overrides": []}}, 4, 4, 0)
add({"type": "stat", "title": "Idle runners", "datasource": PROM,
     "targets": [prom('count(circleci_runner_busy{%s} == 0) or vector(0)' % INST, instant=True)],
     "options": {"colorMode": "background", "graphMode": "none"},
     "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": "blue"}}, "overrides": []}}, 4, 4, 4)
add({"type": "stat", "title": "Runner hosts reporting", "datasource": PROM,
     "targets": [prom('count(count by (instance_id) (node_load1{%s}))' % INST, instant=True)],
     "options": {"colorMode": "background", "graphMode": "none"},
     "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": "purple"}}, "overrides": []}}, 4, 4, 8)
add({"type": "timeseries", "title": "Busy runners over time", "datasource": PROM,
     "targets": [prom('sum by (runner) (circleci_runner_busy{%s})' % INST, "{{runner}}")],
     "fieldConfig": {"defaults": {"custom": {"drawStyle": "line", "lineInterpolation": "stepAfter", "fillOpacity": 30, "stacking": {"mode": "normal"}}, "min": 0, "decimals": 0}, "overrides": []}}, 12, 4, 12)
nl(4)
add({"type": "table", "title": "What each runner is doing now", "datasource": PROM,
     "description": "From the wrapper's per-runner Prometheus textfile. One row per runner agent; idle runners show no job.",
     "targets": [prom('max by (runner, instance_id, resource_class, job_name, project, job_id, workflow_id) (circleci_runner_busy{%s})' % INST, instant=True, fmt="table", ref="A"),
                 prom('time() - max by (runner, instance_id, resource_class, job_name, project, job_id, workflow_id) (circleci_runner_job_start_time_seconds{%s})' % INST, instant=True, fmt="table", ref="B")],
     "transformations": [{"id": "merge", "options": {}},
                         {"id": "organize", "options": {"excludeByName": {"Time": True},
                          "renameByName": {"Value #A": "busy", "Value #B": "running for"},
                          "indexByName": {"runner": 0, "instance_id": 1, "busy": 2, "job_name": 3, "running for": 4, "project": 5, "resource_class": 6, "job_id": 7, "workflow_id": 8}}}],
     "fieldConfig": {"defaults": {}, "overrides": [
         {"matcher": {"id": "byName", "options": "running for"}, "properties": [{"id": "unit", "value": "s"}]},
         {"matcher": {"id": "byName", "options": "busy"}, "properties": [
             {"id": "mappings", "value": [{"type": "value", "options": {"0": {"text": "idle", "color": "blue"}, "1": {"text": "busy", "color": "green"}}}]},
             {"id": "custom.cellOptions", "value": {"type": "color-background"}}]},
         links_on("job_name", link("Open running job in CircleCI", APP + "/workflow/${__data.fields.workflow_id}/job/${__data.fields.job_id}")),
         links_on("job_id", link("Open running job in CircleCI", APP + "/workflow/${__data.fields.workflow_id}/job/${__value.raw}"), link("Drill into this job", DRILL, False)),
         links_on("workflow_id", link("Open workflow in CircleCI", APP + "/workflow/${__value.raw}"))]}}, 24, 7, 0)
nl(7)

# ---------------------------------------------------------------- host health
row("Host health (Alloy unix exporter), job starts as annotations")
host_ts = [
    ("CPU busy %", '100 * (1 - avg by (instance_id) (rate(node_cpu_seconds_total{mode="idle",%s}[$__rate_interval])))' % INST, "percent"),
    ("CPU IO wait %", '100 * avg by (instance_id) (rate(node_cpu_seconds_total{mode="iowait",%s}[$__rate_interval]))' % INST, "percent"),
    ("Memory used %", '100 * (1 - node_memory_MemAvailable_bytes{%s} / node_memory_MemTotal_bytes{%s})' % (INST, INST), "percent"),
    ("Disk throughput", 'sum by (instance_id) (rate(node_disk_read_bytes_total{%s}[$__rate_interval]) + rate(node_disk_written_bytes_total{%s}[$__rate_interval]))' % (INST, INST), "Bps"),
    ("Network throughput", 'sum by (instance_id) (rate(node_network_receive_bytes_total{device!="lo",%s}[$__rate_interval]) + rate(node_network_transmit_bytes_total{device!="lo",%s}[$__rate_interval]))' % (INST, INST), "Bps"),
    ("Load average (1m)", 'max by (instance_id) (node_load1{%s})' % INST, "short"),
]
for i, (t, e, u) in enumerate(host_ts):
    add({"type": "timeseries", "title": t, "datasource": PROM, "targets": [prom(e, "{{instance_id}}")],
         "fieldConfig": {"defaults": {"unit": u, "min": 0, "custom": {"fillOpacity": 10}}, "overrides": []}}, 8, 7, (i % 3) * 8)
    if i % 3 == 2:
        nl(7)

# ---------------------------------------------------------------- jobs
row("Jobs per host: wrapper + task agent logs (host side) and CircleCI spans")
add({"type": "bargauge", "title": "Jobs started per host (time range)", "datasource": LOKI,
     "targets": [dict(loki('sum by (instance_id) (count_over_time(%s | event="job_start" | json | %s [$__range]))' % (SEL, INST), qtype="instant"), legendFormat="{{instance_id}}")],
     "options": {"orientation": "horizontal", "displayMode": "gradient", "showUnfilled": True, "namePlacement": "left"},
     "fieldConfig": {"defaults": {"decimals": 0, "min": 0}, "overrides": []}}, 8, 8, 0)
add({"type": "table", "title": "Job results from CircleCI spans", "datasource": TEMPO,
     "targets": [traceql('{ name =~ "Job:.*" } | select(span.com.circleci.job.id, span.com.circleci.job.name, span.com.circleci.job.status, span.com.circleci.resource.class, span.com.circleci.workflow.id)', limit=100)],
     "transformations": TEMPO_FLAT,
     "fieldConfig": {"defaults": {}, "overrides": [{"matcher": {"id": "byName", "options": "job result"}, "properties": [
         {"id": "mappings", "value": [{"type": "value", "options": {"success": {"color": "green"}, "failed": {"color": "red"}, "canceled": {"color": "orange"}}}]},
         {"id": "custom.cellOptions", "value": {"type": "color-text"}}]},
         links_on("job_id", link("Open job in CircleCI", APP + "/workflow/${__data.fields.workflow_id}/job/${__value.raw}"), link("Drill into this job", DRILL, False)),
         links_on("workflow_id", link("Open workflow in CircleCI", APP + "/workflow/${__value.raw}"))]}}, 8, 8, 16)
add({"type": "table", "title": "Job results per host (task agent log on the host)", "datasource": LOKI,
     "description": "From the task agent's own 'Reporting task end.' log line, collected by Alloy from the runner journal and tagged with the instance id. Many failures on one host at the same time points at a wedged worker.",
     "targets": [loki('sum by (instance_id, result) (count_over_time(%s | event="task_end" | json | result!="" | %s [$__range]))' % (TA, INST), qtype="instant")],
     "transformations": [{"id": "labelsToFields", "options": {"mode": "columns"}}, {"id": "merge", "options": {}},
                         {"id": "organize", "options": {"excludeByName": {"Time": True}, "renameByName": {"Value #A": "jobs"}}}],
     "fieldConfig": {"defaults": {"decimals": 0, "custom": {"cellOptions": {"type": "color-text"}}, "color": {"mode": "fixed", "fixedColor": "text"}}, "overrides": [
         {"matcher": {"id": "byName", "options": "result"}, "properties": [{"id": "mappings", "value": [{"type": "value", "options": {"success": {"color": "green"}, "failed": {"color": "red"}, "canceled": {"color": "orange"}}}]}]}]},
     "options": {"sortBy": [{"displayName": "jobs", "desc": True}]}}, 8, 8, 8)
nl(8)
add({"type": "timeseries", "title": "Failed jobs per host over time (spike = wedged worker)", "datasource": LOKI,
     "targets": [dict(loki('sum by (instance_id) (count_over_time(%s | event="task_end" | json | result="failed" | %s [5m]))' % (TA, INST)), legendFormat="{{instance_id}}")],
     "fieldConfig": {"defaults": {"decimals": 0, "min": 0, "custom": {"drawStyle": "bars", "fillOpacity": 60}, "color": {"mode": "palette-classic"}}, "overrides": []}}, 12, 7, 0)
add({"type": "table", "title": "Live step activity (task agent log, seconds behind real time)", "datasource": LOKI,
     "description": "Step start/end lines from the task agent as they happen, unlike CircleCI spans which arrive when the job finishes.",
     "targets": [loki('%s | event=~"step_start|step_end|task_start|task_end" | %s' % (TA, INST))],
     "transformations": [{"id": "extractFields", "options": {"source": "Line", "format": "json", "replace": True}},
                         {"id": "filterFieldsByName", "options": {"include": {"names": ["time", "msg", "job-id", "step", "step-id", "step_type", "exit_code", "duration", "result", "build_uri"]}}},
                         {"id": "organize", "options": {"renameByName": {"job-id": "job_id", "duration": "duration_ms"}}}],
     "fieldConfig": {"defaults": {}, "overrides": [{"matcher": {"id": "byName", "options": "duration_ms"}, "properties": [{"id": "unit", "value": "ms"}]},
                                                   {"matcher": {"id": "byName", "options": "build_uri"}, "properties": [{"id": "custom.hidden", "value": True}]},
                                                   links_on("job_id", link("Drill into this job", DRILL, False), link("Open job in CircleCI", "${__data.fields.build_uri}"))]},
     "options": {"sortBy": [{"displayName": "time", "desc": True}]}}, 12, 7, 12)
nl(7)

add({"type": "table", "title": "Recent jobs (wrapper job_end events): which host ran what",
     "datasource": LOKI,
     "targets": [loki('%s | event="job_end" | json | %s' % (SEL, INST))],
     "transformations": [
         {"id": "extractFields", "options": {"source": "Line", "format": "json", "replace": True, "keepTime": False}},
         {"id": "organize", "options": {"indexByName": {"ts": 0, "job_name": 1, "runner_name": 2, "instance_id": 3, "duration_ms": 4, "agent_status": 5, "project": 6, "branch": 7, "job_id": 8, "build_url": 9},
                                       "excludeByName": {"schema": True, "event": True, "sha": True, "wrapper_pid": True, "agent_pid": True, "org_id": True, "project_id": True, "pipeline_number": True, "pr_number": True, "node_index": True, "ami_id": True, "private_ip": True, "region": True, "org": True, "agent_exit_code": True, "job_number": True, "workflow_url": True, "pipeline_url": True}}}],
     "fieldConfig": {"defaults": {}, "overrides": [
         {"matcher": {"id": "byName", "options": "duration_ms"}, "properties": [{"id": "unit", "value": "ms"}]},
         {"matcher": {"id": "byName", "options": "job_id"}, "properties": [{"id": "links", "value": JOB_LINK}]},
         links_on("job_name", link("Open job in CircleCI", "${__data.fields.build_url}")),
         links_on("workflow_id", link("Open workflow in CircleCI", "${__data.fields.workflow_url}")),
         links_on("pipeline_id", link("Open pipeline in CircleCI", "${__data.fields.pipeline_url}")),
         {"matcher": {"id": "byName", "options": "workflow_url"}, "properties": [{"id": "custom.hidden", "value": True}]},
         {"matcher": {"id": "byName", "options": "pipeline_url"}, "properties": [{"id": "custom.hidden", "value": True}]},
         {"matcher": {"id": "byName", "options": "start_ms"}, "properties": [{"id": "custom.hidden", "value": True}]},
         {"matcher": {"id": "byName", "options": "end_ms"}, "properties": [{"id": "custom.hidden", "value": True}]},
         {"matcher": {"id": "byName", "options": "build_url"}, "properties": [{"id": "custom.hidden", "value": True}]}]},
     "options": {"sortBy": [{"displayName": "ts", "desc": True}]}}, 24, 9, 0)
nl(9)

# ---------------------------------------------------------------- one job
row("Drill into one job ($job_id): steps from CircleCI spans, host from the wrapper")
add({"type": "table", "title": "Where and when it ran (wrapper)", "datasource": LOKI,
     "targets": [loki('%s | json | job_id="$job_id"' % SEL)],
     "transformations": [{"id": "extractFields", "options": {"source": "Line", "format": "json", "replace": True}},
                         {"id": "filterFieldsByName", "options": {"include": {"names": ["ts", "event", "job_name", "runner_name", "hostname", "instance_id", "instance_type", "availability_zone", "resource_class", "duration_ms", "agent_status", "workflow_id", "build_url", "workflow_url", "pipeline_url"]}}}],
     "fieldConfig": {"defaults": {}, "overrides": [{"matcher": {"id": "byName", "options": "duration_ms"}, "properties": [{"id": "unit", "value": "ms"}]},
         links_on("job_name", link("Open job in CircleCI", "${__data.fields.build_url}")),
         links_on("workflow_id", link("Open workflow in CircleCI", "${__data.fields.workflow_url}"), link("Open pipeline in CircleCI", "${__data.fields.pipeline_url}")),
         {"matcher": {"id": "byRegexp", "options": "build_url|workflow_url|pipeline_url"}, "properties": [{"id": "custom.hidden", "value": True}]}]}}, 12, 6, 0)
add({"type": "table", "title": "Job result (CircleCI span)", "datasource": TEMPO,
     "targets": [traceql('{ name =~ "Job:.*" && span.com.circleci.job.id = "$job_id" } | select(span.com.circleci.job.name, span.com.circleci.job.status, span.com.circleci.resource.class, span.com.circleci.workflow.name, span.com.circleci.workflow.id)')],
     "transformations": TEMPO_FLAT,
     "fieldConfig": {"defaults": {}, "overrides": [
         links_on("job_id", link("Open job in CircleCI", APP + "/workflow/${__data.fields.workflow_id}/job/${__value.raw}")),
         links_on("job_name", link("Open job in CircleCI", APP + "/workflow/${__data.fields.workflow_id}/job/${__data.fields.job_id}")),
         links_on("workflow_id", link("Open workflow in CircleCI", APP + "/workflow/${__value.raw}"))]}}, 12, 6, 12)
nl(6)
add({"type": "table", "title": "Steps, slowest first (CircleCI step spans)", "datasource": TEMPO,
     "targets": [traceql('{ name =~ "Step:.*" && span.com.circleci.job.id = "$job_id" } | select(span.com.circleci.task.result, span.com.circleci.workflow.id)')],
     "transformations": TEMPO_FLAT,
     "fieldConfig": {"defaults": {}, "overrides": [{"matcher": {"id": "byName", "options": "duration"}, "properties": [{"id": "unit", "value": "ns"}]},
         links_on("job_id", link("Open job in CircleCI", APP + "/workflow/${__data.fields.workflow_id}/job/${__value.raw}"))]},
     "options": {"sortBy": [{"displayName": "duration", "desc": True}]}}, 12, 8, 0)
add({"type": "timeseries", "title": "Host CPU and IO wait during this job", "datasource": PROM,
     "targets": [prom('100 * (1 - avg by (instance_id) (rate(node_cpu_seconds_total{mode="idle",%s}[$__rate_interval])))' % INST, "CPU busy {{instance_id}}", ref="A"),
                 prom('100 * avg by (instance_id) (rate(node_cpu_seconds_total{mode="iowait",%s}[$__rate_interval]))' % INST, "IO wait {{instance_id}}", ref="B")],
     "fieldConfig": {"defaults": {"unit": "percent", "min": 0}, "overrides": []}}, 12, 8, 12)
nl(8)

dash = {
    "uid": "cci-runner-fleet", "title": "CircleCI runner fleet", "tags": ["circleci", "runner"],
    "timezone": "browser", "schemaVersion": 39, "refresh": "30s",
    "time": {"from": "now-3h", "to": "now"},
    "templating": {"list": [
        {"name": "instance", "label": "EC2 instance", "type": "query", "datasource": PROM,
         "query": {"query": "label_values(node_load1, instance_id)", "refId": "v"},
         "definition": "label_values(node_load1, instance_id)", "multi": True, "includeAll": True,
         "allValue": ".*", "current": {"text": "All", "value": "$__all"}, "refresh": 2},
        {"name": "job_id", "label": "Job ID", "type": "textbox", "query": "", "current": {"text": "", "value": ""}}]},
    "annotations": {"list": [
        {"name": "Job starts", "datasource": LOKI, "enable": True, "iconColor": "green",
         "expr": '%s | event="job_start" | json | %s' % (SEL, INST), "titleFormat": "job start",
         "textFormat": "{{job_name}} on {{runner}}", "tagKeys": "runner,instance_id"},
        {"name": "Job ends", "datasource": LOKI, "enable": False, "iconColor": "red",
         "expr": '%s | event="job_end" | json | %s' % (SEL, INST), "titleFormat": "job end",
         "textFormat": "{{job_name}} on {{runner}}", "tagKeys": "runner,instance_id"}]},
    "panels": panels,
}
print(json.dumps(dash, indent=1))
