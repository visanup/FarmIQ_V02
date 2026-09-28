import { z } from 'zod'

export const TelemetryReadingPayloadSchema = z.object({
  tenant_id: z.string().min(1),
  farm_id: z.string().min(1).optional(),
  barn_id: z.string().min(1).optional(),
  device_id: z.string().min(1),
  metric_type: z.string().min(1),
  metric_value: z.number(),
  unit: z.string().min(1).optional(),
  occurred_at: z.string().min(1),
})

export type TelemetryReadingPayload = z.infer<typeof TelemetryReadingPayloadSchema>

export const MediaStoredPayloadSchema = z.object({
  media_id: z.string().min(1).optional(),
  object_id: z.string().min(1).optional(),
  object_key: z.string().min(1),
  bucket: z.string().min(1).optional(),
  etag: z.string().min(1).optional(),
  captured_at: z.string().min(1),
  mime_type: z.string().min(1),
  size_bytes: z.number().int().nonnegative(),
  session_id: z.string().min(1).optional(),
  tenant_id: z.string().min(1).optional(),
  farm_id: z.string().min(1).optional(),
  barn_id: z.string().min(1).optional(),
  device_id: z.string().min(1).optional(),
})

export type MediaStoredPayload = z.infer<typeof MediaStoredPayloadSchema>

export const MediaImageCompleteRequestSchema = z.object({
  tenant_id: z.string().min(1),
  farm_id: z.string().min(1),
  barn_id: z.string().min(1),
  device_id: z.string().min(1),
  object_key: z.string().min(1),
  mime_type: z.string().min(1),
  size_bytes: z.number().int().nonnegative().optional(),
  captured_at: z.string().min(1).optional(),
  session_id: z.string().min(1).optional(),
})

export type MediaImageCompleteRequest = z.infer<
  typeof MediaImageCompleteRequestSchema
>

export const MediaImagePresignRequestSchema = z.object({
  tenant_id: z.string().min(1),
  farm_id: z.string().min(1),
  barn_id: z.string().min(1),
  device_id: z.string().min(1),
  content_type: z.string().min(1),
  filename: z.string().min(1),
})

export type MediaImagePresignRequest = z.infer<
  typeof MediaImagePresignRequestSchema
>

export const InferenceCompletedPayloadSchema = z.object({
  inference_result_id: z.string().min(1),
  predicted_weight_kg: z.number(),
  confidence: z.number().min(0).max(1),
  model_version: z.string().min(1),
  occurred_at: z.string().min(1),
  media_id: z.string().min(1).optional(),
  session_id: z.string().min(1).optional(),
  tenant_id: z.string().min(1).optional(),
  farm_id: z.string().min(1).optional(),
  barn_id: z.string().min(1).optional(),
  device_id: z.string().min(1).optional(),
})

export type InferenceCompletedPayload = z.infer<typeof InferenceCompletedPayloadSchema>

// Observation-only event. Must not be consumed as an individual measured weight.
export const GroupAllocationCompletedPayloadSchema = z.object({
  schema_version: z.literal('1.0'),
  event_type: z.literal('weighvision.group_allocation.completed'),
  session_id: z.string().min(1).nullable(),
  capture_id: z.string().min(1).nullable(),
  model_version: z.string().min(1),
  prediction_mode: z.literal('weak_group_allocation'),
  shadow_only: z.literal(true),
  individual_accuracy_validated: z.literal(false),
  decision_use_allowed: z.literal(false),
  prediction_status: z.enum(['WEAK_ALLOCATION', 'REJECTED_QUALITY', 'REJECTED_MODEL_UNAVAILABLE']),
  group_total_weight_g: z.number().finite().positive().optional(),
  quality_reasons: z.array(z.string()),
  allocations: z.array(z.object({
    detection_index: z.number().int().nonnegative(),
    raw_score_g: z.number().finite().positive(),
    allocated_weight_g: z.number().finite().positive(),
    prediction_status: z.literal('WEAK_ALLOCATION'),
  })),
}).superRefine((value, ctx) => {
  const ids = value.allocations.map(row => row.detection_index)
  const total = value.allocations.reduce((sum, row) => sum + row.allocated_weight_g, 0)
  if (value.prediction_status === 'WEAK_ALLOCATION') {
    if (!value.session_id || !value.capture_id || !value.group_total_weight_g || !ids.length ||
        new Set(ids).size !== ids.length || Math.abs(total - value.group_total_weight_g) > 0.1) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'Invalid allocation identity or total' })
    }
  } else if (ids.length || !value.quality_reasons.length) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'Rejected sessions require reasons and no allocations' })
  }
})
export type GroupAllocationCompletedPayload = z.infer<typeof GroupAllocationCompletedPayloadSchema>

export const WeighVisionSessionCreatedPayloadSchema = z.object({
  session_id: z.string().min(1),
  start_at: z.string().min(1),
  device_id: z.string().min(1),
  tenant_id: z.string().min(1).optional(),
  farm_id: z.string().min(1).optional(),
  barn_id: z.string().min(1).optional(),
  station_id: z.string().min(1).optional(),
  batch_id: z.string().min(1).optional(),
})

export type WeighVisionSessionCreatedPayload = z.infer<
  typeof WeighVisionSessionCreatedPayloadSchema
>

export const WeighVisionSessionFinalizedPayloadSchema = z.object({
  session_id: z.string().min(1),
  end_at: z.string().min(1),
  final_weight_kg: z.number().optional(),
  device_id: z.string().min(1).optional(),
  image_count: z.number().int().nonnegative().optional(),
  tenant_id: z.string().min(1).optional(),
})

export type WeighVisionSessionFinalizedPayload = z.infer<
  typeof WeighVisionSessionFinalizedPayloadSchema
>

export const WeighVisionSessionAttachRequestSchema = z.object({
  media_id: z.string().min(1).optional(),
  inference_result_id: z.string().min(1).optional(),
  captured_at: z.string().min(1).optional(),
}).refine((v: { media_id?: string; inference_result_id?: string }) => v.media_id || v.inference_result_id, {
  message: 'media_id or inference_result_id is required',
})

export type WeighVisionSessionAttachRequest = z.infer<
  typeof WeighVisionSessionAttachRequestSchema
>
