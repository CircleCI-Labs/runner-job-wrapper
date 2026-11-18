---
title: How it works
weight: 2
---

## How command_prefix invokes the wrapper

With this runner config:

```yaml
runner:
  command_prefix: ["/usr/local/bin/circleci-job-wrapper"]
```

the runner executes

```text
/usr/local/bin/circleci-job-wrapper <task-agent-path> <agent args...>
```

with the job's built-in environment (`CIRCLE_*`) added and the task token on stdin. The wrapper:

1. Starts the task agent as a child with `<&0`, so stdin is the very same pipe.
2. While the job already runs, resolves the host identity and writes `job_start` and the state file. The cost to job start-up is one `fork`.
3. Waits for the child. If the wrapper itself gets `SIGTERM`, `SIGINT` or `SIGHUP`, it forwards the signal to the child.
4. Writes `job_end`, removes the state file, and exits with the child's exit code (`128+n` for a signalled child).

Every helper command the wrapper runs has `</dev/null`, so it can never take the task token from the agent's stdin. The wrapper never changes the job's environment, umask or process group.

## Overhead

About 6 ms per job. The agent is spawned before any telemetry runs. Logging is best effort: every logging failure is swallowed, and the wrapper is silent unless `CCI_JOBLOG_DEBUG` is set. It needs bash 4 or later and POSIX utilities, with no `jq`, no daemon and no Python.

## agent_status is not the job result

The task agent exits 0 even when the job fails or is cancelled from the UI. So `completed` only means the agent process exited 0. Take the job result from the CircleCI span (`com.circleci.job.status`) or, on the host, from the task agent's own "Reporting task end." log line (see [Ship with Grafana Alloy]({{< relref "/docs/send-the-data/ship-with-alloy.md" >}})).

`cancelled` only means the wrapper received `TERM`, `INT` or `HUP`, for example because the runner is stopping a task.

## Signals

When the runner stops a task, it sends `SIGTERM` to the `command_prefix` process only, not the process group. It sends `SIGKILL` to the whole process group after 10 s, or immediately with `enable_unsafe_retries`. So:

- Signal forwarding (on by default) is required. Otherwise the agent never sees the `SIGTERM`.
- If the agent has not exited within 10 s, the wrapper is killed too and `job_end` is lost. Consumers must tolerate a `job_start` without a `job_end`.
- A cancel from the CircleCI UI is handled by the agent itself (exit 0, no signal), so it shows as `completed`.

## stdin

The task token stays on the agent's stdin. The wrapper never reads or redirects it.

## Environment the runner provides

Verified on machine runner 3.1.14, these built-in variables reach the `command_prefix` process (names only):

`CIRCLE_BRANCH` `CIRCLE_BUILD_NUM` `CIRCLE_BUILD_URL` `CIRCLE_JOB` `CIRCLE_NODE_INDEX` `CIRCLE_NODE_TOTAL` `CIRCLE_ORGANIZATION_ID` `CIRCLE_PIPELINE_ID` `CIRCLE_PROJECT_ID` `CIRCLE_PROJECT_REPONAME` `CIRCLE_PROJECT_USERNAME` `CIRCLE_REPOSITORY_URL` `CIRCLE_SHA1` `CIRCLE_USERNAME` `CIRCLE_WORKFLOW_ID` `CIRCLE_WORKFLOW_JOB_ID` `CIRCLE_WORKFLOW_WORKSPACE_ID`

There is no resource class, pipeline number or PR number, so those event fields stay empty unless you supply them. For the resource class, see [Configuration]({{< relref "/docs/configure/configuration.md#resource-class" >}}).

## Multiple runners on one host

Several runner agents share one wrapper, one log file and one cache. Each event carries its `runner_name`, and each runner has its own state file. See [Install]({{< relref "/docs/get-started/install.md#several-runner-agents-on-one-host" >}}).
