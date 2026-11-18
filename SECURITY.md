# Security policy

## Report a vulnerability

Do not open a public issue for a security problem.

Report it privately with a [GitHub security advisory](https://github.com/CircleCI-Labs/runner-job-wrapper/security/advisories/new) on this repository. Include what you found, the steps to reproduce it, and the version or commit.

This is a CircleCI Labs project that field engineers maintain on a best-effort basis, without an SLA. We read reports and reply as soon as we can.

Vulnerabilities in the CircleCI platform or the runner agent are not in scope here. Report those through the [CircleCI security policy](https://circleci.com/security/).

## What to know about the design

The wrapper reads an allow-list of `CIRCLE_*` variables and never the task token, the environment or the agent's arguments. The [Security page](https://circleci-labs.github.io/runner-job-wrapper/docs/configure/security/) lists what it reads, writes and leaves to the operator.
