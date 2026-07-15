import { processIngressMessage } from '../../src/ingress/processor'
import { InMemoryDedupeStore } from '../../src/db/dedupeStore'
import {
  DeviceAllowlistStore,
  StationAllowlistStore,
} from '../../src/db/allowlistStore'
import { LastSeenStore } from '../../src/db/lastSeenStore'
import { ParsedTopic } from '../../src/ingress/topic'

describe('Batch 1 traceability smoke', () => {
  const allowlistedDevice: DeviceAllowlistStore = {
    getDevice: async () => ({
      tenant_id: 'tenant-smoke',
      device_id: 'device-smoke',
      farm_id: 'farm-smoke',
      barn_id: 'barn-smoke',
      enabled: true,
      notes: null,
    }),
  }
  const allowlistedStation: StationAllowlistStore = {
    getStation: async () => ({
      tenant_id: 'tenant-smoke',
      station_id: 'station-smoke',
      farm_id: 'farm-smoke',
      barn_id: 'barn-smoke',
      enabled: true,
      notes: null,
    }),
  }
  const noopLastSeen: LastSeenStore = { upsertLastSeen: async () => {} }

  beforeEach(() => {
    ;(global as any).fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => '',
    })
  })

  it('routes mocked capture metadata to edge session persistence with the required fields intact', async () => {
    const topic: ParsedTopic = {
      kind: 'weighvision',
      tenantId: 'tenant-smoke',
      farmId: 'farm-smoke',
      barnId: 'barn-smoke',
      stationId: 'station-smoke',
      sessionId: 'session-smoke',
      eventType: 'weighvision.inference.completed',
    }

    const mockedMetadata = {
      image_id: 'capture-smoke-001',
      timestamp: '2026-07-14T08:30:00Z',
      roi_count: 1,
      scale: {
        weight_kg: 1.94,
      },
      detections: [
        {
          confidence: 0.93,
          bbox_xyxy: [12, 22, 132, 242],
          mask_xy: [
            [12, 22],
            [132, 22],
            [132, 242],
            [12, 242],
          ],
          depth_mm: 834.7,
          height_mm: 124.5,
          width_mm: 78.2,
          length_mm: 149.1,
          area_xy_mm2: 10123.4,
        },
      ],
    }

    const decision = await processIngressMessage({
      topic,
      rawTopic:
        'iot/weighvision/tenant-smoke/farm-smoke/barn-smoke/station-smoke/session/session-smoke/weighvision.inference.completed',
      message: Buffer.from(
        JSON.stringify({
          schema_version: '1.0',
          event_id: 'event-smoke-001',
          trace_id: 'trace-smoke-001',
          tenant_id: 'tenant-smoke',
          device_id: 'device-smoke',
          event_type: 'weighvision.inference.completed',
          ts: '2026-07-14T08:30:01Z',
          payload: {
            capture_id: 'capture-smoke-001',
            media_ids: ['media-left-001', 'media-vis-001'],
            metadata_schema: {
              name: 'farmiq.weighvision.capture-metadata',
              version: '1.0',
            },
            feature_schema: {
              version: '1.0',
            },
            metadata: mockedMetadata,
          },
        })
      ),
      deps: {
        dedupe: new InMemoryDedupeStore(),
        deviceAllowlist: allowlistedDevice,
        stationAllowlist: allowlistedStation,
        lastSeen: noopLastSeen,
        downstream: {
          telemetryBaseUrl: 'http://telemetry',
          weighvisionBaseUrl: 'http://weighvision-session',
          timeoutMs: 50,
        },
        dedupeTtlMs: 60_000,
      },
    })

    expect(decision).toMatchObject({
      action: 'processed',
      routedTo: 'edge-weighvision-session',
    })

    const [url, options] = (global as any).fetch.mock.calls[0]
    expect(url).toBe(
      'http://weighvision-session/api/v1/weighvision/sessions/session-smoke/metadata'
    )
    const body = JSON.parse(options.body as string)

    expect(body).toMatchObject({
      tenantId: 'tenant-smoke',
      farmId: 'farm-smoke',
      barnId: 'barn-smoke',
      deviceId: 'device-smoke',
      stationId: 'station-smoke',
      eventId: 'event-smoke-001',
      captureId: 'capture-smoke-001',
      eventSchemaVersion: '1.0',
      sourceEventType: 'weighvision.inference.completed',
      mediaIds: ['media-left-001', 'media-vis-001'],
    })
    expect(body.metadata).toMatchObject(mockedMetadata)
  })
})
