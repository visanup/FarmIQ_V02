import { z } from 'zod'

export const BatchContextEventTypeSchema = z.enum([
  'batch.upsert',
  'batch.activate',
  'batch.deactivate',
  'batch.binding.upsert',
  'batch.binding.remove',
])

export type BatchContextEventType = z.infer<typeof BatchContextEventTypeSchema>

export const BatchContextEventSchema = z.object({
  eventId: z.string().min(1),
  eventType: BatchContextEventTypeSchema,
  revision: z.number().int().positive(),
  occurredAt: z.string().datetime(),
  tenantId: z.string().min(1),
  farmId: z.string().min(1),
  barnId: z.string().min(1),
  batchId: z.string().min(1),
  status: z.string().min(1),
  species: z.string().min(1),
  breedCode: z.string().min(1).nullable(),
  sex: z.enum(['as_hatched', 'male', 'female']).nullable(),
  startDate: z.string().datetime().nullable(),
  endDate: z.string().datetime().nullable(),
  deviceBindings: z.array(z.object({
    deviceId: z.string().min(1),
    stationId: z.string().min(1).nullable(),
  })),
})

export type BatchContextEvent = z.infer<typeof BatchContextEventSchema>
