---
title: Troubleshooting
weight: 12
---

The wrapper never fails a job over logging, so a problem usually shows up as missing data, not as an error. Turn on diagnostics first: set `CCI_JOBLOG_DEBUG=1` in the runner service environment, restart the runner, and read the runner's journal.

## jobs.jsonl is missing or empty

1. Check that the runner uses the wrapper: `command_prefix` in the runner config must be `["/usr/local/bin/circleci-job-wrapper"]`, and the runner must have been restarted after the change.
2. Check that the file is executable: `ls -l /usr/local/bin/circleci-job-wrapper`.
3. Check that `CCI_JOBLOG_DISABLE` is not set in the runner's environment.
4. Check the permissions below.

## Permission denied on the log directory

The wrapper appends as the runner user, and skips logging silently if it cannot write. Check that `/var/log/circleci-job-wrapper` is writable by that user:

```sh
sudo -u circleci test -w /var/log/circleci-job-wrapper && echo writable
```

Replace `circleci` with your runner user. Fix it with a group-writable directory (mode 0775, owned by the runner group), or a `Group=` drop-in for the host cache unit. If logrotate recreated the file as root, switch to `copytruncate` as in the shipped config.

## EC2 fields are empty

- Check that IMDS is enabled on the instance, and that you are on EC2. See [EC2 metadata](../ec2-metadata/).
- Check the cache: `cat /run/circleci-job-wrapper/host.env` (it contains the instance identity, not secrets). If the unit failed, run `systemctl status circleci-job-wrapper-hostcache.service`.
- A negative result is cached for 300 s. After you fix IMDS, run `sudo /usr/local/bin/circleci-job-wrapper --refresh-host-cache`.

## runner_name is empty or the state file is called pid-NNN.json

The wrapper could not find `runner.name`. Set `CCI_RUNNER_NAME` in the runner's environment or the operator file, or check that the runner config has a `name:` key directly under `runner:`. See [Configuration](../configuration/#runner-name).

## resource_class is empty

The runner does not tell the wrapper its resource class. Set `CCI_RESOURCE_CLASS` in the operator file. See [Configuration](../configuration/#resource-class).

## A job_start has no job_end

This is expected when the runner kills the wrapper with `SIGKILL`. See [How it works](../how-it-works/#signals). Treat a state file whose `wrapper_pid` is gone as stale.

## Alloy cannot read the log or the journal

- Add the `alloy` user to the runner's group so it can read `jobs.jsonl`, and restart Alloy.
- For the journal pipeline, add `alloy` to the `systemd-journal` group.
- Make the `CCI_JOBLOG_PROM_DIR` directory readable by `alloy`.
- Check that `matches` in `config.alloy` lists your runner units.

Then read the Alloy log for `permission denied` or `no such file`.
