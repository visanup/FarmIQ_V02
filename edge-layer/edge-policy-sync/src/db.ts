import { Pool } from 'pg'
import { logger } from './utils/logger'

export type PolicyDb = {
  pool: Pool
}

export async function createDbPool(databaseUrl: string): Promise<PolicyDb> {
  const pool = new Pool({ connectionString: databaseUrl })
  await ensureSchema(pool)
  return { pool }
}

async function ensureSchema(pool: Pool): Promise<void> {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS edge_config_cache (
      tenant_id TEXT NOT NULL,
      farm_id TEXT NOT NULL,
      barn_id TEXT NOT NULL,
      config_json JSONB NOT NULL,
      hash TEXT NULL,
      fetched_at TIMESTAMPTZ NOT NULL,
      source_etag TEXT NULL,
      last_error TEXT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (tenant_id, farm_id, barn_id)
    );
  `)

  await pool.query(`
    CREATE TABLE IF NOT EXISTS edge_config_sync_state (
      id INTEGER PRIMARY KEY,
      last_success_at TIMESTAMPTZ NULL,
      last_error_at TIMESTAMPTZ NULL,
      last_error TEXT NULL,
      consecutive_failures INTEGER NOT NULL DEFAULT 0
    );
  `)

  await pool.query(`
    CREATE TABLE IF NOT EXISTS edge_model_subscription_cache (
      tenant_id TEXT NOT NULL,
      site_id TEXT NOT NULL,
      resolved_json JSONB NOT NULL,
      hash TEXT NULL,
      fetched_at TIMESTAMPTZ NOT NULL,
      source_etag TEXT NULL,
      last_error TEXT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (tenant_id, site_id)
    );
  `)

  await pool.query(`
    CREATE TABLE IF NOT EXISTS edge_batch_context_cache (
      tenant_id TEXT NOT NULL,
      farm_id TEXT NOT NULL,
      barn_id TEXT NOT NULL,
      batch_id TEXT NOT NULL,
      revision INTEGER NOT NULL,
      source_revision BIGINT NOT NULL DEFAULT 0,
      lifecycle TEXT NOT NULL,
      species TEXT NOT NULL,
      breed_code TEXT NULL,
      sex TEXT NULL,
      start_date TIMESTAMPTZ NULL,
      end_date TIMESTAMPTZ NULL,
      model_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      source_event_id TEXT NULL,
      hash TEXT NOT NULL,
      source_etag TEXT NULL,
      fetched_at TIMESTAMPTZ NOT NULL,
      expires_at TIMESTAMPTZ NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (tenant_id, batch_id)
    );
  `)
  await pool.query(`
    ALTER TABLE edge_batch_context_cache
      ADD COLUMN IF NOT EXISTS source_revision BIGINT NOT NULL DEFAULT 0;
  `)

  await pool.query(`
    CREATE TABLE IF NOT EXISTS edge_batch_binding_cache (
      tenant_id TEXT NOT NULL,
      batch_id TEXT NOT NULL,
      binding_id TEXT NOT NULL,
      device_id TEXT NOT NULL,
      station_id TEXT NULL,
      revision INTEGER NOT NULL,
      active BOOLEAN NOT NULL DEFAULT TRUE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (tenant_id, binding_id)
    );
    CREATE INDEX IF NOT EXISTS edge_batch_binding_lookup_idx
      ON edge_batch_binding_cache (tenant_id, device_id, station_id, active);
  `)

  await pool.query(`
    CREATE TABLE IF NOT EXISTS edge_batch_context_sync_state (
      tenant_id TEXT NOT NULL,
      site_id TEXT NOT NULL,
      revision BIGINT NOT NULL DEFAULT 0,
      source_etag TEXT NULL,
      last_success_at TIMESTAMPTZ NULL,
      last_error_at TIMESTAMPTZ NULL,
      last_error TEXT NULL,
      consecutive_failures INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (tenant_id, site_id)
    );
  `)

  await pool.query(`
    INSERT INTO edge_config_sync_state (id)
    VALUES (1)
    ON CONFLICT (id) DO NOTHING;
  `)

  logger.info('edge-policy-sync schema ensured')
}
