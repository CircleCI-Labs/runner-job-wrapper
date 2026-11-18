#!/usr/bin/env python3
"""Generate the 'CircleCI runner detail' and 'CircleCI resource class' dashboards.

  build_runner_dashboards.py runner [--prom UID --loki UID --tempo UID] > runner-dashboard.json
  build_runner_dashboards.py resource-class [...]                      > resource-class-dashboard.json

Keys: a runner agent is identified by its runner name (busy gauge, wrapper events)
and its systemd cgroup (cAdvisor metrics, task agent journal lines).
"""
import argparse, json

ap = argparse.ArgumentParser()
ap.add_argument("which", choices=["runner", "resource-class"])
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
WRAP = SEL + ' | log_type="wrapper"'
TA = SEL + ' | log_type="task_agent"'
JOBDASH = "/d/cci-runner-job/circleci-job-detail"
RUNDASH = "/d/cci-runner-detail/circleci-runner-detail"
RCDASH = "/d/cci-runner-rc/circleci-resource-class"

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


def unit(regex, u):
    return {"matcher": {"id": "byRegexp", "options": regex}, "properties": [{"id": "unit", "value": u}]}


def prom(expr, legend="", ref="A", instant=False, fmt="time_series"):
    t = {"datasource": PROM, "expr": expr, "legendFormat": legend, "refId": ref}
    if instant:
        t.update({"instant": True, "range": False, "format": fmt})
    return t


def loki(expr, ref="A", qtype="range", legend=""):
    t = {"datasource": LOKI, "expr": expr, "refId": ref, "queryType": qtype}
    if legend:
        t["legendFormat"] = legend
    return t


def stat(title, target, u="short", ds=None, color="text", desc=""):
    return {"type": "stat", "title": title, "datasource": ds or target["datasource"], "description": desc,
            "targets": [target], "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value", "graphMode": "none"},
            "fieldConfig": {"defaults": {"unit": u, "decimals": 0 if u == "short" else 1, "color": {"mode": "fixed", "fixedColor": color}}, "overrides": []}}


def ts(title, targets, u="short", stack=False, bars=False):
    custom = {"fillOpacity": 20}
    if stack:
        custom["stacking"] = {"mode": "normal"}
    if bars:
        custom.update({"drawStyle": "bars", "fillOpacity": 70})
    return {"type": "timeseries", "title": title, "datasource": targets[0]["datasource"], "targets": targets,
            "fieldConfig": {"defaults": {"unit": u, "min": 0, "custom": custom}, "overrides": [
                {"matcher": {"id": "byRegexp", "options": ".*failed.*"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]},
                {"matcher": {"id": "byRegexp", "options": ".*success.*"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "green"}}]},
                {"matcher": {"id": "byRegexp", "options": ".*cancel.*"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "gray"}}]}]}}


JOBS_TABLE_TX = [
    {"id": "extractFields", "options": {"source": "Line", "format": "json", "replace": True}},
    {"id": "filterFieldsByName", "options": {"include": {"names": [
        "ts", "job_name", "runner_name", "instance_id", "duration_ms", "cpu_user_ms", "cpu_sys_ms", "project", "branch",
        "job_id", "workflow_id", "pipeline_id", "build_url", "trace_id", "cgroup", "start_ms", "end_ms"]}}},
    {"id": "convertFieldType", "options": {"conversions": [{"targetField": f, "destinationType": "number"} for f in ("duration_ms", "cpu_user_ms", "cpu_sys_ms")]}}]
JOBS_TABLE_FC = {"defaults": {}, "overrides": [
    unit("duration_ms|cpu_user_ms|cpu_sys_ms", "ms"),
    links_on("job_name", link("Open job in CircleCI", APP + "/workflow/${__data.fields.workflow_id}/job/${__data.fields.job_id}")),
    links_on("job_id", link("Drill into this job (spans, steps, resources)",
                            JOBDASH + "?var-job_id=${__value.raw}&var-trace_id=${__data.fields.trace_id}&var-cgroup=${__data.fields.cgroup}&var-instance=${__data.fields.instance_id}&from=${__data.fields.start_ms}&to=${__data.fields.end_ms}", False),
             link("Open job in CircleCI", APP + "/workflow/${__data.fields.workflow_id}/job/${__data.fields.job_id}")),
    links_on("workflow_id", link("Open workflow in CircleCI", APP + "/workflow/${__value.raw}")),
    links_on("pipeline_id", link("Open pipeline in CircleCI", APP + "/pipeline/${__value.raw}")),
    links_on("runner_name", link("Open runner", RUNDASH + "?var-runner=${__value.raw}&${__url_time_range}", False)),
    hide("build_url|trace_id|cgroup|start_ms|end_ms")]}

if a.which == "runner":
    R = 'runner="$runner"'
    CG = 'cgroup="$cgroup"'
    row("Runner $runner")
    add(stat("Status now", prom('max(circleci_runner_busy{%s})' % R, instant=True)) | {
        "fieldConfig": {"defaults": {"mappings": [{"type": "value", "options": {"0": {"text": "idle", "color": "blue"}, "1": {"text": "busy", "color": "green"}}}], "color": {"mode": "thresholds"}}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background", "graphMode": "none"}}, 4, 4, 0)
    add(stat("Jobs taken (time range)", loki('sum(count_over_time(%s | event="job_start" | json | runner_name="$runner" [$__range]))' % WRAP, qtype="instant")), 4, 4, 4)
    add(stat("Failed jobs (time range)", loki('sum(count_over_time(%s | event="task_end" | json | label_format cg="/system.slice/{{.unit}}" | cg="$cgroup" | result="failed" [$__range])) or vector(0)' % TA, qtype="instant"), color="red",
             desc="From the task agent's 'Reporting task end.' log line for this runner's service (experimental)."), 4, 4, 8)
    add(stat("Busy time (time range)", prom('avg_over_time(max(circleci_runner_busy{%s})[$__range:1m])' % R, instant=True), u="percentunit",
             desc="Share of the time range this runner was running a job."), 4, 4, 12)
    add(stat("CPU time used by jobs", loki('sum(sum_over_time(%s | event="job_end" | json | runner_name="$runner" | unwrap cpu_user_ms [$__range]))' % WRAP, qtype="instant"), u="ms",
             desc="User CPU of all jobs on this runner (wrapper, from rusage)."), 4, 4, 16)
    add(stat("Median job duration", loki('quantile_over_time(0.5, %s | event="job_end" | json | runner_name="$runner" | unwrap duration_ms [$__range]) by (runner_name)' % WRAP, qtype="instant"), u="ms"), 4, 4, 20)
    nl(4)
    add({"type": "table", "title": "Running now", "datasource": PROM,
         "targets": [prom('max by (runner, instance_id, resource_class, cgroup, job_name, project, job_id, workflow_id) (circleci_runner_busy{%s})' % R, instant=True, fmt="table", ref="A"),
                     prom('time() - max by (runner, instance_id, resource_class, cgroup, job_name, project, job_id, workflow_id) (circleci_runner_job_start_time_seconds{%s})' % R, instant=True, fmt="table", ref="B")],
         "transformations": [{"id": "merge", "options": {}},
                             {"id": "organize", "options": {"excludeByName": {"Time": True}, "renameByName": {"Value #A": "busy", "Value #B": "running for"}}}],
         "fieldConfig": {"defaults": {}, "overrides": [
             unit("running for", "s"),
             {"matcher": {"id": "byName", "options": "busy"}, "properties": [
                 {"id": "mappings", "value": [{"type": "value", "options": {"0": {"text": "idle", "color": "blue"}, "1": {"text": "busy", "color": "green"}}}]},
                 {"id": "custom.cellOptions", "value": {"type": "color-background"}}]},
             links_on("job_name", link("Open running job in CircleCI", APP + "/workflow/${__data.fields.workflow_id}/job/${__data.fields.job_id}")),
             links_on("resource_class", link("Open resource class", RCDASH + "?var-rc=${__value.raw}&${__url_time_range}", False)),
             links_on("job_id", link("Drill into this job", JOBDASH + "?var-job_id=${__value.raw}&from=now-1h&to=now", False))]}}, 24, 4, 0)
    nl(4)
    row("Resources")
    add(ts("Runner CPU (cores), runner service cgroup", [prom('sum(rate(container_cpu_usage_seconds_total{%s}[$__rate_interval]))' % CG, "$runner")]), 8, 7, 0)
    add(ts("Runner memory (working set)", [prom('sum(container_memory_working_set_bytes{%s})' % CG, "$runner")], u="bytes"), 8, 7, 8)
    add(ts("Busy (1) / idle (0)", [prom('max(circleci_runner_busy{%s})' % R, "$runner")]) | {
        "fieldConfig": {"defaults": {"min": 0, "max": 1, "custom": {"drawStyle": "line", "lineInterpolation": "stepAfter", "fillOpacity": 40}}, "overrides": []}}, 8, 7, 16)
    nl(7)
    add(ts("Host CPU busy % (whole host)", [prom('100 * (1 - avg by (instance_id) (rate(node_cpu_seconds_total{mode="idle",instance_id="$instance"}[$__rate_interval])))', "{{instance_id}}")], u="percent"), 8, 7, 0)
    add(ts("Host IO wait %", [prom('100 * avg by (instance_id) (rate(node_cpu_seconds_total{mode="iowait",instance_id="$instance"}[$__rate_interval]))', "{{instance_id}}")], u="percent"), 8, 7, 8)
    add(ts("Host memory used %", [prom('100 * (1 - node_memory_MemAvailable_bytes{instance_id="$instance"} / node_memory_MemTotal_bytes{instance_id="$instance"})', "{{instance_id}}")], u="percent"), 8, 7, 16)
    nl(7)
    row("Jobs this runner took")
    add(ts("Jobs taken over time", [loki('sum(count_over_time(%s | event="job_start" | json | runner_name="$runner" [5m]))' % WRAP, legend="jobs started")], bars=True), 8, 7, 0)
    add(ts("Job results over time (task agent log)", [loki('sum by (result) (count_over_time(%s | event="task_end" | json | label_format cg="/system.slice/{{.unit}}" | cg="$cgroup" | result!="" [5m]))' % TA, legend="{{result}}")], bars=True, stack=True), 8, 7, 8)
    add(ts("Job duration", [loki('max by (job_name) (max_over_time(%s | event="job_end" | json | runner_name="$runner" | unwrap duration_ms [5m]))' % WRAP, legend="{{job_name}}")], u="ms") | {
        "fieldConfig": {"defaults": {"unit": "ms", "min": 0, "custom": {"drawStyle": "points", "pointSize": 8}}, "overrides": []}}, 8, 7, 16)
    nl(7)
    add({"type": "table", "title": "Jobs (newest first)", "datasource": LOKI,
         "targets": [loki('%s | event="job_end" | json | runner_name="$runner"' % WRAP)],
         "transformations": JOBS_TABLE_TX, "fieldConfig": JOBS_TABLE_FC,
         "options": {"sortBy": [{"displayName": "ts", "desc": True}]}}, 24, 10, 0)
    nl(10)
    tmpl = [
        {"name": "runner", "label": "Runner", "type": "query", "datasource": PROM, "refresh": 2,
         "query": {"query": "label_values(circleci_runner_busy, runner)", "refId": "r"}, "definition": "label_values(circleci_runner_busy, runner)"},
        {"name": "cgroup", "label": "cgroup", "type": "query", "datasource": PROM, "refresh": 2, "hide": 0,
         "query": {"query": 'label_values(circleci_runner_busy{runner="$runner"}, cgroup)', "refId": "c"}, "definition": 'label_values(circleci_runner_busy{runner="$runner"}, cgroup)'},
        {"name": "instance", "label": "EC2 instance", "type": "query", "datasource": PROM, "refresh": 2,
         "query": {"query": 'label_values(circleci_runner_busy{runner="$runner"}, instance_id)', "refId": "i"}, "definition": 'label_values(circleci_runner_busy{runner="$runner"}, instance_id)'}]
    dash = {"uid": "cci-runner-detail", "title": "CircleCI runner detail"}
    annot = '%s | json | runner_name="$runner"' % WRAP
else:
    RC = 'resource_class="$rc"'
    INST_IN_RC = 'and on (instance_id) max by (instance_id) (circleci_runner_busy{%s})' % RC
    SP = 'span.com.circleci.resource.class = "$rc"'

    def tq(q, ref="A", instant=True, legend=""):
        t = {"datasource": TEMPO, "queryType": "traceql", "query": q, "refId": ref, "metricsQueryType": "instant" if instant else "range", "step": "5m"}
        if legend:
            t["legendFormat"] = legend
        return t

    row("Resource class $rc")
    add(stat("Runners", prom('count(max by (runner) (circleci_runner_busy{%s}))' % RC, instant=True)), 4, 4, 0)
    add(stat("Busy now", prom('sum(max by (runner) (circleci_runner_busy{%s}))' % RC, instant=True), color="green"), 4, 4, 4)
    add(stat("Utilization (time range)", prom('avg_over_time((sum(circleci_runner_busy{%s}) / count(circleci_runner_busy{%s}))[$__range:1m])' % (RC, RC), instant=True), u="percentunit",
             desc="Average share of this class's runners that were busy."), 4, 4, 8)
    add(stat("Jobs (time range)", tq('{ name =~ "Job:.*" && %s } | count_over_time()' % SP)) | {
        "options": {"reduceOptions": {"calcs": ["sum"]}, "colorMode": "value", "graphMode": "none"}}, 4, 4, 12)
    add(stat("Median job duration", tq('{ name =~ "Job:.*" && %s } | quantile_over_time(duration, .5)' % SP), u="s") | {
        "options": {"reduceOptions": {"calcs": ["mean"]}, "colorMode": "value", "graphMode": "none"}}, 4, 4, 16)
    add(stat("P95 job duration", tq('{ name =~ "Job:.*" && %s } | quantile_over_time(duration, .95)' % SP), u="s") | {
        "options": {"reduceOptions": {"calcs": ["mean"]}, "colorMode": "value", "graphMode": "none"}}, 4, 4, 20)
    nl(4)
    add({"type": "table", "title": "Runners in this class", "datasource": PROM,
         "targets": [prom('max by (runner, instance_id, cgroup, job_name, project, job_id, workflow_id) (circleci_runner_busy{%s})' % RC, instant=True, fmt="table", ref="A"),
                     prom('max by (runner) (rate(container_cpu_usage_seconds_total{cgroup=~"/system.slice/circleci-runner.*"}[5m]) * on (cgroup) group_left (runner) max by (cgroup, runner) (circleci_runner_busy{%s}))' % RC, instant=True, fmt="table", ref="B")],
         "transformations": [{"id": "merge", "options": {}},
                             {"id": "organize", "options": {"excludeByName": {"Time": True, "cgroup": True}, "renameByName": {"Value #A": "busy", "Value #B": "CPU cores now"},
                                                            "indexByName": {"runner": 0, "busy": 1, "job_name": 2, "CPU cores now": 3, "instance_id": 4}}}],
         "fieldConfig": {"defaults": {}, "overrides": [
             {"matcher": {"id": "byName", "options": "busy"}, "properties": [
                 {"id": "mappings", "value": [{"type": "value", "options": {"0": {"text": "idle", "color": "blue"}, "1": {"text": "busy", "color": "green"}}}]},
                 {"id": "custom.cellOptions", "value": {"type": "color-background"}}]},
             {"matcher": {"id": "byName", "options": "CPU cores now"}, "properties": [{"id": "decimals", "value": 2}]},
             links_on("runner", link("Open runner", RUNDASH + "?var-runner=${__value.raw}&${__url_time_range}", False)),
             links_on("job_name", link("Open running job in CircleCI", APP + "/workflow/${__data.fields.workflow_id}/job/${__data.fields.job_id}")),
             links_on("job_id", link("Drill into this job", JOBDASH + "?var-job_id=${__value.raw}&from=now-1h&to=now", False))]}}, 24, 6, 0)
    nl(6)
    row("Capacity and load")
    add(ts("Busy runners vs runners", [prom('sum(circleci_runner_busy{%s})' % RC, "busy", ref="A"), prom('count(circleci_runner_busy{%s})' % RC, "runners", ref="B")]), 8, 7, 0)
    add(ts("Jobs started per runner", [loki('sum by (runner_name) (count_over_time(%s | event="job_start" | json | resource_class="$rc" [5m]))' % WRAP, legend="{{runner_name}}")], bars=True, stack=True), 8, 7, 8)
    add(ts("Job results (CircleCI spans)", [tq('{ name =~ "Job:.*" && %s } | count_over_time() by (span.com.circleci.job.status)' % SP, instant=False, legend="{{span.com.circleci.job.status}}")], bars=True, stack=True), 8, 7, 16)
    nl(7)
    add(ts("Host CPU busy % (hosts in this class)", [prom('100 * (1 - avg by (instance_id) (rate(node_cpu_seconds_total{mode="idle"}[$__rate_interval]))) %s' % INST_IN_RC, "{{instance_id}}")], u="percent"), 8, 7, 0)
    add(ts("Runner CPU (cores) per runner", [prom('sum by (runner) (rate(container_cpu_usage_seconds_total{cgroup=~"/system.slice/circleci-runner.*"}[$__rate_interval]) * on (cgroup) group_left (runner) max by (cgroup, runner) (circleci_runner_busy{%s}))' % RC, "{{runner}}")]), 8, 7, 8)
    add(ts("Runner memory per runner", [prom('sum by (runner) (container_memory_working_set_bytes{cgroup=~"/system.slice/circleci-runner.*"} * on (cgroup) group_left (runner) max by (cgroup, runner) (circleci_runner_busy{%s}))' % RC, "{{runner}}")], u="bytes"), 8, 7, 16)
    nl(7)
    row("Jobs in this class")
    add({"type": "table", "title": "Slowest jobs in this class (CircleCI spans)", "datasource": TEMPO,
         "targets": [{"datasource": TEMPO, "queryType": "traceql", "refId": "A", "limit": 500, "spss": 100, "tableType": "spans", "streaming": False,
                      "query": '{ name =~ "Job:.*" && %s } | select(span.com.circleci.job.name, span.com.circleci.job.status)' % SP}],
         "transformations": [{"id": "merge", "options": {}},
                             {"id": "groupBy", "options": {"fields": {"com.circleci.job.name": {"aggregations": [], "operation": "groupby"},
                                                                      "duration": {"aggregations": ["count", "p50", "p95", "max"], "operation": "aggregate"}}}},
                             {"id": "organize", "options": {"renameByName": {"com.circleci.job.name": "job", "duration (count)": "runs", "duration (p50)": "median", "duration (p95)": "p95", "duration (max)": "max"}}},
                             {"id": "sortBy", "options": {"sort": [{"field": "median", "desc": True}]}}],
         "fieldConfig": {"defaults": {}, "overrides": [unit("median|p95|max", "ns")]}}, 10, 10, 0)
    add({"type": "table", "title": "Recent jobs in this class (wrapper)", "datasource": LOKI,
         "targets": [loki('%s | event="job_end" | json | resource_class="$rc"' % WRAP)],
         "transformations": JOBS_TABLE_TX, "fieldConfig": JOBS_TABLE_FC,
         "options": {"sortBy": [{"displayName": "ts", "desc": True}]}}, 14, 10, 10)
    nl(10)
    tmpl = [{"name": "rc", "label": "Resource class", "type": "query", "datasource": PROM, "refresh": 2,
             "query": {"query": "label_values(circleci_runner_busy, resource_class)", "refId": "rc"}, "definition": "label_values(circleci_runner_busy, resource_class)"}]
    dash = {"uid": "cci-runner-rc", "title": "CircleCI resource class"}
    annot = '%s | event="job_start" | json | resource_class="$rc"' % WRAP

dash.update({
    "tags": ["circleci", "runner"], "timezone": "browser", "schemaVersion": 39, "refresh": "30s",
    "time": {"from": "now-3h", "to": "now"},
    "links": [{"title": "Runner fleet", "type": "link", "url": "/d/cci-runner-fleet/circleci-runner-fleet", "icon": "dashboard", "keepTime": True},
              {"title": "Resource class", "type": "link", "url": RCDASH, "icon": "dashboard", "keepTime": True},
              {"title": "Runner detail", "type": "link", "url": RUNDASH, "icon": "dashboard", "keepTime": True},
              {"title": "Job detail", "type": "link", "url": JOBDASH, "icon": "dashboard", "keepTime": True}],
    "templating": {"list": tmpl},
    "annotations": {"list": [{"name": "Jobs", "datasource": LOKI, "enable": True, "iconColor": "green", "expr": annot,
                              "titleFormat": "{{event}}", "textFormat": "{{job_name}} on {{runner_name}}"}]},
    "panels": panels})
print(json.dumps(dash, indent=1))
