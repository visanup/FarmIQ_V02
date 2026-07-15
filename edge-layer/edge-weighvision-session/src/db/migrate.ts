import { PrismaClient } from '@prisma/client'

async function main() {
  const prisma = new PrismaClient()
  await prisma.$connect()

  await prisma.$executeRawUnsafe(`CREATE EXTENSION IF NOT EXISTS pgcrypto;`)

  await prisma.$executeRawUnsafe(`
    CREATE TABLE IF NOT EXISTS weight_sessions (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      session_id TEXT NOT NULL UNIQUE,
      tenant_id TEXT NOT NULL,
      farm_id TEXT NOT NULL,
      barn_id TEXT NOT NULL,
      device_id TEXT NOT NULL,
      station_id TEXT NOT NULL,
      batch_id TEXT NULL,
      status TEXT NOT NULL,
      start_at TIMESTAMPTZ NOT NULL,
      end_at TIMESTAMPTZ NULL,
      initial_weight_kg NUMERIC(10, 2) NULL,
      final_weight_kg NUMERIC(10, 2) NULL,
      image_count INTEGER NOT NULL DEFAULT 0,
      inference_result_id TEXT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
  `)
  await prisma.$executeRawUnsafe(`
    CREATE INDEX IF NOT EXISTS weight_sessions_tenant_session_idx
    ON weight_sessions(tenant_id, session_id);
  `)

  await prisma.$executeRawUnsafe(`
    CREATE TABLE IF NOT EXISTS session_weights (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      session_id TEXT NOT NULL,
      tenant_id TEXT NOT NULL,
      weight_kg NUMERIC(10, 2) NOT NULL,
      occurred_at TIMESTAMPTZ NOT NULL,
      event_id TEXT NOT NULL,
      trace_id TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
  `)
  await prisma.$executeRawUnsafe(`
    CREATE UNIQUE INDEX IF NOT EXISTS session_weights_tenant_event_uidx
    ON session_weights(tenant_id, event_id);
  `)
  await prisma.$executeRawUnsafe(`
    CREATE INDEX IF NOT EXISTS session_weights_session_idx
    ON session_weights(session_id);
  `)

  await prisma.$executeRawUnsafe(`
    CREATE TABLE IF NOT EXISTS session_media_bindings (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      session_id TEXT NOT NULL,
      tenant_id TEXT NOT NULL,
      media_object_id TEXT NOT NULL,
      occurred_at TIMESTAMPTZ NOT NULL,
      event_id TEXT NOT NULL,
      trace_id TEXT NOT NULL,
      is_bound BOOLEAN NOT NULL DEFAULT FALSE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
  `)
  await prisma.$executeRawUnsafe(`
    CREATE UNIQUE INDEX IF NOT EXISTS session_media_bindings_tenant_event_uidx
    ON session_media_bindings(tenant_id, event_id);
  `)
  await prisma.$executeRawUnsafe(`
    CREATE UNIQUE INDEX IF NOT EXISTS session_media_bindings_session_media_uidx
    ON session_media_bindings(session_id, media_object_id);
  `)
  await prisma.$executeRawUnsafe(`
    CREATE INDEX IF NOT EXISTS session_media_bindings_session_idx
    ON session_media_bindings(session_id);
  `)

  await prisma.$executeRawUnsafe(`
    CREATE TABLE IF NOT EXISTS outbox (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      event_type TEXT NOT NULL,
      payload JSONB NOT NULL,
      trace_id TEXT NOT NULL,
      tenant_id TEXT NOT NULL,
      processed BOOLEAN NOT NULL DEFAULT FALSE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
  `)

  await prisma.$executeRawUnsafe(`
    CREATE TABLE IF NOT EXISTS session_capture_metadata (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      session_id TEXT NOT NULL,
      tenant_id TEXT NOT NULL,
      capture_id TEXT NULL,
      event_id TEXT NOT NULL,
      trace_id TEXT NOT NULL,
      source_event_type TEXT NOT NULL,
      metadata_schema_version TEXT NOT NULL,
      feature_schema_version TEXT NOT NULL,
      occurred_at TIMESTAMPTZ NOT NULL,
      media_ids JSONB NULL,
      raw_metadata JSONB NOT NULL,
      normalized_features JSONB NOT NULL,
      selected_detection_index INTEGER NULL,
      detection_count INTEGER NOT NULL DEFAULT 0,
      roi_count INTEGER NULL,
      area_mm2 NUMERIC(14, 2) NULL,
      mask_area_px2 NUMERIC(14, 2) NULL,
      bbox_x1 INTEGER NULL,
      bbox_y1 INTEGER NULL,
      bbox_x2 INTEGER NULL,
      bbox_y2 INTEGER NULL,
      object_height_mm NUMERIC(14, 2) NULL,
      object_width_mm NUMERIC(14, 2) NULL,
      object_length_mm NUMERIC(14, 2) NULL,
      average_depth_mm NUMERIC(14, 2) NULL,
      median_depth_mm NUMERIC(14, 2) NULL,
      distance_mm NUMERIC(14, 2) NULL,
      confidence_score NUMERIC(8, 4) NULL,
      scale_weight_kg NUMERIC(10, 2) NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
  `)
  await prisma.$executeRawUnsafe(`
    CREATE UNIQUE INDEX IF NOT EXISTS session_capture_metadata_tenant_event_uidx
    ON session_capture_metadata(tenant_id, event_id);
  `)
  await prisma.$executeRawUnsafe(`
    CREATE INDEX IF NOT EXISTS session_capture_metadata_session_idx
    ON session_capture_metadata(session_id, occurred_at);
  `)
  await prisma.$executeRawUnsafe(`
    CREATE INDEX IF NOT EXISTS session_capture_metadata_capture_idx
    ON session_capture_metadata(tenant_id, capture_id);
  `)

  await prisma.$disconnect()
  console.log('edge-weighvision-session DB schema ensured')
}

main().catch((error) => {
  console.error('edge-weighvision-session db:migrate failed', error)
  process.exitCode = 1
})
