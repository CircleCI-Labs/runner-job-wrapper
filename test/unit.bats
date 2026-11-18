#!/usr/bin/env bats
# Unit tests for the helper functions (the script is sourced, not executed).

load test_helper

# Sourced at file level so that the script's `declare -A` is global.
# shellcheck source=../bin/circleci-job-wrapper
source "$WRAPPER"

setup() { common_setup; }
teardown() { common_teardown; }

@test "json_escape: every control character 0x01-0x1f round-trips through jq" {
  local i ch
  for ((i = 1; i < 32; i++)); do
    printf -v ch '%b' "\\0$((i / 64))$(((i / 8) % 8))$((i % 8))"
    json_escape "a${ch}b"
    printf '{"v":"%s"}' "$JSON_ESC" >"$T/j.json"
    run jq -e --arg v "a${ch}b" '.v == $v' "$T/j.json"
    if [ "$status" -ne 0 ]; then
      echo "failed for 0x$(printf %02x "$i")"
      return 1
    fi
  done
}

@test "json_escape: quotes, backslashes, newline, tab, CR, emoji" {
  local s=$'q"uote \\ back\nnl\ttab\rcr 😀 é'
  json_escape "$s"
  printf '{"v":"%s"}' "$JSON_ESC" >"$T/j.json"
  run jq -e --arg v "$s" '.v == $v' "$T/j.json"
  [ "$status" -eq 0 ]
  [[ $JSON_ESC != *$'\n'* ]]
}

@test "json_escape: truncation never splits a UTF-8 character" {
  local s="a😀😀😀😀" n
  for ((n = 1; n <= 20; n++)); do
    json_escape "$s" "$n"
    if ! printf '%s' "$JSON_ESC" | iconv -f UTF-8 -t UTF-8 >/dev/null; then
      echo "invalid UTF-8 at max=$n"
      return 1
    fi
    [ "$(printf '%s' "$JSON_ESC" | wc -c)" -le "$n" ]
  done
}

@test "json_escape does not change the caller's locale" {
  export LC_ALL=C.UTF-8
  json_escape $'x\x01y'
  [ "$LC_ALL" = C.UTF-8 ]
  run bash -c 'env | grep -c "^LC_ALL=C.UTF-8$"'
  [ "$output" -eq 1 ]
}

@test "fmt_ts matches date -u for assorted instants" {
  local ms
  for ms in 0 951782400123 1709164799999 1709164800000 1763500000042 4102444799999 1234567890000; do
    fmt_ts "$ms"
    [ "$TS" = "$(date -u -d "@$((ms / 1000))" +%Y-%m-%dT%H:%M:%S).$(printf %03d $((ms % 1000)))Z" ]
  done
}

@test "now_ms returns plausible epoch milliseconds" {
  now_ms
  local ref
  ref=$(($(date +%s) * 1000))
  ((NOW_MS - ref < 2000 && ref - NOW_MS < 2000))
}

@test "kv_parse reads key=value, strips quotes/export/comments, never executes anything" {
  {
    printf '%s\n' '# c' 'A=1' 'export B="two words"' "C='x y'" '  D = trimmed around key'
    printf '%s\n' "\$(touch $T/pwned)=1" "E=\$(touch $T/pwned)"
  } >"$T/kv"
  kv_parse "$T/kv"
  [ "${KV[A]}" = 1 ]
  [ "${KV[B]}" = "two words" ]
  [ "${KV[C]}" = "x y" ]
  [ "${KV[D]}" = "trimmed around key" ]
  [ ! -e "$T/pwned" ]
}

@test "read_runner_name handles indentation, quoting and comments" {
  printf 'runner:\n    name: r-1 # c\n' >"$T/c.yaml"
  read_runner_name "$T/c.yaml"
  [ "$RUNNER_NAME" = "r-1" ]
  printf "runner:\n  name: 'quoted name'\n" >"$T/c.yaml"
  read_runner_name "$T/c.yaml"
  [ "$RUNNER_NAME" = "quoted name" ]
  printf 'api:\n  name: no\n' >"$T/c.yaml"
  RUNNER_NAME=""
  run read_runner_name "$T/c.yaml"
  [ "$status" -ne 0 ]
}

@test "source hygiene: no set -e, agent arguments never reach a log call" {
  run grep -nE '^[[:space:]]*set -[a-z]*e|errexit' "$WRAPPER"
  [ "$status" -ne 0 ]
  run bash -c "grep -nF '\"\$@\"' '$WRAPPER' | grep -E 'printf|echo|dbg|jadd'"
  [ "$status" -ne 0 ]
}
