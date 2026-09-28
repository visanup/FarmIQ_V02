import { PrismaClient } from '@prisma/client'

export async function ensureMediaSchema(prisma: PrismaClient): Promise<void> {
  await prisma.$executeRawUnsafe(`
    CREATE TABLE IF NOT EXISTS media_objects (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id TEXT NOT NULL,
      farm_id TEXT NOT NULL,
      barn_id TEXT NOT NULL,
      device_id TEXT NOT NULL,
      session_id TEXT NULL,
      bucket TEXT NOT NULL,
      object_key TEXT NOT NULL,
      etag TEXT NULL,
      mime_type TEXT NOT NULL,
      size_bytes BIGINT NULL,
      captured_at TIMESTAMPTZ NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
  `)

  // Idempotency: allow the same object_key to exist across tenants, but prevent duplicates within a tenant.
  await prisma.$executeRawUnsafe(`
    CREATE UNIQUE INDEX IF NOT EXISTS media_objects_tenant_object_key_uidx
    ON media_objects(tenant_id, object_key);
  `)

  await prisma.$executeRawUnsafe(`
    CREATE INDEX IF NOT EXISTS media_objects_tenant_session_idx
    ON media_objects(tenant_id, session_id);
  `)

  await prisma.$executeRawUnsafe(`
    CREATE INDEX IF NOT EXISTS media_objects_tenant_device_captured_idx
    ON media_objects(tenant_id, device_id, captured_at DESC);
  `)

  await prisma.$executeRawUnsafe(`
    CREATE UNIQUE INDEX IF NOT EXISTS media_objects_bucket_key_uidx
    ON media_objects(bucket, object_key);
  `)

  // edge-sync-forwarder consumes this transactional outbox. Keep it local to
  // the media database because a completed upload must not be acknowledged
  // before its media.stored event is durable.
  await prisma.$executeRawUnsafe(`
    CREATE TABLE IF NOT EXISTS sync_outbox (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id TEXT NOT NULL, farm_id TEXT, barn_id TEXT, device_id TEXT,
      session_id TEXT, event_type TEXT NOT NULL,
      occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), trace_id TEXT,
      payload_json JSONB NOT NULL, payload_size_bytes INTEGER,
      status TEXT NOT NULL DEFAULT 'pending', attempt_count INTEGER NOT NULL DEFAULT 0,
      last_attempt_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), priority INTEGER NOT NULL DEFAULT 0,
      next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
  `)
  await prisma.$executeRawUnsafe(`
    CREATE INDEX IF NOT EXISTS idx_media_sync_outbox_status_next
    ON sync_outbox(status, next_attempt_at ASC);
  `)
}
