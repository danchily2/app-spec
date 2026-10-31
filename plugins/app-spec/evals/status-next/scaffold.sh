#!/usr/bin/env bash
set -euo pipefail
CASE="$(cd "$(dirname "$0")" && pwd)"
S="$CASE/../../scripts"
bash "$CASE/../_fixtures/make-apps.sh"
python3 "$S/module.py" ios-app --module Payslips --out ./specs/payslips >/dev/null
python3 "$S/inventory.py" ./specs/payslips >/dev/null
cp "$S/tests/fixtures/results/understand_result.json" "$S/tests/fixtures/results/rules_result.json" ./specs/payslips/
python3 "$S/render.py" catalogs ./specs/payslips >/dev/null 2>&1
