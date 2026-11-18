# Contributing

Thank you for helping. This is a CircleCI Labs project, so reviews happen on a best-effort basis.

## Before you start

Open an issue for a larger change, so we can agree on the approach first. Do not put customer data, tokens or internal hostnames in issues, commits or examples.

## Check your change

```sh
make check
```

This runs shellcheck and the bats tests. You need `bats`, `shellcheck`, `jq`, `python3` and `curl`. `strace` and `iconv` are used when present. Add or update a test with every behavior change.

## Commits and pull requests

- Use [conventional commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
- Keep a pull request to one logical change, and update the docs in `site/content/` and `CHANGELOG.md` with it.
- CI must pass.

## Docs site

The site in `site/` uses Hugo extended 0.168.0 and the Hextra theme. Build it with `site/build.sh` and commit the generated `docs/` folder with your change.

## Security

Report vulnerabilities as described in [SECURITY.md](SECURITY.md), not in a public issue.
