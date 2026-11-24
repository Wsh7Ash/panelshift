#!/usr/bin/env bash
# End-to-end demo: checks documented exit codes and the verify round trip.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH=src
TMP="$(pwd)/.demo-tmp"
rm -rf "$TMP"
mkdir -p "$TMP"

fail=0
check_exit() {
  local label="$1" expected="$2"
  shift 2
  python -m panelshift "$@" >"$TMP/demo.out" 2>"$TMP/demo.err"
  local actual=$?
  if [ "$actual" -ne "$expected" ]; then
    echo "FAIL $label: expected exit $expected, got $actual"
    sed 's/^/    /' "$TMP/demo.err"
    fail=1
  else
    echo "ok   $label (exit $actual)"
  fi
}

echo "panelshift demo"
echo "---------------"
check_exit "feasible workshop plan" 0 plan examples/workshop.json
check_exit "infeasible capacity plan" 1 plan examples/impossible.json
check_exit "infeasible slot plan" 1 plan examples/slots.json
check_exit "invalid path" 2 plan examples/not-a-file.json

python -m panelshift plan examples/workshop.json --format json >"$TMP/report.json"
json_exit=$?
PANELSHIFT_REPORT="$TMP/report.json" python - <<'PY'
import json
import os
import sys

with open(os.environ["PANELSHIFT_REPORT"], "r", encoding="utf-8") as handle:
    report = json.load(handle)
ok = (
    report["verdict"] == "feasible"
    and report["optimal"] is True
    and report["certificate"]["search_complete"] is True
    and report["certificate"]["method"] == "exact-subset-sum-dp"
    and report["legs"]["a"]["amps"] <= report["panel"]["capacity_amps"]
    and report["legs"]["b"]["amps"] <= report["panel"]["capacity_amps"]
    and len(report["circuits"]) == 12
)
print(f"ok   json report contract ({'satisfied' if ok else 'violated'})")
print(
    "     legs {:.1f} A / {:.1f} A, imbalance {:.1f} A, {} states".format(
        report["legs"]["a"]["amps"],
        report["legs"]["b"]["amps"],
        report["imbalance_amps"],
        report["certificate"]["reachable_states"],
    )
)
sys.exit(0 if ok else 1)
PY
report_exit=$?
[ "$json_exit" -ne 0 ] && fail=1
[ "$report_exit" -ne 0 ] && fail=1

check_exit "verify emitted report" 0 verify "$TMP/report.json"

# Tamper with one leg assignment and confirm the verifier rejects it.
PANELSHIFT_REPORT="$TMP/report.json" PANELSHIFT_TAMPERED="$TMP/tampered.json" python - <<'PY'
import json
import os

with open(os.environ["PANELSHIFT_REPORT"], "r", encoding="utf-8") as handle:
    report = json.load(handle)
target = next(c for c in report["circuits"] if c["poles"] == 1)
target["leg"] = "B" if target["leg"] == "A" else "A"
with open(os.environ["PANELSHIFT_TAMPERED"], "w", encoding="utf-8") as handle:
    json.dump(report, handle)
PY
check_exit "reject tampered report" 1 verify "$TMP/tampered.json"

if [ "$fail" -ne 0 ]; then
  echo "demo: FAILED"
  exit 1
fi
rm -rf "$TMP"
echo "demo: all checks passed"
