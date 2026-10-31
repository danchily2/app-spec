#!/usr/bin/env bash
set -euo pipefail
CASE="$(cd "$(dirname "$0")" && pwd)"
bash "$CASE/../_fixtures/make-apps.sh"
python3 "$CASE/../../scripts/module.py" ios-app --module Payslips --out ./specs/payslips >/dev/null
