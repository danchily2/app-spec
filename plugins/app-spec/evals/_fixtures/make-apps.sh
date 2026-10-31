#!/usr/bin/env bash
# Shared fixture: copies the three synthetic apps of the unit tests (ios-app, rn-app, android-app) into the current
# folder, which is the eval's scratch folder. Nothing here comes from a real app.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FIX="$HERE/../../scripts/tests/fixtures"
for app in ios-app rn-app android-app; do
  [ -e "./$app" ] || cp -R "$FIX/$app" "./$app"
done
