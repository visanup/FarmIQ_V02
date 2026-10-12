# YOLO legacy cleanup checklist

- [x] Searched all Python runtime modules for callers of `PredictorService`,
  `GridBuilderService`, and `ResultProcessorService`; none were found.
- [x] Confirmed the active job path calls `InferenceService.run_inference` with
  session-derived normalized features, not a YOLO predictor.
- [x] Confirmed `requirements.txt` has no `ultralytics` or `torch` dependency.
- [x] Removed unused YOLO service modules and their Docker model-copy step.
- [x] Removed obsolete `MODEL_PATH` configuration and legacy YOLO documentation.
- [x] Built `farmiq-edge-vision-inference:hybrid-trial-75s25v` after removal.
- [x] Ran 7 inference and Hybrid Trial tests in a disposable container.
- [x] Ran an in-container runtime smoke test: legacy mode leaves Hybrid disabled;
  explicit opt-in returns a Hybrid weight prediction.
- [x] Ran an isolated real-Edge loop with `iot-vision-input-mock`: session,
  media upload, capture metadata, inference job, result persistence and
  `sync_outbox` `inference.completed` acknowledgement all succeeded.
- [ ] Confirm `/api/v1/inference/models` reports the expected package/stub
  runtime after deployment to an Edge environment with its database available.

## Validation note

The Hybrid test loads the existing XGBoost `joblib` artifact successfully but
emits an upstream serialized-model compatibility warning. Prediction succeeds;
re-exporting the visual component in the deployed XGBoost runtime remains a
separate hardening task before production promotion.
