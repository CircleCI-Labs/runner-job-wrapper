---
title: EC2 metadata
weight: 2
---

The wrapper reads the instance identity from one request to the instance identity document (`/latest/dynamic/instance-identity/document`).

- **The instance metadata service (IMDS) must be enabled** on the instance. On non-EC2 hosts, or with IMDS disabled, the EC2 fields are empty and nothing else changes.
- **IMDSv2 works and is recommended** (`HttpTokens=required`). The wrapper sends `PUT /latest/api/token` first and falls back to IMDSv1 only if that fails. Timeouts are 0.3 s to connect and 1 s in total per request, and proxies are bypassed.
- **A hop limit of 1 is enough** for jobs that run on the host, because the wrapper runs on the host itself. Use a hop limit of 2 only if the jobs themselves, for example containers they start, query IMDS.
- **Instance metadata tags** (`InstanceMetadataTags=enabled`) are optional and the wrapper does not read them. To put a tag such as `Team` on every event, read it once at boot (`/latest/meta-data/tags/instance/<key>`) and write it to `CCI_JOBLOG_EXTRA_FIELDS` in the operator file.

## Cache

The identity is cached in `CCI_JOBLOG_HOST_CACHE` (tmpfs by default) together with the kernel boot id, so a cache that survives in an image or a new boot is ignored.

The boot-time unit (`circleci-job-wrapper --refresh-host-cache`, 3 attempts) fills the cache, so no job ever queries IMDS. Without the unit, the first job on each boot fills it, while the job runs and never delaying its start. If the cache cannot be written, each job queries IMDS itself. A negative result (not on EC2) is cached for 300 s.
