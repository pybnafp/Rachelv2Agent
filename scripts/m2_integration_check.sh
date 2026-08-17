#!/usr/bin/env bash
# M2 integration check: register -> me -> submit job -> list -> trace -> result -> files -> delete
# Usage: scripts/m2_integration_check.sh [base_url]
set -u
BASE="${1:-http://127.0.0.1:8000}"
PASS=0; FAIL=0
check() { # name expected_status actual_status [extra_cond_cmd]
  local name="$1" want="$2" got="$3"
  if [ "$want" = "$got" ] && { [ $# -lt 4 ] || eval "$4"; }; then
    echo "PASS: $name (status $got)"; PASS=$((PASS+1))
  else
    echo "FAIL: $name (want $want, got $got)"; FAIL=$((FAIL+1))
  fi
}

USER="m2it_$RANDOM$RANDOM"
TOKEN=$(curl -s -X POST "$BASE/api/auth/register" -H "Content-Type: application/json" \
  -d "{\"username\":\"$USER\",\"password\":\"pass1234\"}" | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])" 2>/dev/null)
[ -n "$TOKEN" ] && [ "$TOKEN" != "None" ] && echo "PASS: register ($USER)" && PASS=$((PASS+1)) || { echo "FAIL: register"; FAIL=$((FAIL+1)); exit 1; }
AUTH="Authorization: Bearer $TOKEN"

S=$(curl -s -o /tmp/m2me.json -w "%{http_code}" "$BASE/api/auth/me" -H "$AUTH"); check "GET /api/auth/me" 200 "$S"

JOB=$(curl -s -X POST "$BASE/api/jobs" -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"smiles":"CC(=O)Nc1ccc(O)cc1"}' | python -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null)
[ -n "$JOB" ] && echo "PASS: POST /api/jobs (id=$JOB)" && PASS=$((PASS+1)) || { echo "FAIL: POST /api/jobs"; FAIL=$((FAIL+1)); exit 1; }

# Wait for job to leave queued (LLM provider fails fast -> failed with error)
STATUS=""
for i in $(seq 1 20); do
  STATUS=$(curl -s "$BASE/api/jobs/$JOB" -H "$AUTH" | python -c "import sys,json;print(json.load(sys.stdin)['status'])" 2>/dev/null)
  [ "$STATUS" = "failed" ] || [ "$STATUS" = "succeeded" ] && break
  sleep 1
done
echo "job final status: $STATUS"
ERR=$(curl -s "$BASE/api/jobs/$JOB" -H "$AUTH" | python -c "import sys,json;print(json.load(sys.stdin).get('error') or '')" 2>/dev/null)
if [ "$STATUS" = "failed" ] && [ -n "$ERR" ]; then echo "PASS: job queryable + failed with error"; PASS=$((PASS+1)); else echo "FAIL: job status/error (status=$STATUS err=$ERR)"; FAIL=$((FAIL+1)); fi

S=$(curl -s -o /tmp/m2list.json -w "%{http_code}" "$BASE/api/jobs?mine=1" -H "$AUTH")
check "GET /api/jobs?mine=1 contains job" 200 "$S" "grep -q $JOB /tmp/m2list.json"

S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/jobs/$JOB/trace" -H "$AUTH"); check "GET /api/jobs/{id}/trace" 200 "$S"
S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/jobs/$JOB/result" -H "$AUTH"); check "GET /api/jobs/{id}/result (job-only)" 200 "$S"
S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/jobs/$JOB/files/messages.jsonl?token=$TOKEN")
if [ "$S" = "200" ] || [ "$S" = "404" ]; then echo "PASS: GET /files/messages.jsonl?token= (status $S)"; PASS=$((PASS+1)); else echo "FAIL: files endpoint ($S)"; FAIL=$((FAIL+1)); fi
S=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE/api/jobs/$JOB" -H "$AUTH"); check "DELETE /api/jobs/{id}" 200 "$S"

echo "-----"
echo "RESULT: $PASS PASS / $FAIL FAIL"
exit $([ "$FAIL" -eq 0 ] && echo 0 || echo 1)
