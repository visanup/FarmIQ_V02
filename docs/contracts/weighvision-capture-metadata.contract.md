Purpose: Define the canonical metadata contract for WeighVision capture metadata used across IoT, Edge, and Cloud.  
Scope: Raw capture JSON, normalized feature mapping, and ownership boundaries for Batch 1 traceability work.  
Owner: FarmIQ Edge and IoT Architecture  
Last updated: 2026-07-14  

---

## Objective

This contract defines the canonical metadata shape for WeighVision capture data after field deployment hardening.

It is the reference for:

- IoT capture output
- Edge raw metadata persistence
- Edge normalized feature mapping
- Edge-to-Cloud metadata synchronization
- Cloud-side audit and training-data extraction

---

## Canonical schema identity

- `metadata_schema.name`: `farmiq.weighvision.capture-metadata`
- `metadata_schema.version`: `1.0`
- `feature_schema.version`: `1.0`

---

## Raw metadata contract

Minimum required top-level fields:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `timestamp` | ISO datetime string | Yes | capture timestamp |
| `image_id` | string | Yes | canonical capture identifier |
| `detections` | array | Yes | may be empty |
| `scale` | object | No | load-cell context if available |
| `roi` | object | No | ROI context |
| `camera` | object | No | camera calibration context |
| `height_estimation` | object | No | floor depth and related values |

Minimum required detection-level fields when a detection exists:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `confidence` | number | Yes | confidence score |
| `bbox_xyxy` | number[4] | Yes | `[x1, y1, x2, y2]` |
| `mask_xy` | array | No | polygon points used to derive mask area if present |
| `depth_mm` | number | No | selected depth or distance surrogate |
| `height_mm` | number | No | object height |
| `width_mm` | number | No | object width |
| `length_mm` | number | No | object length |
| `area_xy_mm2` | number | No | projected area in mm^2 |

---

## Canonical normalized feature mapping

For Batch 1, Edge persists the following normalized fields in `session_capture_metadata`:

| Canonical field | Raw JSON source |
| --- | --- |
| `capture_id` | `image_id` or `capture_id` |
| `detection_count` | `len(detections)` |
| `roi_count` | `roi_count` |
| `area_mm2` | `detections[selected].area_xy_mm2` |
| `mask_area_px2` | `detections[selected].mask_area_px2` or derived from `mask_xy` |
| `bbox_x1..bbox_y2` | `detections[selected].bbox_xyxy` |
| `object_height_mm` | `detections[selected].height_mm` |
| `object_width_mm` | `detections[selected].width_mm` |
| `object_length_mm` | `detections[selected].length_mm` |
| `average_depth_mm` | `detections[selected].average_depth_mm` or fallback `depth_mm` |
| `median_depth_mm` | `detections[selected].median_depth_mm` or fallback `depth_mm` |
| `distance_mm` | `detections[selected].distance_mm` or fallback depth |
| `confidence_score` | `detections[selected].confidence` |
| `scale_weight_kg` | `scale.weight_kg` |

Selection rule for `selected` detection in Batch 1:

- choose the detection with the largest available `area_xy_mm2`
- if unavailable, choose the detection with the largest available mask area
- if still unavailable, choose the first detection

---

## Ownership by layer

| Layer | Responsibility |
| --- | --- |
| IoT | generate raw capture metadata and publish it with `weighvision.inference.completed` |
| Edge ingress | route metadata event to session persistence |
| Edge session service | persist raw JSON and normalized features in `session_capture_metadata` |
| Edge sync forwarder | push versioned metadata event to Cloud through `cloud-ingestion` |
| Cloud readmodel | persist `weighvision.inference.completed` for audit and downstream analytics |

---

## Batch 1 traceability requirements

One session is considered traceable only if:

1. raw capture JSON exists in IoT output
2. the same capture is persisted in Edge `session_capture_metadata.raw_metadata`
3. flattened key fields exist in Edge typed columns
4. the corresponding `weighvision.inference.completed` event exists in Edge `sync_outbox`
5. the event is visible in Cloud readmodel storage after ingestion

---

## Non-goals in Batch 1

- final ML feature engineering for training
- advanced depth-statistics derivation beyond current fallbacks
- model registry or prediction control-plane behavior
