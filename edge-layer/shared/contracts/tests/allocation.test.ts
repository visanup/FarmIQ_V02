import { GroupAllocationCompletedPayloadSchema as schema } from '../src/payloads'
import { OUTBOX_EVENT_TYPES, SHADOW_EVENT_TYPES } from '../src/eventTypes'

const valid = {
  schema_version: '1.0', event_type: 'weighvision.group_allocation.completed',
  session_id: 's', capture_id: 'c', model_version: 'experimental',
  prediction_mode: 'weak_group_allocation', shadow_only: true,
  individual_accuracy_validated: false, decision_use_allowed: false,
  prediction_status: 'WEAK_ALLOCATION', group_total_weight_g: 800,
  quality_reasons: [], allocations: [
    { detection_index: 0, raw_score_g: 400, allocated_weight_g: 400, prediction_status: 'WEAK_ALLOCATION' },
    { detection_index: 1, raw_score_g: 400, allocated_weight_g: 400, prediction_status: 'WEAK_ALLOCATION' },
  ],
}

test('accepts reconciled shadow allocation', () => expect(schema.safeParse(valid).success).toBe(true))
test('rejects decision use', () => expect(schema.safeParse({...valid, decision_use_allowed: true}).success).toBe(false))
test('rejects false accuracy claim', () => expect(schema.safeParse({...valid, individual_accuracy_validated: true}).success).toBe(false))
test('rejects unreconciled total', () => expect(schema.safeParse({...valid, group_total_weight_g: 900}).success).toBe(false))
test('rejects duplicate detections', () => expect(schema.safeParse({...valid, allocations: [valid.allocations[0], valid.allocations[0]]}).success).toBe(false))
test('rejected result contains reasons and no birds', () => {
  expect(schema.safeParse({...valid, prediction_status: 'REJECTED_QUALITY', allocations: [], quality_reasons: ['unstable']}).success).toBe(true)
  expect(schema.safeParse({...valid, prediction_status: 'REJECTED_QUALITY'}).success).toBe(false)
})
test('allocation is never routed through production outbox', () => {
  expect(SHADOW_EVENT_TYPES).toContain(valid.event_type)
  expect(OUTBOX_EVENT_TYPES).not.toContain(valid.event_type)
})
