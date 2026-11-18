# shellcheck shell=bash disable=SC2034  # variables are consumed by the .bats files that load this
# Shared helpers for the bats tests.

bats_require_minimum_version 1.5.0

REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/.." && pwd)"
WRAPPER="$REPO_ROOT/bin/circleci-job-wrapper"
AGENT="$BATS_TEST_DIRNAME/fixtures/fake-agent"

# Isolated environment: every path lives under the per-test temp dir and no
# real network or host state is touched. Anything CIRCLE_*/CCI_*/FAKE_* from
# the invoking shell is dropped first.
common_setup() {
  local v
  for v in $(compgen -v | grep -E '^(CIRCLE_|CCI_|FAKE_)'); do unset "$v"; done
  T="$BATS_TEST_TMPDIR"
  export CCI_JOBLOG_FILE="$T/log/jobs.jsonl"
  export CCI_JOBLOG_STATE_DIR="$T/state"
  export CCI_JOBLOG_HOST_CACHE="$T/run/host.env"
  export CCI_JOBLOG_CONF="$T/none.env"
  export CCI_RUNNER_CONFIG="$T/none.yaml"
  export CCI_JOBLOG_IMDS_URL="http://127.0.0.1:9" # discard port: refused at once
  MOCK_PID=""
}

common_teardown() {
  if [[ -n ${MOCK_PID:-} ]]; then
    kill "$MOCK_PID" 2>/dev/null || true
  fi
}

# start_mock MODE: sets MOCK_URL and MOCK_LOG.
start_mock() {
  MOCK_LOG="$T/mock-requests.log"
  : >"$MOCK_LOG"
  python3 -I "$BATS_TEST_DIRNAME/mock_server.py" "$T/mock.port" "$MOCK_LOG" "$1" &
  MOCK_PID=$!
  local i
  for ((i = 0; i < 100; i++)); do
    [[ -s $T/mock.port ]] && break
    sleep 0.05
  done
  MOCK_URL="http://127.0.0.1:$(cat "$T/mock.port")"
}

# Pre-populate a valid host cache (so no IMDS access happens).
seed_cache() {
  mkdir -p "$T/run"
  cat >"$CCI_JOBLOG_HOST_CACHE" <<CACHE
ec2=yes
cached_at=$(date +%s)
instance_id=i-0cafe0000000000a1
instance_type=m6i.large
availability_zone=us-west-2c
region=us-west-2
private_ip=10.9.8.7
ami_id=ami-0feed000000000001
CACHE
}

# wait_for_file PATH: wait up to 5 s.
wait_for_file() {
  local i
  for ((i = 0; i < 100; i++)); do
    [[ -e $1 ]] && return 0
    sleep 0.05
  done
  return 1
}

# event_of FILE EVENT: print the first JSON line with .event == EVENT.
event_of() {
  jq -c --arg e "$2" 'select(.event == $e)' "$1" | head -n 1
}

# refute_grep FIXED_STRING PATH...: fail if the string occurs anywhere.
# (A plain `! grep` never fails a bats test because errexit ignores `!`.)
refute_grep() {
  if grep -rqF -- "$1" "${@:2}" 2>/dev/null; then
    echo "unexpected occurrence of '$1' in: ${*:2}" >&2
    return 1
  fi
  return 0
}

epoch_ms() {
  local t=${EPOCHREALTIME/[.,]/}
  printf '%s' "$((t / 1000))"
}
