---
type: regex
target: { source: file, path: specs/payslips/app-spec.json }
pattern: '"confirmed":\s*false'
---

A headless run takes the proposed scope and records that nobody confirmed it.
