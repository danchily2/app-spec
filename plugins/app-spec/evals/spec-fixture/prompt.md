---
max_turns: 200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write, Edit, Agent]
runs: 1
timeout_seconds: 1800
---

/app-spec:spec ios-app --module Payslips --out ./specs/payslips --headless
