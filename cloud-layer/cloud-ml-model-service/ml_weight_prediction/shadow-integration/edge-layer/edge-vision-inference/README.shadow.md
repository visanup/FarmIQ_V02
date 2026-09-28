# Experimental Arbor Acres allocation shadow

This branch is opt-in and does not replace scalar inference. It runs only after
the existing job has completed and never attaches allocation as a session outcome.

Enable with `ALLOCATION_SHADOW_ENABLED=true`, `ALLOCATION_SHADOW_PACKAGE_DIR`
(read-only trusted package) and a deployment-pinned
`ALLOCATION_SHADOW_MANIFEST_SHA256`. Default is disabled. Use `Dockerfile.shadow`
and `requirements-shadow.txt` for the approved candidate's Python/ML runtime;
do not pass the joblib package to the legacy linear-model subscription.

Session metadata must include complete raw detections, group scale weight/stability,
calibration/tare evidence, ROI/image dimensions and actual breed/sex/age context.
Captures are matched by the job media ID, never merely by latest session capture.
One invalid detection rejects the entire group. Missing/ambiguous linkage rejects.

The service ensures `allocation_shadow_events` and `session_bird_allocations` in
its own PostgreSQL database using `app/allocation_shadow.sql`. Events remain
`held_shadow`; the production sync outbox and original scalar tables are unchanged.
`individual_accuracy_validated=false`, `decision_use_allowed=false` and
`shadow_only=true` are mandatory. Allocated grams are not measured bird weights.

The observation queue is best-effort, serialized, capped at eight tasks. Overflow
is logged and dropped to protect legacy latency. Monitor queue warnings, latency,
rejections, disk growth and scalar health before field rollout.

Set `ALLOCATION_SHADOW_ENABLED=false` and restart to rollback; retained rows are
not deleted. For the isolated local Compose deployment, mock inputs, commands,
verification and limits, see:

- [Plan and runbook](../../cloud-layer/cloud-ml-model-service/ml_weight_prediction/docs/SHADOW_ALLOCATION_IMPLEMENTATION.md)
- [Test report](../../cloud-layer/cloud-ml-model-service/ml_weight_prediction/docs/SHADOW_ALLOCATION_TEST_REPORT.md)

The vendored `app/weight_prediction` source is the training feature implementation
from `cloud-ml-model-service/ml_weight_prediction/src/weight_prediction` at this
integration. Update both copies together and revalidate/retrain when definitions
change; this candidate deliberately retains missing normalized centroids and a
fixed-zero height-outlier feature to preserve train/serve parity.
