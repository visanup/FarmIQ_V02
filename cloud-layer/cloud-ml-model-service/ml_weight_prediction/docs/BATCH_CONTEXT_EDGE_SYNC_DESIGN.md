# Batch Context Sync for Edge WeightVision

## Purpose

Make each WeightVision session traceable to the flock being weighed, without
making realtime inference depend on a Cloud round trip.  A valid session must
be able to report its batch, breed, sex, age in days, and the selected model
package when those data are available.

This design also defines a safe behaviour for farms which begin weighing before
their Batch & Flocks record is entered.

## Verified current state

The current implementation is only partially wired:

- Cloud Tenant Registry persists a batch but emits no batch outbox event.
- `edge-policy-sync` caches farm/barn config and site model subscriptions, but
  has no batch-context or device-binding cache.
- Edge WeighVision Session accepts an optional `batchId` and propagates it in
  `weighvision.session.created` events.
- Edge Vision Inference can fetch batch master data from the Cloud BFF and
  compute `age_days`, but only after a session already contains `batchId` and
  capture metadata can identify the capture timestamp.
- If no model subscription is cached, inference runs in fallback/shadow mode.

Therefore, a dashboard-created Batch is not currently available to Edge
automatically.

## Target behaviour

```text
Dashboard creates/updates/activates a batch
  -> Tenant Registry transaction writes batch + outbox event
  -> Cloud control endpoint exposes latest batch context for the edge site
  -> edge-policy-sync upserts its local cache
  -> device/station starts a WeightVision session
  -> Edge resolves one active batch and stamps batchId on the session
  -> inference reads local context, computes age_days, and selects the package
  -> prediction + provenance are synced back to Cloud and displayed in Dashboard
```

Cloud is the source of truth. Edge has a versioned read cache so realtime work
continues while Cloud is unreachable.

## Data model and contract

### Batch context

The Edge cache stores one record per `tenantId + deviceId + stationId` binding.
It contains the effective batch and a monotonically increasing revision.

```json
{
  "eventType": "batch.upsert",
  "eventId": "uuid",
  "revision": 4,
  "tenantId": "t-001",
  "farmId": "f-001",
  "barnId": "b-001",
  "batchId": "uuid",
  "status": "active",
  "species": "broiler",
  "breedCode": "Arbor Acres Plus",
  "sex": "male",
  "startDate": "2026-09-08",
  "deviceBindings": [{ "deviceId": "wv-001", "stationId": "st-01" }],
  "modelPolicy": {
    "packageId": "weight-broiler-arbor-acres-v1",
    "version": "1.0.0"
  }
}
```

Required cache columns:

- scope: tenant, farm, barn, device, station, batch;
- ML context: species, breed, sex, start date, package and version;
- sync metadata: revision, source event ID, fetched time, status and expiry.

### Resolution rules

1. At session creation, resolve an active cache record by tenant, device and
   station.  Farm/barn must also match.
2. Stamp the resolved `batchId` and context version onto the immutable session.
3. Calculate `age_days = local capture date - batch start date`.
4. If exactly one active binding does not exist, create an **unassigned**
   session and use the explicitly configured fallback model.
5. If more than one active binding matches, reject the session with
   `BATCH_CONTEXT_AMBIGUOUS`; never guess a flock.
6. Store model package/version, batch ID, breed and age in inference provenance.

## Lifecycle events

Tenant Registry must write an outbox record in the same transaction as the
Batch write. Supported events are:

- `batch.upsert` — create or amend master data/binding;
- `batch.activate` — eligible for new Edge sessions;
- `batch.deactivate` — no new sessions may use this binding;
- `batch.binding.upsert` / `batch.binding.remove` — change device or station
  assignments.

Events are idempotent by `eventId`. Edge applies a record only when its
revision is newer than its cached revision. Acknowledge sync state so the Cloud
can surface stale Edge configuration.

## Late batch entry and historical data

The normal action after a late Batch entry is **association only**, not an
inference replay:

1. Operator supplies the real placement/start date.
2. Operator selects the batch, device/station and an effective time interval.
3. System previews matching unassigned sessions.
4. After confirmation, sessions receive `batchId` and derived provenance such
   as breed and `age_days`.

Association is low-cost and does not use inference CPU/GPU.

Historical reprocessing is optional and must be a separate operation. It is
allowed only where source media are retained. It writes a new inference
revision; it never overwrites the original prediction.

### Reprocessing QoS

- Separate `historical-reprocess` queue from `realtime-inference`.
- Realtime has dedicated capacity and higher priority.
- Limit historical work by per-edge concurrency and CPU/GPU utilization.
- Pause historical work automatically when realtime backlog or latency exceeds
  a configured threshold.
- Default to manually initiated/off-hours work and provide cancellation.

## API additions

### Cloud control plane

- `GET /api/v1/edge/batch-context?tenantId=&siteId=&sinceRevision=`
- `POST /api/v1/batches/:id/bindings`
- `POST /api/v1/batches/:id/associate-sessions` (preview and confirm modes)
- `POST /api/v1/weighvision/sessions/reprocess` (asynchronous; optional)

### Edge

- `GET /api/v1/edge-config/batch-context/:tenantId/:deviceId/:stationId`
- internal session resolution uses cache; callers do not supply `batchId` in
  the normal device path.

## Delivery tickets

### Core path — 6 tickets

1. **Batch event contract and Cloud outbox** — add event schema, transactional
   outbox, revisions, and tests to Tenant Registry.
2. **Cloud batch-context/control API** — expose effective batch/device binding
   data and model-policy resolution through BFF/control endpoints.
3. **Edge batch-context cache and sync** — schema, incremental polling,
   idempotency, acknowledgement, stale-cache health checks and metrics.
4. **Automatic Edge session binding** — resolve device/station to one active
   batch, add unassigned/ambiguous behaviour, and propagate provenance.
5. **Inference context and model selection** — consume cache offline, compute
   age, record provenance, and enforce fallback semantics.
6. **Dashboard and end-to-end acceptance** — show batch/breed/age/model on
   sessions, binding administration, Docker Compose smoke test, and E2E tests.

### Optional capability — 1 separate ticket

7. **Historical association and throttled reprocessing** — preview/confirm
   association, separate queue, quotas, cancellation, audit trail and inference
   revisions.

The core feature is six tickets. Including safe historical reprocessing makes
seven tickets. Each ticket must run its focused unit/integration tests; the
final ticket also runs `docker compose up -d --build` in the intended
environment and the complete Edge-to-Cloud-to-Dashboard smoke test.

## Acceptance criteria

1. A batch created and bound in Cloud reaches the target Edge cache within the
   configured sync period.
2. A capture from a bound device produces a session with the expected batch,
   breed, age and model provenance.
3. Cloud outage does not prevent inference while an unexpired Edge cache entry
   exists.
4. Missing context produces a visible unassigned/fallback result; ambiguous
   context is rejected.
5. Dashboard displays the same batch and weight provenance returned by the
   read model.
6. Historical association consumes no inference worker capacity. Historical
   replay cannot degrade realtime latency beyond its configured SLO.
