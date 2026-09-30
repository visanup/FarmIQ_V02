# Weight-prediction model selection runbook

## Purpose and safety boundary

Use this runbook to validate that an active batch exposes a compatible model
policy to Edge and that a completed prediction is visible in the Cloud and
Dashboard. Run it only against an isolated Dev or `bces-e2e-*` stack. Do not
place JWTs, MinIO credentials, subscription keys, or production endpoints in a
tracked Compose file or shell script.

The current dashboard catalog is intentionally a Dev catalog:

- `Arbor Acres Plus`: approved policy, `as_hatched`, `male`, and `female`.
- `Ross 308`: Dev fallback policy, `male` and `female` only.

The Cloud ML model registry remains the production source of truth. A fallback
must remain visible as a fallback; it must not be labelled as an approved
subscription.

## 1. Create a compatible active batch

Open **Barns → Batches** and create an `active` batch with the selected breed
and sex. The UI filters sex options to the compatible entries in the catalog.
Only `active` batches are resolvable by Edge.

Bind a registered device and, when used, its station. The Device selector is
limited to the batch farm/barn. If another active batch already owns the same
device/station, complete or cancel that batch before making a new binding.

## 2. Verify Cloud-to-Edge policy delivery

Check that Edge policy sync has received the context with the expected batch,
breed, sex, model policy, and revision. A successful delta with no changed
contexts is valid and refreshes cache freshness.

When moving a device to a newly-created batch, verify the new batch identity
appears even if its per-batch revision is numerically lower than the prior
batch. This prevents a device from remaining unassigned after reassignment.

## 3. Run a real Edge mock capture

From `cloud-layer/cloud-ml-model-service/vision-input-mock`, start the
real-Edge override only after the Edge stack is healthy:

```powershell
docker compose -f docker-compose.real-edge.yml -p farmiq-vision-input-mock up -d
```

Submit a capture with tenant, farm, barn, device, station, and session IDs. Do
not submit `batchId`; Edge must resolve and stamp it from its local policy
cache. See the mock README for the object-sequence request.

Expected result: one prediction per media object, including Batch/breed/sex,
model policy, prediction mode, and a fallback reason when no approved site
subscription exists.

## 4. Verify Cloud and Dashboard

Wait for the sync-forwarder ACK, then query the BFF session list and the
Analytics/Distribution views for the selected time range. The BFF accepts
`from`/`to` as well as `start_date`/`end_date`; the Dashboard must receive the
analytics object without an extra `{ data: ... }` envelope.

Confirm that session list/detail display the provenance fields and that
Analytics and Distribution contain the finalized measurements. A fallback
must display its reason rather than appearing as an approved model.

## 5. Rollback and troubleshooting

- If the binding is wrong, create a corrected Cloud binding and wait for the
  next Edge sync; do not modify Edge cache rows by hand.
- If the model is unavailable, keep the prediction in the documented fallback
  mode and investigate the Cloud subscription/package state.
- If results are duplicated, stop the mock and confirm Media Store's
  `inference_job_id` is reused rather than posting a second inference job.
- Tear down only the `farmiq-vision-input-mock` project or exact
  `bces-e2e-*` resources used for this validation.
