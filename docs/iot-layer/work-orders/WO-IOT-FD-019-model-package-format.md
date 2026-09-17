# Work Order: WO-IOT-FD-019 - Model Package Format

**Work Order ID**: `WO-IOT-FD-019`  
**Ticket**: `IOT-FD-019`  
**Epic**: `EPIC-IOT-FD-04` AI Weight Prediction Enablement  
**Owner Role**: `ML Engineer` and `Data Engineer`  
**Suggested Assignee**: ML Platform Engineering  
**Suggested Reviewer**: Lead Software Architect, CV Technical Reviewer  
**Priority**: P1  
**Status**: Completed (MVP)  
**Created**: 2026-07-13  
**Estimated Effort**: 10-14 hours  
**Execution Model**: artifact-spec design with validation rules

---

## Objective

Standardize the model artifact package that Cloud publishes and Edge consumes.

## Business Outcome

This ensures deployable models are verifiable, versioned, and compatible before Edge activation.

## Implementation Status

Implemented in Batch 4 MVP:

- package manifest schema is represented in `WeighVisionPackageManifest`
- required fields now cover package version, runtime, feature schema, checksum, package URI, channel, activation policy, fallback policy, and metadata
- `edge-vision-inference` now reads active and fallback manifest files through environment-driven paths

Current limitation:

- the runtime currently validates and reports manifest metadata, but does not yet download and unpack a real Cloud-produced model artifact

## Agent Skill Profile

### Primary

- `ML Engineer`
- `Data Engineer`

### Supporting

- `Node Edge Engineer`
- `Documentation Agent`

## Code Areas

- model artifact packaging outputs from Cloud training workflow
- manifest schema and checksum metadata
- Edge validation path in `edge-layer/edge-vision-inference`
- registry and subscription contract dependencies

## Scope

### In Scope

- artifact contents
- manifest schema
- checksum and compatibility metadata
- runtime requirements
- feature-schema compatibility declaration
- package versioning rules

### Out of Scope

- subscription endpoint behavior
- Edge rollback policy
- training dataset redesign

## Dependencies

- `WO-IOT-FD-015`

## Proposed Package Layout

```text
model-package/
  manifest.json
  model/
    model.onnx
  schema/
    feature-schema.json
    output-schema.json
  config/
    preprocessing.json
    postprocessing.json
  evidence/
    metrics-summary.json
    training-summary.json
```

## Required Manifest Fields

- `package_format_version`
- `model_family`
- `model_version`
- `artifact_checksum`
- `artifact_size_bytes`
- `runtime_family`
- `runtime_version`
- `feature_schema_version`
- `output_schema_version`
- `training_dataset_version`
- `created_at`
- `created_by`
- `compatible_edge_services`
- `fallback_compatible_with`

## Design Decisions To Lock

- canonical runtime artifact format such as `onnx` for Edge portability
- whether metrics evidence ships inside the package or remains registry-linked only
- whether package validation is done fully offline on Edge or requires optional Cloud signature verification
- backward-compatibility rule for new manifest versions

## Risks and Controls

| Risk | Impact | Control |
| --- | --- | --- |
| package omits runtime dependencies | Edge load failure | include explicit compatibility manifest |
| checksum policy is weak | untrusted artifact activation | require checksum and package validation |
| artifact format is too model-specific | future migration pain | keep manifest model-family aware but runtime generic |

## Implementation Plan

1. Define artifact contents and packaging structure.
2. Define manifest schema and required metadata.
3. Define validation rules before Edge activation.
4. Define package versioning and compatibility rules.
5. Publish one reference package example.

## Edge Validation Rules

- checksum must match before extraction or activation
- runtime family and version must be supported by the local Edge runtime
- feature schema version must match the active extractor contract
- missing required manifest fields must fail activation immediately

## Test Plan

### Static Verification

- verify manifest includes model version, checksum, runtime compatibility, and package contents

### Runtime Verification

- validate one package successfully
- reject one malformed or incompatible package
- validate one package against an older unsupported runtime and confirm deterministic rejection

### Regression Guardrails

- Edge must not activate a package that fails validation

## Rollback Plan

- retain current manual artifact handling until package format is accepted
- reject new package format versions that break backward validation rules

## Deliverables

- model package specification
- manifest schema
- package validation rules
- reference package directory example
- package versioning policy

## Acceptance Criteria

- one package format is defined that Edge can validate before activation

## Evidence Required

- package specification
- manifest example
- validation checklist
- rejection example for incompatible package
