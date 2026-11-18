---
title: Ship with Datadog Agent
weight: 9
---

{{< callout type="warning" >}}
This is documented but **not tested** in this repository.
{{< /callout >}}

See Datadog's [custom log collection](https://docs.datadoghq.com/agent/logs/#custom-log-collection) and [Prometheus host collection](https://docs.datadoghq.com/integrations/guide/prometheus-host-collection/).

1. Enable logs in `datadog.yaml`: `logs_enabled: true`.
2. Create `/etc/datadog-agent/conf.d/circleci_job_wrapper.d/conf.yaml`:

   ```yaml
   logs:
     - type: file
       path: /var/log/circleci-job-wrapper/jobs.jsonl
       service: circleci-job-wrapper
       source: circleci
   ```

   Datadog parses the JSON into attributes. Make `@job_id`, `@instance_id` and `@runner_name` facets.
3. Add the `dd-agent` user to the runner's group so it can read the file.
4. Optional: add a second `type: journald` source for the runner units, with `include_units`, to get the task agent's step and result lines. The same caveat applies: the format is internal.
5. Host metrics come from the Agent's built-in system checks. On EC2, the host is identified by its instance ID.
6. For the busy gauge, point the Agent's OpenMetrics check at node_exporter's textfile collector, or build Datadog log-based metrics from `job_start` and `job_end`.
7. CircleCI spans reach Datadog through its OTLP intake (the Agent's or a Collector's OTLP receiver, or Datadog's OTLP endpoint), using the same CircleCI exporter API as in [Ship with Grafana Alloy](../ship-with-alloy/#circleci-spans-to-grafana).
