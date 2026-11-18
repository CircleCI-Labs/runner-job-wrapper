---
title: Several runners, upgrades and removal
weight: 2
---

Day-two tasks for the wrapper after you have followed [Set it up end to end]({{< relref "/docs/get-started/set-up-end-to-end.md" >}}).

## Several runner agents on one host

Agents on one host share the wrapper, the log file and the cache. This was tested with two systemd units (`circleci-runner` and `circleci-runner-b`), each with its own `-c` config file and `runner.name`. The wrapper reads the name from the parent's `-c` or `--config` argument, so nothing more is needed, and events from both interleave safely. Each runner has its own state file.

Set `CCI_RUNNER_NAME` in a unit's environment only to override the name.

Check which runner wrote which event. On the runner host:

```sh
# one line per runner name seen in the last 200 events
tail -n 200 /var/log/circleci-job-wrapper/jobs.jsonl |
  jq -r .runner_name | sort | uniq -c
```

Expected output:

```text
     12 runner-a
      9 runner-b
```

If it fails: a runner with an empty name is covered in [Troubleshooting]({{< relref "/docs/operate/troubleshooting.md" >}}).

## File locations and permissions

| Path | Mode and owner | What it is |
|---|---|---|
| `/usr/local/bin/circleci-job-wrapper` | 0755, root | The wrapper |
| `/var/log/circleci-job-wrapper/` | 0775, root, runner group | `jobs.jsonl` and its rotations. The runner user must be able to write here |
| `/run/circleci-job-wrapper/` | 1777 (sticky) | State files and the root-owned `host.env` cache. Runner accounts write state files but cannot replace `host.env` |
| `/etc/circleci-job-wrapper/wrapper.env` | 0644, root | Operator settings. Parsed, never sourced |
| `/etc/systemd/system/circleci-job-wrapper-hostcache.service` | 0644, root | Boot-time host cache unit |
| `/etc/logrotate.d/circleci-job-wrapper` | 0644, root | Daily rotation |

The host cache unit runs `circleci-job-wrapper --refresh-host-cache` once per boot and creates the two directories above. If your runner group is not `circleci`, add a `Group=` line in a drop-in of the unit.

## Upgrade the wrapper

The wrapper is one file, and each job starts a fresh copy, so an upgrade needs no downtime. A job that is running keeps using the old copy. On the runner host, from an updated checkout:

```sh
# replace the script atomically
sudo install -m 0755 bin/circleci-job-wrapper \
  /usr/local/bin/circleci-job-wrapper.new
sudo mv /usr/local/bin/circleci-job-wrapper.new \
  /usr/local/bin/circleci-job-wrapper

# refresh the unit and logrotate files if they changed
sudo install -m 0644 systemd/circleci-job-wrapper-hostcache.service \
  /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart circleci-job-wrapper-hostcache.service
```

Check that the new version works. Run a job, then:

```sh
tail -n1 /var/log/circleci-job-wrapper/jobs.jsonl | jq -c '{event,schema}'
```

Expected output:

```text
{"event":"job_end","schema":1}
```

If it fails: see [Troubleshooting]({{< relref "/docs/operate/troubleshooting.md" >}}). To roll back, install the previous copy the same way.

## Uninstall

Remove the prefix first, so no job calls a missing file. On the runner host:

```sh
# 1. delete the command_prefix lines from the runner config, then
sudo systemctl restart circleci-runner

# 2. remove the wrapper, the unit, rotation and settings
sudo systemctl disable --now circleci-job-wrapper-hostcache.service
sudo rm /etc/systemd/system/circleci-job-wrapper-hostcache.service
sudo rm /etc/logrotate.d/circleci-job-wrapper
sudo rm /usr/local/bin/circleci-job-wrapper
sudo rm -r /etc/circleci-job-wrapper
sudo systemctl daemon-reload
```

The logs in `/var/log/circleci-job-wrapper` stay until you delete them.

## Run the tests

`make check` runs shellcheck and the bats tests. It needs `bats`, `jq`, `python3` and `curl`. `strace` and `iconv` are used when present.
