---
title: Install
weight: 1
---

Install the wrapper on every host that runs a machine runner. You need machine runner 3.1.11 or later on Linux, with `bash` 4 or later and the POSIX utilities `date`, `curl`, `mkdir`, `mv` and `rm`.

1. Install the wrapper.

   ```sh
   sudo install -m 0755 bin/circleci-job-wrapper /usr/local/bin/circleci-job-wrapper
   ```

2. Create the directories. The runner user must be able to write both.

   ```sh
   sudo install -d -m 0775 -o root -g circleci /var/log/circleci-job-wrapper
   sudo install -d -m 1777 /run/circleci-job-wrapper   # or let systemd do it, see step 3
   ```

3. Install the boot-time host cache (recommended).

   ```sh
   sudo install -m 0644 systemd/circleci-job-wrapper-hostcache.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now circleci-job-wrapper-hostcache.service
   ```

4. Install log rotation (recommended).

   ```sh
   sudo install -m 0644 logrotate/circleci-job-wrapper /etc/logrotate.d/circleci-job-wrapper
   ```

5. Set the resource class (recommended). The file is parsed, never sourced.

   ```sh
   sudo install -d /etc/circleci-job-wrapper
   echo 'CCI_RESOURCE_CLASS=my-org/linux-large' | sudo tee /etc/circleci-job-wrapper/wrapper.env
   ```

6. Add the prefix to the runner config (`/etc/circleci-runner/circleci-runner-config.yaml`), then restart the runner.

   ```yaml
   runner:
     command_prefix: ["/usr/local/bin/circleci-job-wrapper"]
   ```

7. Run a job and check the log.

   ```sh
   tail -n2 /var/log/circleci-job-wrapper/jobs.jsonl
   ```

Replace `circleci` with the account and group your runner service runs as.

## What the host cache unit does

The unit runs `circleci-job-wrapper --refresh-host-cache` once per boot. It creates two directories:

- `/run/circleci-job-wrapper`, sticky with mode 1777, so runner accounts can write state files but cannot replace the root-owned `host.env`.
- `/var/log/circleci-job-wrapper`, mode 0775. Add a `Group=` in a drop-in to match the runner group.

## Several runner agents on one host

Agents on one host share the wrapper, the log file and the cache. This was tested with two systemd units (`circleci-runner` and `circleci-runner-b`), each with its own `-c` config file and `runner.name`. The wrapper reads the name from the parent's `-c` or `--config` argument, so nothing more is needed, and events from both interleave safely. Set `CCI_RUNNER_NAME` in a unit's environment only to override the name.

## Run the tests

`make check` runs shellcheck and the bats tests. It needs `bats`, `jq`, `python3` and `curl`. `strace` and `iconv` are used when present.
