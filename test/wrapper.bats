#!/usr/bin/env bats
# Behavioural tests: the wrapper is executed exactly as the runner would.

load test_helper

setup() { common_setup; }
teardown() { common_teardown; }

# --- exit status -----------------------------------------------------------

@test "exit status 0 is passed through" {
  seed_cache
  run "$WRAPPER" "$AGENT"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "exit status 1 is passed through" {
  seed_cache
  FAKE_EXIT=1 run "$WRAPPER" "$AGENT"
  [ "$status" -eq 1 ]
}

@test "exit status 137 (explicit) is passed through and logged as agent_error" {
  seed_cache
  FAKE_EXIT=137 run "$WRAPPER" "$AGENT"
  [ "$status" -eq 137 ]
  run jq -e 'select(.event == "job_end") | .agent_exit_code == 137 and .agent_status == "agent_error"' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
}

@test "agent killed by SIGKILL yields 137 and the end event is still written" {
  seed_cache
  FAKE_KILL9=1 run "$WRAPPER" "$AGENT"
  [ "$status" -eq 137 ]
  run jq -e 'select(.event == "job_end") | .agent_exit_code == 137 and .agent_status == "agent_error"' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
}

@test "missing agent binary returns 127 like a direct exec" {
  seed_cache
  run -127 "$WRAPPER" "$T/does-not-exist"
}

@test "no arguments: usage and status 2" {
  run "$WRAPPER"
  [ "$status" -eq 2 ]
}

# --- stdin -----------------------------------------------------------------

@test "stdin reaches the agent untouched (including large input)" {
  seed_cache
  head -c 300000 /dev/urandom >"$T/in.bin"
  FAKE_STDIN_OUT="$T/out.bin" "$WRAPPER" "$AGENT" <"$T/in.bin"
  cmp "$T/in.bin" "$T/out.bin"
}

@test "stdin from a pipe reaches the agent, even with IMDS unreachable" {
  printf 'token-line\nsecond line' | FAKE_STDIN_OUT="$T/out.txt" "$WRAPPER" "$AGENT"
  [ "$(cat "$T/out.txt")" = $'token-line\nsecond line' ]
}

@test "stdin that arrives late is still delivered" {
  seed_cache
  (
    sleep 0.5
    printf 'late-data'
  ) | FAKE_STDIN_OUT="$T/out.txt" "$WRAPPER" "$AGENT"
  [ "$(cat "$T/out.txt")" = "late-data" ]
}

# --- events ----------------------------------------------------------------

@test "job_start and job_end are valid JSON with the expected fields" {
  seed_cache
  export CIRCLE_WORKFLOW_JOB_ID=job-uuid-1 CIRCLE_JOB=build CIRCLE_BUILD_NUM=42 \
    CIRCLE_WORKFLOW_ID=wf-uuid CIRCLE_PIPELINE_ID=pl-uuid CIRCLE_PIPELINE_NUMBER=7 \
    CIRCLE_PROJECT_REPONAME=widgets CIRCLE_PROJECT_USERNAME=example-org \
    CIRCLE_BRANCH=main CIRCLE_SHA1=0123abc CIRCLE_BUILD_URL=https://example.test/jobs/42 \
    CIRCLE_NODE_INDEX=3 CIRCLE_PR_NUMBER=99 CCI_RUNNER_NAME=runner-a CCI_RESOURCE_CLASS=ns/large
  "$WRAPPER" "$AGENT"
  [ "$(wc -l <"$CCI_JOBLOG_FILE")" -eq 2 ]
  jq -e . "$CCI_JOBLOG_FILE" >/dev/null
  run jq -e -s '
    .[0].event == "job_start" and .[1].event == "job_end"
    and (.[0].schema == 1)
    and (.[0].ts | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\\.[0-9]{3}Z$"))
    and (.[1].ts >= .[0].ts)
    and (.[] | .job_id == "job-uuid-1" and .job_name == "build" and .job_number == "42"
         and .workflow_id == "wf-uuid" and .pipeline_id == "pl-uuid" and .pipeline_number == "7"
         and .project == "widgets" and .org == "example-org" and .branch == "main"
         and .sha == "0123abc" and .build_url == "https://example.test/jobs/42"
         and .node_index == "3" and .pr_number == "99"
         and .instance_id == "i-0cafe0000000000a1" and .instance_type == "m6i.large"
         and .availability_zone == "us-west-2c" and .region == "us-west-2"
         and .private_ip == "10.9.8.7" and .ami_id == "ami-0feed000000000001"
         and .runner_name == "runner-a" and .resource_class == "ns/large"
         and (.hostname | length > 0)
         and (.wrapper_pid | type == "number") and (.agent_pid | type == "number"))
    and (.[1].agent_exit_code == 0 and .[1].agent_status == "completed" and (.[1].duration_ms | type == "number"))
    and (.[0] | has("exit_code") | not)
  ' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
}

@test "missing CIRCLE_* variables become empty strings; the log is still valid" {
  seed_cache
  "$WRAPPER" "$AGENT"
  run jq -e -s '.[0].job_id == "" and .[0].branch == "" and .[0].pr_number == ""' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
}

@test "duration_ms reflects the job run time" {
  seed_cache
  FAKE_SLEEP=0.4 "$WRAPPER" "$AGENT"
  run jq -e 'select(.event == "job_end") | .duration_ms >= 400 and .duration_ms < 3000' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
}

@test "special characters, newlines, quotes, control chars and emoji stay valid JSON" {
  seed_cache
  local name branch
  name=$'say "hi"\\ back\nnew\tline\r\x01\x1f end 🚀 ünï'
  branch=$'feat/"q"\n\\x😀'
  CIRCLE_JOB="$name" CIRCLE_BRANCH="$branch" "$WRAPPER" "$AGENT"
  [ "$(wc -l <"$CCI_JOBLOG_FILE")" -eq 2 ]
  run jq -e --arg n "$name" --arg b "$branch" \
    '.job_name == $n and .branch == $b' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
}

@test "very long values are truncated, never inside a UTF-8 character; lines stay < 4 KiB" {
  seed_cache
  local long="" i
  for ((i = 0; i < 200; i++)); do long+="🚀é"; done
  CIRCLE_JOB="$long" CIRCLE_BRANCH="$long" CIRCLE_BUILD_URL="$long" \
    CCI_JOBLOG_EXTRA_FIELDS="a=$long,b=$long,c=$long" "$WRAPPER" "$AGENT"
  [ "$(LC_ALL=C awk '{ if (length($0) > m) m = length($0) } END { print m }' "$CCI_JOBLOG_FILE")" -lt 4000 ]
  iconv -f UTF-8 -t UTF-8 "$CCI_JOBLOG_FILE" >/dev/null
  jq -e . "$CCI_JOBLOG_FILE" >/dev/null
}

@test "CCI_JOBLOG_EXTRA_FIELDS are merged as strings; reserved and secret-like keys are skipped" {
  seed_cache
  CCI_JOBLOG_EXTRA_FIELDS='team=infra, pool=bazel,event=evil,api_token=zzz,n=5' "$WRAPPER" "$AGENT"
  run jq -e -s '
    all(.[]; .team == "infra" and .pool == "bazel" and .n == "5" and (has("api_token") | not))
    and .[0].event == "job_start"' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
  refute_grep zzz "$CCI_JOBLOG_FILE"
}

# --- signals ---------------------------------------------------------------

@test "SIGTERM sent to the wrapper only is forwarded; status cancelled, exit 143" {
  seed_cache
  FAKE_READY="$T/ready" FAKE_SLEEP=30 "$WRAPPER" "$AGENT" &
  local pid=$!
  wait_for_file "$T/ready"
  kill -TERM "$pid"
  local rc=0
  wait "$pid" || rc=$?
  [ "$rc" -eq 143 ]
  run jq -e 'select(.event == "job_end") | .agent_status == "cancelled" and .agent_exit_code == 143' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
  [ "$(wc -l <"$CCI_JOBLOG_FILE")" -eq 2 ]
}

@test "SIGINT is delivered to the agent (not ignored) and recorded as cancelled" {
  seed_cache
  # (a shell starts background jobs with SIGINT ignored; the runner does not)
  FAKE_READY="$T/ready" FAKE_SLEEP=30 env --default-signal=INT "$WRAPPER" "$AGENT" &
  local pid=$!
  wait_for_file "$T/ready"
  kill -INT "$pid"
  local rc=0
  wait "$pid" || rc=$?
  [ "$rc" -eq 130 ]
  run jq -e 'select(.event == "job_end") | .agent_status == "cancelled"' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
}

@test "SIGHUP is forwarded and recorded as cancelled" {
  seed_cache
  FAKE_READY="$T/ready" FAKE_SLEEP=30 "$WRAPPER" "$AGENT" &
  local pid=$!
  wait_for_file "$T/ready"
  kill -HUP "$pid"
  local rc=0
  wait "$pid" || rc=$?
  [ "$rc" -eq 129 ]
  run jq -e 'select(.event == "job_end") | .agent_status == "cancelled"' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
}

@test "SIGTERM to the whole process group (what the runner does) works" {
  seed_cache
  FAKE_READY="$T/ready" FAKE_SLEEP=30 setsid "$WRAPPER" "$AGENT" &
  local pid=$!
  wait_for_file "$T/ready"
  kill -TERM -- "-$pid"
  local rc=0
  wait "$pid" || rc=$?
  [ "$rc" -eq 143 ]
  run jq -e 'select(.event == "job_end") | .agent_status == "cancelled"' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
  [ -z "$(ls -A "$CCI_JOBLOG_STATE_DIR")" ]
}

@test "a signal during slow startup telemetry is still forwarded" {
  # Cold cache and a hanging metadata service: telemetry takes > 1 s.
  start_mock hang
  CCI_JOBLOG_IMDS_URL="$MOCK_URL" FAKE_READY="$T/ready" FAKE_SLEEP=30 "$WRAPPER" "$AGENT" &
  local pid=$!
  wait_for_file "$T/ready"
  kill -TERM "$pid"
  local rc=0
  wait "$pid" || rc=$?
  [ "$rc" -eq 143 ]
}

# --- failure isolation -----------------------------------------------------

@test "unwritable log directory does not fail the job, and is silent" {
  seed_cache
  mkdir -p "$T/ro"
  chmod 555 "$T/ro"
  CCI_JOBLOG_FILE="$T/ro/sub/jobs.jsonl" CCI_JOBLOG_STATE_DIR="$T/ro/state" FAKE_EXIT=3 run "$WRAPPER" "$AGENT"
  chmod 755 "$T/ro"
  [ "$status" -eq 3 ]
  [ -z "$output" ]
}

@test "log path under a non-directory is silently skipped" {
  seed_cache
  CCI_JOBLOG_FILE=/dev/null/x/jobs.jsonl CCI_JOBLOG_STATE_DIR=/dev/null/y CCI_JOBLOG_HOST_CACHE=/dev/null/z/h.env \
    FAKE_EXIT=5 run "$WRAPPER" "$AGENT"
  [ "$status" -eq 5 ]
  [ -z "$output" ]
}

@test "log file that is a directory is silently skipped" {
  seed_cache
  mkdir -p "$T/asdir"
  CCI_JOBLOG_FILE="$T/asdir" run "$WRAPPER" "$AGENT"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "missing IMDS: job runs, EC2 fields are empty, wrapper is silent" {
  run "$WRAPPER" "$AGENT"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  run jq -e -s 'all(.[]; .instance_id == "" and .region == "" and .ami_id == "")' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
  grep -q '^ec2=no$' "$CCI_JOBLOG_HOST_CACHE"
}

@test "hanging IMDS does not delay the start of the job" {
  start_mock hang
  local t0 t1
  t0=$(epoch_ms)
  CCI_JOBLOG_IMDS_URL="$MOCK_URL" FAKE_READY="$T/ready" "$WRAPPER" "$AGENT" </dev/null &
  local pid=$!
  wait_for_file "$T/ready"
  t1=$(epoch_ms)
  echo "# agent started after $((t1 - t0)) ms with a hanging IMDS" >&3
  ((t1 - t0 < 400))
  wait "$pid"
  # the whole run is bounded by the curl timeouts
  (($(epoch_ms) - t0 < 4000))
}

@test "debug mode writes to stderr; default mode writes nothing" {
  run --separate-stderr "$WRAPPER" "$AGENT"
  [ -z "$output" ]
  [ -z "$stderr" ]
  CCI_JOBLOG_DEBUG=1 run --separate-stderr "$WRAPPER" "$AGENT"
  [ -z "$output" ]
  [[ $stderr == *circleci-job-wrapper:* ]]
}

@test "CCI_JOBLOG_DISABLE runs the agent directly with no telemetry" {
  CCI_JOBLOG_DISABLE=1 FAKE_EXIT=4 run "$WRAPPER" "$AGENT"
  [ "$status" -eq 4 ]
  [ ! -e "$CCI_JOBLOG_FILE" ]
}

@test "the job environment is not polluted by wrapper internals" {
  seed_cache
  export LC_ALL=C.UTF-8 LANG=C.UTF-8
  CIRCLE_JOB=$'x\x01"y' FAKE_ENV_OUT="$T/env.out" "$WRAPPER" "$AGENT"
  grep -qx 'LC_ALL=C.UTF-8' "$T/env.out"
  grep -qx 'LANG=C.UTF-8' "$T/env.out"
  run grep -E '^(HOST_|KV=|RUNNER_NAME|COMMON|FRAG|START_MS|CCI_WRAPPER_VERSION|SCHEMA_VERSION)' "$T/env.out"
  [ "$status" -ne 0 ]
}

# --- concurrency -----------------------------------------------------------

@test "20 concurrent wrappers produce no corrupted lines" {
  seed_cache
  local big="" i
  for ((i = 0; i < 40; i++)); do big+='line "with" quotes\and 😀 '; done # ~1.5 KB job name
  for ((i = 0; i < 20; i++)); do
    CIRCLE_JOB="$big" CIRCLE_BUILD_NUM="$i" CCI_RUNNER_NAME="runner-$i" FAKE_SLEEP=0.2 "$WRAPPER" "$AGENT" &
  done
  wait
  [ "$(wc -l <"$CCI_JOBLOG_FILE")" -eq 40 ]
  jq -e . "$CCI_JOBLOG_FILE" >/dev/null
  run jq -s '[.[] | select(.event == "job_start")] | length' "$CCI_JOBLOG_FILE"
  [ "$output" -eq 20 ]
  run jq -s '[.[].job_number] | unique | length' "$CCI_JOBLOG_FILE"
  [ "$output" -eq 20 ]
  [ "$(LC_ALL=C awk '{ if (length($0) > m) m = length($0) } END { print m }' "$CCI_JOBLOG_FILE")" -lt 4000 ]
  [ -z "$(ls -A "$CCI_JOBLOG_STATE_DIR")" ]
}

@test "each event is written with a single write(2)" {
  command -v strace >/dev/null || skip "strace not installed"
  seed_cache
  strace -f -qq -s 8192 -e trace=write -o "$T/strace.out" "$WRAPPER" "$AGENT" || skip "strace not permitted"
  # strace escapes the quotes: "event":"job_start" appears as \"event\":\"job_start\"
  [ "$(grep -c 'event.*job_start' "$T/strace.out")" -eq 1 ]
  [ "$(grep -c 'event.*job_end' "$T/strace.out")" -eq 1 ]
  # each of those writes carries the complete line, newline included
  [ "$(grep 'event.*job_\(start\|end\)' "$T/strace.out" | grep -c '}\\n"')" -eq 2 ]
}

# --- secrets ---------------------------------------------------------------

@test "no secrets or agent arguments leak into any output" {
  seed_cache
  cat >"$T/runner.yaml" <<'YAML'
api:
  auth_token: FAKE-CONFIG-TOKEN-5551212
  url: https://runner.example.test
runner:
  name: leak-test-runner
  working_directory: /tmp/x
YAML
  export CCI_RUNNER_CONFIG="$T/runner.yaml"
  export CIRCLE_TOKEN=FAKE-ENV-TOKEN-8675309 CIRCLE_OIDC_TOKEN=FAKE-OIDC-TOKEN-1 \
    CCI_AUTH_TOKEN=FAKE-CCI-TOKEN-2 AWS_SECRET_ACCESS_KEY=FAKE-AWS-SECRET-3
  CCI_JOBLOG_DEBUG=1 run --separate-stderr "$WRAPPER" "$AGENT" --token FAKE-ARG-TOKEN-4242 --secret=FAKE-ARG-SECRET-7
  [ "$status" -eq 0 ]
  local s
  for s in FAKE-CONFIG-TOKEN FAKE-ENV-TOKEN FAKE-OIDC FAKE-CCI-TOKEN FAKE-AWS-SECRET FAKE-ARG-TOKEN FAKE-ARG-SECRET 5551212 auth_token; do
    refute_grep "$s" "$CCI_JOBLOG_FILE" "$CCI_JOBLOG_HOST_CACHE"
    [[ $output != *"$s"* ]]
    [[ $stderr != *"$s"* ]]
  done
  # the state file only exists while a job runs, so inspect it then as well
  FAKE_READY="$T/ready" FAKE_SLEEP=30 "$WRAPPER" "$AGENT" --token FAKE-ARG-TOKEN-4242 &
  local pid=$!
  wait_for_file "$T/ready"
  wait_for_file "$CCI_JOBLOG_STATE_DIR/leak-test-runner.json"
  for s in FAKE- 5551212 auth_token; do
    refute_grep "$s" "$CCI_JOBLOG_STATE_DIR"
  done
  kill -TERM "$pid"
  wait "$pid" || true
  run jq -e -s 'all(.[]; .runner_name == "leak-test-runner")' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
}

# --- state file ------------------------------------------------------------

@test "state file: written at start, valid JSON, removed at end" {
  seed_cache
  CCI_RUNNER_NAME="runner/odd name" CIRCLE_JOB=lint FAKE_READY="$T/ready" FAKE_SLEEP=30 "$WRAPPER" "$AGENT" &
  local pid=$!
  wait_for_file "$T/ready"
  wait_for_file "$CCI_JOBLOG_STATE_DIR/runner_odd_name.json"
  run jq -e '.state == "running" and .job_name == "lint" and .runner_name == "runner/odd name"
             and (.wrapper_pid | type == "number") and .instance_id == "i-0cafe0000000000a1"' \
    "$CCI_JOBLOG_STATE_DIR/runner_odd_name.json"
  [ "$status" -eq 0 ]
  [ "$(ls -A "$CCI_JOBLOG_STATE_DIR")" = "runner_odd_name.json" ]
  kill -TERM "$pid"
  wait "$pid" || true
  [ -z "$(ls -A "$CCI_JOBLOG_STATE_DIR")" ] # removed, and no tmp leftovers
}

@test "state file falls back to the runner pid when there is no runner name" {
  seed_cache
  FAKE_READY="$T/ready" FAKE_SLEEP=30 "$WRAPPER" "$AGENT" &
  local pid=$!
  wait_for_file "$T/ready"
  wait_for_file "$CCI_JOBLOG_STATE_DIR/pid-$$.json"
  kill -TERM "$pid"
  wait "$pid" || true
}

@test "CCI_JOBLOG_STATE_ON_END=idle leaves an idle marker" {
  seed_cache
  CCI_RUNNER_NAME=r1 CCI_JOBLOG_STATE_ON_END=idle "$WRAPPER" "$AGENT"
  run jq -e '.state == "idle" and .runner_name == "r1"' "$CCI_JOBLOG_STATE_DIR/r1.json"
  [ "$status" -eq 0 ]
}

# --- runner name / resource class ------------------------------------------

@test "runner name is read from runner.name only, not from other sections" {
  seed_cache
  cat >"$T/runner.yaml" <<'YAML'
# comment
api:
  auth_token: FAKE-TOKEN
  name: not-this-one
runner:
  # inner comment
  working_directory: /tmp
  name: "real-runner"   # trailing comment
  logging:
    name: nested-not-this
other:
  name: nor-this
YAML
  CCI_RUNNER_CONFIG="$T/runner.yaml" "$WRAPPER" "$AGENT"
  run jq -e -s 'all(.[]; .runner_name == "real-runner")' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
}

@test "CCI_RUNNER_NAME overrides the config file" {
  seed_cache
  printf 'runner:\n  name: from-file\n' >"$T/runner.yaml"
  CCI_RUNNER_CONFIG="$T/runner.yaml" CCI_RUNNER_NAME=from-env "$WRAPPER" "$AGENT"
  run jq -e -s 'all(.[]; .runner_name == "from-env")' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
}

@test "resource class: operator file is parsed (not sourced); env wins over file" {
  seed_cache
  {
    printf '%s\n' '# operator settings' 'export CCI_RESOURCE_CLASS="acme/linux-large"' "CCI_JOBLOG_EXTRA_FIELDS='pool=bazel'"
    printf '%s\n' "\$(touch $T/pwned)" "\`touch $T/pwned2\`"
  } >"$T/wrapper.env"
  CCI_JOBLOG_CONF="$T/wrapper.env" "$WRAPPER" "$AGENT"
  run jq -e -s 'all(.[]; .resource_class == "acme/linux-large" and .pool == "bazel")' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
  [ ! -e "$T/pwned" ]
  [ ! -e "$T/pwned2" ]
  : >"$CCI_JOBLOG_FILE"
  CCI_RESOURCE_CLASS=acme/env-wins CCI_JOBLOG_CONF="$T/wrapper.env" "$WRAPPER" "$AGENT"
  run jq -e -s 'all(.[]; .resource_class == "acme/env-wins")' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
}

# --- host identity ---------------------------------------------------------

@test "IMDSv2 is used first; identity lands in events and the cache" {
  start_mock v2
  CCI_JOBLOG_IMDS_URL="$MOCK_URL" "$WRAPPER" "$AGENT"
  run jq -e -s 'all(.[]; .instance_id == "i-0123456789abcdef0" and .instance_type == "c7g.xlarge"
        and .availability_zone == "us-east-1b" and .region == "us-east-1"
        and .private_ip == "10.0.1.23" and .ami_id == "ami-0abc1234def567890")' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
  grep -q '^PUT /latest/api/token' "$MOCK_LOG"
  grep -q '^GET /latest/dynamic/instance-identity/document token=yes' "$MOCK_LOG"
  run grep -q '^GET .* token=no' "$MOCK_LOG" # no IMDSv1 attempt
  [ "$status" -ne 0 ]
  grep -q '^ec2=yes$' "$CCI_JOBLOG_HOST_CACHE"
}

@test "falls back to IMDSv1 only when IMDSv2 fails" {
  start_mock v1
  CCI_JOBLOG_IMDS_URL="$MOCK_URL" "$WRAPPER" "$AGENT"
  run jq -e -s 'all(.[]; .instance_id == "i-0123456789abcdef0")' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
  grep -q '^PUT /latest/api/token' "$MOCK_LOG"
  grep -q '^GET /latest/dynamic/instance-identity/document token=no' "$MOCK_LOG"
}

@test "the second job uses the cache and does not contact IMDS" {
  start_mock v2
  CCI_JOBLOG_IMDS_URL="$MOCK_URL" "$WRAPPER" "$AGENT"
  local n
  n=$(wc -l <"$MOCK_LOG")
  : >"$CCI_JOBLOG_FILE"
  CCI_JOBLOG_IMDS_URL="$MOCK_URL" "$WRAPPER" "$AGENT"
  [ "$(wc -l <"$MOCK_LOG")" -eq "$n" ]
  run jq -e -s 'all(.[]; .instance_id == "i-0123456789abcdef0")' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
}

@test "a cache from a different boot is ignored" {
  start_mock v2
  mkdir -p "$T/run"
  printf 'ec2=yes\nboot_id=00000000-dead-beef-0000-000000000000\ninstance_id=i-stale\n' >"$CCI_JOBLOG_HOST_CACHE"
  CCI_JOBLOG_IMDS_URL="$MOCK_URL" "$WRAPPER" "$AGENT"
  run jq -e -s 'all(.[]; .instance_id == "i-0123456789abcdef0")' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
}

@test "--refresh-host-cache fills the cache from IMDS and exits 0" {
  start_mock v2
  CCI_JOBLOG_IMDS_URL="$MOCK_URL" run "$WRAPPER" --refresh-host-cache
  [ "$status" -eq 0 ]
  grep -q '^instance_id=i-0123456789abcdef0$' "$CCI_JOBLOG_HOST_CACHE"
  grep -q '^ec2=yes$' "$CCI_JOBLOG_HOST_CACHE"
  grep -q '^region=us-east-1$' "$CCI_JOBLOG_HOST_CACHE"
  grep -q '^boot_id=' "$CCI_JOBLOG_HOST_CACHE"
}

@test "--refresh-host-cache on a non-EC2 host exits 0 and records the negative result" {
  run "$WRAPPER" --refresh-host-cache
  [ "$status" -eq 0 ]
  grep -q '^ec2=no$' "$CCI_JOBLOG_HOST_CACHE"
}

# --- HTTP sink -------------------------------------------------------------

@test "HTTP sink receives both events; header is sent; stdin untouched" {
  seed_cache
  start_mock sink
  printf 'abc' | CCI_JOBLOG_HTTP_URL="$MOCK_URL/sink" CCI_JOBLOG_HTTP_HEADER="X-Test: s3cr3t-header" \
    FAKE_STDIN_OUT="$T/o" "$WRAPPER" "$AGENT"
  local i
  for ((i = 0; i < 60; i++)); do
    (($(grep -c '^POST' "$MOCK_LOG") >= 2)) && break
    sleep 0.05
  done
  [ "$(grep -c '^POST /sink' "$MOCK_LOG")" -eq 2 ]
  grep -q 'X-Test=s3cr3t-header' "$MOCK_LOG"
  grep -q 'body={"schema":1,"event":"job_start"' "$MOCK_LOG"
  grep -q 'body={"schema":1,"event":"job_end"' "$MOCK_LOG"
  [ "$(cat "$T/o")" = abc ]
}

@test "a hanging HTTP sink never delays the job" {
  seed_cache
  start_mock hang
  local t0 took
  t0=$(epoch_ms)
  CCI_JOBLOG_HTTP_URL="$MOCK_URL/sink" "$WRAPPER" "$AGENT"
  took=$(($(epoch_ms) - t0))
  echo "# wrapper with hanging HTTP sink: ${took} ms" >&3
  ((took < 1000))
}

@test "the HTTP header secret is not visible in the process list" {
  seed_cache
  start_mock hang
  CCI_JOBLOG_HTTP_URL="$MOCK_URL/sink" CCI_JOBLOG_HTTP_HEADER="X-Test: ps-secret-77" "$WRAPPER" "$AGENT"
  run bash -c "ps -eo args | grep -F 'ps-secret-77' | grep -vF grep"
  [ "$status" -ne 0 ]
}

# --- overhead --------------------------------------------------------------

@test "overhead with a warm cache is below 150 ms (median of 15 runs)" {
  seed_cache
  local i t0 t1 base=() wrapped=()
  for ((i = 0; i < 15; i++)); do
    t0=$(epoch_ms)
    "$AGENT"
    t1=$(epoch_ms)
    base+=($((t1 - t0)))
    t0=$(epoch_ms)
    "$WRAPPER" "$AGENT"
    t1=$(epoch_ms)
    wrapped+=($((t1 - t0)))
  done
  local mb mw
  mb=$(printf '%s\n' "${base[@]}" | sort -n | sed -n 8p)
  mw=$(printf '%s\n' "${wrapped[@]}" | sort -n | sed -n 8p)
  echo "# median direct: ${mb} ms, wrapped: ${mw} ms, overhead: $((mw - mb)) ms (whole run, incl. job_end)" >&3
  ((mw - mb < 150))
}

@test "agent starts within 150 ms of the wrapper (telemetry runs after the spawn)" {
  seed_cache
  local i t0 ts=() m
  for ((i = 0; i < 15; i++)); do
    rm -f "$T/ready"
    t0=$(epoch_ms)
    FAKE_READY="$T/ready" "$WRAPPER" "$AGENT" &
    wait_for_file "$T/ready"
    ts+=($(($(epoch_ms) - t0)))
    wait
  done
  m=$(printf '%s\n' "${ts[@]}" | sort -n | sed -n 8p)
  echo "# median wrapper-launch to agent-ready: ${m} ms (includes 50 ms polling granularity)" >&3
  ((m < 150))
}

# --- prometheus textfile ---------------------------------------------------

@test "prom textfile: busy=1 while running, busy=0 after, labels escaped" {
  export CCI_JOBLOG_PROM_DIR="$BATS_TEST_TMPDIR/prom" CCI_RUNNER_NAME=r1 CIRCLE_JOB=$'we"ird\\job'
  "$WRAPPER" sh -c 'sleep 0.4' &
  sleep 0.25
  run cat "$CCI_JOBLOG_PROM_DIR/r1.prom"
  [[ $output == *'circleci_runner_busy{runner="r1"'*'job_name="we\"ird\\job"'*'} 1'* ]]
  wait
  run cat "$CCI_JOBLOG_PROM_DIR/r1.prom"
  [[ $output == *'circleci_runner_busy{runner="r1",resource_class="'*'} 0'* ]]
  [[ $output != *job_name* ]]
}

@test "prom textfile: operator file can enable it" {
  printf 'CCI_JOBLOG_PROM_DIR=%s\n' "$BATS_TEST_TMPDIR/prom2" > "$BATS_TEST_TMPDIR/w.env"
  CCI_JOBLOG_CONF="$BATS_TEST_TMPDIR/w.env" CCI_RUNNER_NAME=r2 run "$WRAPPER" true
  [ "$status" -eq 0 ]
  [ -f "$BATS_TEST_TMPDIR/prom2/r2.prom" ]
}

@test "job_end carries start_ms/end_ms that bracket duration_ms" {
  run "$WRAPPER" sh -c 'sleep 0.2'
  [ "$status" -eq 0 ]
  run jq -e 'select(.event=="job_end") | (.end_ms - .start_ms) == .duration_ms and .duration_ms >= 150' "$CCI_JOBLOG_FILE"
  [ "$status" -eq 0 ]
}
