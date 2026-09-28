export const MQTT_EVENT_TYPES = [
  'telemetry.reading',
  'sensor.heartbeat',
  'device.status',
  'weighvision.session.created',
  'weighvision.weight.recorded',
  'weighvision.image.captured',
  'weighvision.inference.completed',
  'weighvision.session.finalized',
] as const

export type MqttEventType = (typeof MQTT_EVENT_TYPES)[number]

export const OUTBOX_EVENT_TYPES = [
  'telemetry.ingested',
  'telemetry.aggregated',
  'media.stored',
  'inference.completed',
  'weighvision.session.created',
  'weighvision.session.finalized',
  'feed.intake.recorded',
  'sync.batch.sent',
  'sync.batch.acked',
] as const

export type OutboxEventType = (typeof OUTBOX_EVENT_TYPES)[number]

// Local-only until a cloud consumer and explicit release policy are deployed.
export const SHADOW_EVENT_TYPES = ['weighvision.group_allocation.completed'] as const
export type ShadowEventType = (typeof SHADOW_EVENT_TYPES)[number]

export type EdgeEventType = MqttEventType | OutboxEventType

export const BATCH_CONTEXT_EVENT_TYPES = [
  'batch.upsert',
  'batch.activate',
  'batch.deactivate',
  'batch.binding.upsert',
  'batch.binding.remove',
] as const

export type BatchContextEventType = (typeof BATCH_CONTEXT_EVENT_TYPES)[number]

