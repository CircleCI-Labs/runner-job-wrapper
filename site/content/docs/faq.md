---
title: FAQ
weight: 12
---

## Does it change my jobs?

No. The task agent runs as a normal child. Stdin is the same pipe, signals are forwarded, and the exit status is returned exactly. If logging fails, the job does not.

## Does it slow jobs down?

About 6 ms per job. The agent starts before any telemetry runs.

## Do I need OpenTelemetry or Grafana?

No. The wrapper writes `jobs.jsonl` with nothing else. The OpenTelemetry export, a shipper and the dashboard are optional. See [what you need](../../#what-you-need).

## Is the agent_status the job result?

No. See [How it works](../how-it-works/#agent_status-is-not-the-job-result). Take the result from the CircleCI span or the task-agent journal.

## Does it work off EC2?

Yes. The EC2 fields are empty and everything else works.

## Does it work with CircleCI Server, container runner, Windows or macOS?

Not tested and not supported. The project targets machine runner 3.1.11 or later on Linux. `CCI_JOBLOG_APP_URL` exists for CircleCI Server links, but that setup was not tested.

## Why a wrapper, and not only CircleCI's OpenTelemetry spans?

The spans carry the job result and timing, but no runner or host identity. The wrapper adds the host. If CircleCI later adds that to the built-in runner telemetry, you may not need this project.

## Why is the task-agent journal pipeline experimental?

It reads the task agent's internal log lines, and that format may change between runner versions.

## Can I send events to another system?

Yes. Ship `jobs.jsonl` with any log shipper (Vector, Fluent Bit and others), or set `CCI_JOBLOG_HTTP_URL` to POST every event.

## Where do I ask for help?

See Support on the [home page](../../#support).
