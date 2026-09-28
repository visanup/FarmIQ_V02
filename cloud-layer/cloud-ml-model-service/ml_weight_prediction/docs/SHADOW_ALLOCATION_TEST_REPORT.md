# Shadow allocation verification — 2026-09-21

Scope: code and local isolated shadow deployment, not installation on the farm.

## Completed

- Edge opt-in XGBoost runtime, trusted manifest/file checksums, matching capture by
  media ID, complete detection group QC, gram-unit allocation.
- Transactional `allocation_shadow_events` and `session_bird_allocations` tables.
- Local-only `weighvision.group_allocation.completed` event with decision and
  individual-accuracy flags permanently false.
- Reproducible mock services, legacy fixed-value fixture, Docker Compose and runbook.

## Executed results

| Check | Result |
|---|---|
| Real-model shadow tests including PostgreSQL | 15 passed, 0 skipped |
| Existing scalar/database/job regression, shadow disabled | 13 passed |
| Shared TypeScript contracts (new allocation + existing MQTT) | 10 passed; TypeScript build passed |
| HTTP success through running services | WEAK_ALLOCATION, 2 birds, sum 800 g |
| HTTP unstable-scale rejection | REJECTED_QUALITY, 0 bird rows |
| Legacy result in both HTTP cases | 1.23 kg, non-stub fixture model; job completed |
| Production sync outbox | Only original inference.completed; no allocation event |
| Repeated same-job persistence | Same event ID; no duplicate bird rows |
| Mid-transaction invalid bird row | Entire event and bird transaction rolled back |
| Simulated shadow DB failure | Original scalar result and completed job preserved |

Both HTTP events remain `held_shadow` in the isolated database. Tests use a random
session/job ID each run. The model is the existing trained candidate, not a mock
predictor. Input geometry and calibration identities are synthetic fixtures.

Package version: `aa-male-20260919-shadow-v1`.
Manifest SHA256: `b641e70694eb5b66821557268accb1a2d73ad488a7085e56a5e85741e296b3bf`.
Reference: approved Arbor Acres Plus Male workbook; mock sex male and age 10.

Total automated assertions suites: 38 passing test cases, plus two HTTP end-to-end
scenarios. A pytest-asyncio deprecation warning about its future loop-scope default
is present; no test failures or skipped tests in the final database-backed run.

TypeScript was tested in the staged copy under
`shadow-integration/edge-layer/shared/contracts` (source files identical to Edge),
using `node node_modules/typescript/bin/tsc -p tsconfig.json` and
`node node_modules/jest/bin/jest.js --runInBand`. Its installed dependencies and
build output are ignored; no dependency changes to the repository root were needed.

## Limitations

This proves the workflow, not model accuracy or real camera/scale performance.
Reconciliation to 800 g is a mathematical constraint. Allocation events are held
locally because a Cloud consumer is outside this phase. No field deployment,
individual-accuracy approval, real calibration verification, or long-duration load
test has been performed. The default deployment flag is off. The local Compose
project enables it only against its own mock services and PostgreSQL volume.
