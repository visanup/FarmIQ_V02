# IoT-Layer Field Deployment Work Orders

**Owner**: FarmIQ Edge and IoT Architecture  
**Last Updated**: 2026-07-14

---

## Purpose

This directory contains executable Work Orders derived from:

- `docs/iot-layer/04-field-deployment-enhancement-plan.md`
- `docs/iot-layer/05-field-deployment-ticket-backlog.md`

These files are intended to be used as implementation-ready execution units for engineering agents and developers.

Each Work Order follows an enterprise-oriented structure with:

- assignee and reviewer guidance
- code-area scoping
- risk and control notes
- test plan and rollback plan
- acceptance and evidence requirements

---

## Work Order Index

| Work Order | Ticket | Priority | Title |
| --- | --- | --- | --- |
| [WO-IOT-FD-001](./WO-IOT-FD-001-field-session-audit-dataset.md) | `IOT-FD-001` | P0 | Build field session audit dataset |
| [WO-IOT-FD-002](./WO-IOT-FD-002-final-weight-path-reconstruction.md) | `IOT-FD-002` | P0 | Reconstruct final weight calculation path |
| [WO-IOT-FD-003](./WO-IOT-FD-003-scale-stability-and-capture-timing.md) | `IOT-FD-003` | P0 | Validate scale stability and capture timing |
| [WO-IOT-FD-004](./WO-IOT-FD-004-segmentation-depth-sensitivity.md) | `IOT-FD-004` | P1 | Analyze segmentation-depth parameter sensitivity |
| [WO-IOT-FD-005](./WO-IOT-FD-005-parameter-baseline-validation-report.md) | `IOT-FD-005` | P1 | Publish corrected parameter set and validation report |
| [WO-IOT-FD-006](./WO-IOT-FD-006-canonical-metadata-schema.md) | `IOT-FD-006` | P0 | Define canonical metadata schema |
| [WO-IOT-FD-007](./WO-IOT-FD-007-ingress-routing-for-inference-metadata.md) | `IOT-FD-007` | P0 | Add routing for inference metadata events |
| [WO-IOT-FD-008](./WO-IOT-FD-008-raw-capture-metadata-persistence.md) | `IOT-FD-008` | P0 | Persist raw capture metadata on Edge |
| [WO-IOT-FD-009](./WO-IOT-FD-009-normalized-feature-store.md) | `IOT-FD-009` | P0 | Add Edge-to-Cloud normalized feature mapping |
| [WO-IOT-FD-010](./WO-IOT-FD-010-metadata-verification-report-pack.md) | `IOT-FD-010` | P1 | Build metadata verification report/query pack |
| [WO-IOT-FD-011](./WO-IOT-FD-011-yolo26-runtime-compatibility.md) | `IOT-FD-011` | P1 | Validate YOLO26 runtime compatibility |
| [WO-IOT-FD-012](./WO-IOT-FD-012-yolo12-vs-yolo26-benchmark.md) | `IOT-FD-012` | P1 | Build YOLO12 vs YOLO26 benchmark harness |
| [WO-IOT-FD-013](./WO-IOT-FD-013-yolo26-rollout-and-rollback.md) | `IOT-FD-013` | P1 | Add rollout config and rollback path |
| [WO-IOT-FD-014](./WO-IOT-FD-014-ai-training-feature-dataset.md) | `IOT-FD-014` | P1 | Design Cloud AI training feature dataset |
| [WO-IOT-FD-015](./WO-IOT-FD-015-baseline-weight-prediction-models.md) | `IOT-FD-015` | P2 | Train baseline weight prediction models and publish deployable model package |
| [WO-IOT-FD-016](./WO-IOT-FD-016-shadow-prediction-pipeline.md) | `IOT-FD-016` | P2 | Integrate Cloud model subscription and Edge prediction pipeline end-to-end |
| [WO-IOT-FD-017](./WO-IOT-FD-017-cloud-model-registry.md) | `IOT-FD-017` | P1 | Design and implement Cloud model registry |
| [WO-IOT-FD-018](./WO-IOT-FD-018-model-subscription-api.md) | `IOT-FD-018` | P1 | Design and implement model subscription API |
| [WO-IOT-FD-019](./WO-IOT-FD-019-model-package-format.md) | `IOT-FD-019` | P1 | Define deployable model package format |
| [WO-IOT-FD-020](./WO-IOT-FD-020-edge-fallback-policy.md) | `IOT-FD-020` | P1 | Define Edge fallback and version activation policy |

---

## Recommended first execution batch

1. [WO-IOT-FD-006](./WO-IOT-FD-006-canonical-metadata-schema.md)
2. [WO-IOT-FD-001](./WO-IOT-FD-001-field-session-audit-dataset.md)
3. [WO-IOT-FD-002](./WO-IOT-FD-002-final-weight-path-reconstruction.md)
4. [WO-IOT-FD-007](./WO-IOT-FD-007-ingress-routing-for-inference-metadata.md)

---

## Batch 1 completion status

Batch 1 traceability scope is now completed and locally verified for:

- [WO-IOT-FD-006](./WO-IOT-FD-006-canonical-metadata-schema.md)
- [WO-IOT-FD-007](./WO-IOT-FD-007-ingress-routing-for-inference-metadata.md)
- [WO-IOT-FD-008](./WO-IOT-FD-008-raw-capture-metadata-persistence.md)
- [WO-IOT-FD-009](./WO-IOT-FD-009-normalized-feature-store.md)
- [WO-IOT-FD-010](./WO-IOT-FD-010-metadata-verification-report-pack.md)

Reference evidence session:

- `sess-int-20260714-004`

---

## Batch 2 completion status

Batch 2 weight anomaly investigation is now completed for:

- [WO-IOT-FD-001](./WO-IOT-FD-001-field-session-audit-dataset.md)
- [WO-IOT-FD-002](./WO-IOT-FD-002-final-weight-path-reconstruction.md)
- [WO-IOT-FD-003](./WO-IOT-FD-003-scale-stability-and-capture-timing.md)
- [WO-IOT-FD-004](./WO-IOT-FD-004-segmentation-depth-sensitivity.md)
- [WO-IOT-FD-005](./WO-IOT-FD-005-parameter-baseline-validation-report.md)

Reference evidence:

- `docs/iot-layer/evidence/batch2-weight-audit-dataset.csv`
- `docs/iot-layer/evidence/batch2-weight-audit-summary.json`
- `docs/iot-layer/08-weight-estimation-audit-pack.md`

Residual note:

- live bench confirmation of the suspected sensor-unit issue is still recommended before field closure

---

## Batch 2.1 completion status

Batch 2.1 local finalized-weight proof is now completed for the Edge-to-Cloud finalized session path.

Primary references:

- `docs/iot-layer/09-final-weight-local-smoke-runbook.md`
- `docs/iot-layer/evidence/batch2.1-final-weight-smoke-2026-07-14.md`

Verified outcome:

- nested `payload.scale.weight_kg` is preserved through Edge finalize persistence, Edge outbox, Cloud ingestion dedupe, and Cloud readmodel finalized measurement

---

## Batch 3 completion status

Batch 3 YOLO26 model hardening is now completed for:

- [WO-IOT-FD-011](./WO-IOT-FD-011-yolo26-runtime-compatibility.md)
- [WO-IOT-FD-012](./WO-IOT-FD-012-yolo12-vs-yolo26-benchmark.md)
- [WO-IOT-FD-013](./WO-IOT-FD-013-yolo26-rollout-and-rollback.md)

Primary references:

- `docs/iot-layer/10-yolo26-upgrade-pack.md`
- `docs/iot-layer/evidence/batch3-yolo26-runtime-compat.json`
- `docs/iot-layer/evidence/batch3-yolo26-benchmark/benchmark-summary.md`

Verified outcome:

- YOLO26 candidate profile is runtime-compatible
- frozen-dataset benchmark evidence exists on the same subset for baseline and candidate
- active and fallback model control is documented and supported via runtime config

---

## Batch 4 status

Batch 4 Cloud-Edge AI control-plane work is now implemented at MVP level for:

- [WO-IOT-FD-014](./WO-IOT-FD-014-ai-training-feature-dataset.md)
- [WO-IOT-FD-017](./WO-IOT-FD-017-cloud-model-registry.md)
- [WO-IOT-FD-018](./WO-IOT-FD-018-model-subscription-api.md)
- [WO-IOT-FD-019](./WO-IOT-FD-019-model-package-format.md)
- [WO-IOT-FD-020](./WO-IOT-FD-020-edge-fallback-policy.md)

WO partially implemented:

- [WO-IOT-FD-015](./WO-IOT-FD-015-baseline-weight-prediction-models.md)

Primary references:

- `docs/iot-layer/12-cloud-edge-ai-control-plane-pack.md`
- `docs/contracts/weighvision-model-control-plane.contract.md`
- `docs/iot-layer/evidence/batch4-control-plane-verification-2026-07-14.md`

Verified outcome:

- Cloud dataset contract, package registry, and site subscription APIs are available
- Edge policy sync can cache the resolved package per site
- Edge inference can read activation and fallback manifest metadata
- local verification passed for Cloud API tests, Edge manifest tests, and the relevant TypeScript builds

Residual note:

- real baseline training artifact publication and full package download plus shadow execution remain open under `WO-IOT-FD-015` and `WO-IOT-FD-016`

---

## Agent role model

| Role | Typical usage |
| --- | --- |
| `Architecture Analyst` | contract definition, boundaries, target-state design |
| `Repo Auditor` | source trace, payload trace, schema trace |
| `Python CV Engineer` | capture, segmentation, depth, feature extraction |
| `Node Edge Engineer` | ingress, session APIs, outbox, persistence |
| `Data Engineer` | schema design, feature tables, dataset extraction |
| `ML Engineer` | model training, evaluation, experiment tracking |
| `QA Benchmark Agent` | replay, regression, benchmark evidence |
| `Documentation Agent` | specs, evidence reports, runbooks |
