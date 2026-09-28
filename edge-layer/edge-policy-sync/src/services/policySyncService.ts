import crypto from 'crypto'
import { Pool } from 'pg'
import { EdgeContext, PolicySyncConfig } from '../config'
import { logger } from '../utils/logger'

export type SyncResult = {
  ok: boolean
  error?: string
}

type BatchContextPayload = {
  mode: 'snapshot' | 'delta'
  reset: boolean
  nextRevision: number
  contexts: Array<{
    batchId: string
    tenantId: string
    farmId: string
    barnId: string
    revision: number
    status: string
    species: string
    breedCode: string | null
    sex: string | null
    startDate: string | null
    endDate: string | null
    deviceBindings: Array<{ bindingId: string; deviceId: string; stationId: string | null }>
    modelPolicy?: Record<string, unknown>
  }>
}

export class PolicySyncService {
  private readonly pool: Pool
  private readonly config: PolicySyncConfig
  private resolutionObserver?: (outcome: 'resolved' | 'unassigned' | 'ambiguous' | 'stale') => void

  constructor(pool: Pool, config: PolicySyncConfig) {
    this.pool = pool
    this.config = config
  }

  async syncAll(): Promise<SyncResult> {
    if (!this.config.contexts.length) {
      await this.updateFailureState('No contexts configured')
      return { ok: false, error: 'No contexts configured' }
    }

    try {
      for (const context of this.config.contexts) {
        await this.syncContext(context)
        if (this.config.batchContextCacheEnabled && context.siteId) {
          await this.syncBatchContext(context)
        }
      }

      await this.updateSuccessState()
      return { ok: true }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      await this.updateFailureState(message)
      return { ok: false, error: message }
    }
  }

  async getEffectiveConfig(context: EdgeContext) {
    const result = await this.pool.query(
      `
      SELECT tenant_id, farm_id, barn_id, config_json, hash, fetched_at, source_etag
      FROM edge_config_cache
      WHERE tenant_id = $1 AND farm_id = $2 AND barn_id = $3
      `,
      [context.tenantId, context.farmId, context.barnId]
    )

    return result.rows[0] || null
  }

  async getEffectiveModelSubscription(tenantId: string, siteId: string) {
    const result = await this.pool.query(
      `
      SELECT tenant_id, site_id, resolved_json, hash, fetched_at, source_etag
      FROM edge_model_subscription_cache
      WHERE tenant_id = $1 AND site_id = $2
      `,
      [tenantId, siteId]
    )
    return result.rows[0] || null
  }

  async getSyncState() {
    const state = await this.pool.query(
      `SELECT last_success_at, last_error_at, last_error, consecutive_failures
       FROM edge_config_sync_state WHERE id = 1`
    )

    const entries = await this.pool.query('SELECT COUNT(*)::int AS count FROM edge_config_cache')
    const batchEntries = await this.pool.query(
      `SELECT COUNT(*)::int AS count,
              EXTRACT(EPOCH FROM (NOW() - MIN(fetched_at)))::float AS oldest_age_seconds
       FROM edge_batch_context_cache WHERE lifecycle = 'active'`
    )
    const batchState = await this.pool.query(
      `SELECT MAX(last_success_at) AS last_success_at,
              SUM(consecutive_failures)::int AS consecutive_failures
       FROM edge_batch_context_sync_state`
    )

    return {
      state: state.rows[0],
      cacheEntries: entries.rows[0]?.count ?? 0,
      batchCacheEntries: batchEntries.rows[0]?.count ?? 0,
      batchCacheOldestAgeSeconds: batchEntries.rows[0]?.oldest_age_seconds ?? null,
      batchState: batchState.rows[0] || null,
    }
  }

  setResolutionObserver(observer: (outcome: 'resolved' | 'unassigned' | 'ambiguous' | 'stale') => void): void {
    this.resolutionObserver = observer
  }

  private resolution<T extends 'resolved' | 'unassigned' | 'ambiguous' | 'stale'>(value: { outcome: T } & Record<string, unknown>) {
    this.resolutionObserver?.(value.outcome)
    return value
  }

  async resolveBatchContext(tenantId: string, deviceId: string, requestedStationId: string) {
    if (!this.config.batchContextCacheEnabled) {
      return this.resolution({ outcome: 'unassigned' as const, reason: 'FEATURE_DISABLED' })
    }
    const station = requestedStationId === '-' ? null : requestedStationId
    const result = await this.pool.query(
      `SELECT c.*, b.device_id, b.station_id
       FROM edge_batch_binding_cache b
       JOIN edge_batch_context_cache c
         ON c.tenant_id = b.tenant_id AND c.batch_id = b.batch_id
       WHERE b.tenant_id = $1 AND b.device_id = $2 AND b.active = TRUE
         AND (($3::text IS NULL AND b.station_id IS NULL) OR b.station_id = $3)
         AND c.lifecycle = 'active'
       ORDER BY c.revision DESC, c.batch_id`,
      [tenantId, deviceId, station]
    )
    if (result.rows.length === 0) return this.resolution({ outcome: 'unassigned' as const, reason: 'NO_ACTIVE_BINDING' })
    const batchIds = new Set(result.rows.map((row) => row.batch_id))
    if (batchIds.size > 1) {
      return this.resolution({ outcome: 'ambiguous' as const, reason: 'MULTIPLE_ACTIVE_BATCHES', candidateBatchIds: [...batchIds] })
    }
    const row = result.rows[0]
    const stale = new Date(row.expires_at).getTime() <= Date.now()
    const context = {
      tenantId: row.tenant_id, farmId: row.farm_id, barnId: row.barn_id,
      batchId: row.batch_id, deviceId: row.device_id, stationId: row.station_id,
      revision: row.revision, species: row.species, breedCode: row.breed_code,
      sex: row.sex, startDate: row.start_date, endDate: row.end_date,
      modelPolicy: row.model_policy_json, fetchedAt: row.fetched_at, expiresAt: row.expires_at,
    }
    return stale
      ? this.resolution({ outcome: 'stale' as const, reason: 'CACHE_EXPIRED', context })
      : this.resolution({ outcome: 'resolved' as const, reason: null, context })
  }

  private async syncContext(context: EdgeContext): Promise<void> {
    const url = new URL('/api/v1/config/context', this.config.bffBaseUrl)
    url.searchParams.set('tenant_id', context.tenantId)
    url.searchParams.set('farm_id', context.farmId)
    url.searchParams.set('barn_id', context.barnId)

    const controller = new AbortController()
    const timeout = setTimeout(
      () => controller.abort(),
      this.config.requestTimeoutSeconds * 1000
    )

    try {
      const headers: Record<string, string> = {
        'x-request-id': `edge-policy-sync-${Date.now()}`,
        'x-tenant-id': context.tenantId,
      }

      if (this.config.cloudToken) {
        headers.Authorization = `Bearer ${this.config.cloudToken}`
      }

      const response = await fetch(url.toString(), {
        method: 'GET',
        headers,
        signal: controller.signal,
      })

      if (!response.ok) {
        const body = await response.text().catch(() => '')
        throw new Error(`BFF response ${response.status}: ${body}`)
      }

      const payload = await response.json()
      const etag = response.headers.get('etag')
      const hash = this.hashPayload(payload)

      await this.pool.query(
        `
        INSERT INTO edge_config_cache
          (tenant_id, farm_id, barn_id, config_json, hash, fetched_at, source_etag, last_error, updated_at)
        VALUES ($1, $2, $3, $4, $5, NOW(), $6, NULL, NOW())
        ON CONFLICT (tenant_id, farm_id, barn_id)
        DO UPDATE SET
          config_json = EXCLUDED.config_json,
          hash = EXCLUDED.hash,
          fetched_at = EXCLUDED.fetched_at,
          source_etag = EXCLUDED.source_etag,
          last_error = NULL,
          updated_at = NOW()
        `,
        [context.tenantId, context.farmId, context.barnId, payload, hash, etag]
      )

      logger.info('Policy synced', {
        tenantId: context.tenantId,
        farmId: context.farmId,
        barnId: context.barnId,
      })

      if (context.siteId) {
        try {
          await this.syncModelSubscription(context)
        } catch (error) {
          logger.warn('Legacy model subscription sync skipped', {
            tenantId: context.tenantId,
            siteId: context.siteId,
            error: error instanceof Error ? error.message : String(error),
          })
        }
      }
    } finally {
      clearTimeout(timeout)
    }
  }

  private async syncBatchContext(context: EdgeContext): Promise<void> {
    if (!context.siteId) return
    const state = await this.pool.query(
      `SELECT revision, source_etag FROM edge_batch_context_sync_state
       WHERE tenant_id = $1 AND site_id = $2`,
      [context.tenantId, context.siteId]
    )
    const revision = Number(state.rows[0]?.revision || 0)
    const sourceEtag = state.rows[0]?.source_etag as string | null | undefined
    const url = new URL('/api/v1/edge/batch-context', this.config.bffBaseUrl)
    url.searchParams.set('siteId', context.siteId)
    url.searchParams.set('sinceRevision', String(revision))
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), this.config.requestTimeoutSeconds * 1000)
    try {
      const headers: Record<string, string> = { 'x-request-id': `edge-batch-context-${Date.now()}` }
      if (this.config.cloudToken) headers.Authorization = `Bearer ${this.config.cloudToken}`
      if (sourceEtag) headers['If-None-Match'] = sourceEtag
      const response = await fetch(url, { headers, signal: controller.signal })
      if (response.status === 304) {
        await this.markBatchSyncSuccess(context, revision, sourceEtag || null, true)
        return
      }
      if (!response.ok) throw new Error(`Batch context response ${response.status}: ${await response.text().catch(() => '')}`)
      const payload = await response.json() as BatchContextPayload
      this.validateBatchContextPayload(context, payload)
      const etag = response.headers.get('etag')
      await this.applyBatchContextPayload(context, payload, etag)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      await this.pool.query(
        `INSERT INTO edge_batch_context_sync_state
           (tenant_id, site_id, last_error_at, last_error, consecutive_failures)
         VALUES ($1, $2, NOW(), $3, 1)
         ON CONFLICT (tenant_id, site_id) DO UPDATE SET
           last_error_at = NOW(), last_error = EXCLUDED.last_error,
           consecutive_failures = edge_batch_context_sync_state.consecutive_failures + 1`,
        [context.tenantId, context.siteId, message]
      )
      throw error
    } finally {
      clearTimeout(timeout)
    }
  }

  private async applyBatchContextPayload(context: EdgeContext, payload: BatchContextPayload, etag: string | null): Promise<void> {
    const client = await this.pool.connect()
    try {
      await client.query('BEGIN')
      const incomingBatchIds: string[] = []
      for (const item of payload.contexts) {
        incomingBatchIds.push(item.batchId)
        const lifecycle = item.status === 'active' ? 'active' : 'deactivated'
        const hash = this.hashPayload(item)
        const upsert = await client.query(
          `INSERT INTO edge_batch_context_cache
             (tenant_id, farm_id, barn_id, batch_id, revision, source_revision, lifecycle, species, breed_code, sex,
              start_date, end_date, model_policy_json, hash, source_etag, fetched_at, expires_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,NOW(),NOW()+($16 * INTERVAL '1 second'),NOW())
           ON CONFLICT (tenant_id, batch_id) DO UPDATE SET
             farm_id=EXCLUDED.farm_id, barn_id=EXCLUDED.barn_id, revision=EXCLUDED.revision,
             source_revision=EXCLUDED.source_revision,
             lifecycle=EXCLUDED.lifecycle, species=EXCLUDED.species, breed_code=EXCLUDED.breed_code,
             sex=EXCLUDED.sex, start_date=EXCLUDED.start_date, end_date=EXCLUDED.end_date,
             model_policy_json=EXCLUDED.model_policy_json, hash=EXCLUDED.hash,
             source_etag=EXCLUDED.source_etag, fetched_at=EXCLUDED.fetched_at,
             expires_at=EXCLUDED.expires_at, updated_at=NOW()
           WHERE edge_batch_context_cache.source_revision <= EXCLUDED.source_revision
           RETURNING batch_id`,
          [item.tenantId, item.farmId, item.barnId, item.batchId, item.revision, payload.nextRevision, lifecycle,
            item.species, item.breedCode, item.sex, item.startDate, item.endDate,
            item.modelPolicy || {}, hash, etag, this.config.batchContextTtlSeconds]
        )
        if (upsert.rowCount) {
          await client.query('DELETE FROM edge_batch_binding_cache WHERE tenant_id=$1 AND batch_id=$2', [item.tenantId, item.batchId])
          for (const binding of item.deviceBindings) {
            await client.query(
              `INSERT INTO edge_batch_binding_cache
                 (tenant_id,batch_id,binding_id,device_id,station_id,revision,active,updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,NOW())
               ON CONFLICT (tenant_id,binding_id) DO UPDATE SET
                 batch_id=EXCLUDED.batch_id, device_id=EXCLUDED.device_id,
                 station_id=EXCLUDED.station_id, revision=EXCLUDED.revision,
                 active=EXCLUDED.active, updated_at=NOW()
               WHERE edge_batch_binding_cache.revision <= EXCLUDED.revision`,
              [item.tenantId, item.batchId, binding.bindingId, binding.deviceId, binding.stationId, item.revision, lifecycle === 'active']
            )
          }
        }
      }
      if (payload.mode === 'snapshot' || payload.reset) {
        await client.query(
          `UPDATE edge_batch_context_cache SET lifecycle='superseded', updated_at=NOW()
           WHERE tenant_id=$1 AND farm_id=$2 AND barn_id=$3
             AND NOT (batch_id = ANY($4::text[]))`,
          [context.tenantId, context.farmId, context.barnId, incomingBatchIds]
        )
        await client.query(
          `UPDATE edge_batch_binding_cache b SET active=FALSE, updated_at=NOW()
           FROM edge_batch_context_cache c
           WHERE b.tenant_id=c.tenant_id AND b.batch_id=c.batch_id
             AND c.tenant_id=$1 AND c.farm_id=$2 AND c.barn_id=$3 AND c.lifecycle='superseded'`,
          [context.tenantId, context.farmId, context.barnId]
        )
      }
      await client.query(
        `INSERT INTO edge_batch_context_sync_state
           (tenant_id,site_id,revision,source_etag,last_success_at,last_error_at,last_error,consecutive_failures)
         VALUES ($1,$2,$3,$4,NOW(),NULL,NULL,0)
         ON CONFLICT (tenant_id,site_id) DO UPDATE SET
           revision=GREATEST(edge_batch_context_sync_state.revision,EXCLUDED.revision),
           source_etag=CASE
             WHEN edge_batch_context_sync_state.revision <= EXCLUDED.revision THEN EXCLUDED.source_etag
             ELSE edge_batch_context_sync_state.source_etag
           END,
           last_success_at=NOW(),last_error_at=NULL,last_error=NULL,consecutive_failures=0`,
        [context.tenantId, context.siteId, payload.nextRevision, etag]
      )
      await client.query('COMMIT')
    } catch (error) {
      await client.query('ROLLBACK')
      throw error
    } finally {
      client.release()
    }
  }

  private async markBatchSyncSuccess(
    context: EdgeContext,
    revision: number,
    etag: string | null,
    refreshCache: boolean
  ): Promise<void> {
    const client = await this.pool.connect()
    try {
      await client.query('BEGIN')
      if (refreshCache) {
        await client.query(
          `UPDATE edge_batch_context_cache
           SET fetched_at=NOW(), expires_at=NOW()+($4 * INTERVAL '1 second'), updated_at=NOW()
           WHERE tenant_id=$1 AND farm_id=$2 AND barn_id=$3 AND lifecycle='active'`,
          [context.tenantId, context.farmId, context.barnId, this.config.batchContextTtlSeconds]
        )
      }
      await client.query(
        `INSERT INTO edge_batch_context_sync_state
           (tenant_id,site_id,revision,source_etag,last_success_at,last_error_at,last_error,consecutive_failures)
         VALUES ($1,$2,$3,$4,NOW(),NULL,NULL,0)
         ON CONFLICT (tenant_id,site_id) DO UPDATE SET
           revision=GREATEST(edge_batch_context_sync_state.revision,EXCLUDED.revision),
           source_etag=CASE
             WHEN edge_batch_context_sync_state.revision <= EXCLUDED.revision THEN EXCLUDED.source_etag
             ELSE edge_batch_context_sync_state.source_etag
           END,
           last_success_at=NOW(),last_error_at=NULL,last_error=NULL,consecutive_failures=0`,
        [context.tenantId, context.siteId, revision, etag]
      )
      await client.query('COMMIT')
    } catch (error) {
      await client.query('ROLLBACK')
      throw error
    } finally {
      client.release()
    }
  }

  private validateBatchContextPayload(context: EdgeContext, payload: BatchContextPayload): void {
    if (!Number.isSafeInteger(payload.nextRevision) || payload.nextRevision < 0) {
      throw new Error('Invalid Batch context nextRevision')
    }
    if (payload.mode !== 'snapshot' && payload.mode !== 'delta') {
      throw new Error('Invalid Batch context mode')
    }
    const outOfScope = payload.contexts.find((item) =>
      item.tenantId !== context.tenantId ||
      item.farmId !== context.farmId ||
      item.barnId !== context.barnId
    )
    if (outOfScope) {
      throw new Error(`Out-of-scope Batch context ${outOfScope.batchId}`)
    }
  }

  private async syncModelSubscription(context: EdgeContext): Promise<void> {
    if (!context.siteId) return

    const url = new URL(
      `/api/v1/weighvision/model-subscriptions/sites/${encodeURIComponent(context.siteId)}/resolve`,
      this.config.bffBaseUrl
    )

    const controller = new AbortController()
    const timeout = setTimeout(
      () => controller.abort(),
      this.config.requestTimeoutSeconds * 1000
    )

    try {
      const headers: Record<string, string> = {
        'x-request-id': `edge-policy-sync-model-${Date.now()}`,
        'x-tenant-id': context.tenantId,
      }

      if (this.config.cloudToken) {
        headers.Authorization = `Bearer ${this.config.cloudToken}`
      }

      const response = await fetch(url.toString(), {
        method: 'GET',
        headers,
        signal: controller.signal,
      })

      if (!response.ok) {
        const body = await response.text().catch(() => '')
        throw new Error(`Model subscription response ${response.status}: ${body}`)
      }

      const payload = await response.json()
      const etag = response.headers.get('etag')
      const hash = this.hashPayload(payload)

      await this.pool.query(
        `
        INSERT INTO edge_model_subscription_cache
          (tenant_id, site_id, resolved_json, hash, fetched_at, source_etag, last_error, updated_at)
        VALUES ($1, $2, $3, $4, NOW(), $5, NULL, NOW())
        ON CONFLICT (tenant_id, site_id)
        DO UPDATE SET
          resolved_json = EXCLUDED.resolved_json,
          hash = EXCLUDED.hash,
          fetched_at = EXCLUDED.fetched_at,
          source_etag = EXCLUDED.source_etag,
          last_error = NULL,
          updated_at = NOW()
        `,
        [context.tenantId, context.siteId, payload, hash, etag]
      )

      logger.info('Model subscription synced', {
        tenantId: context.tenantId,
        siteId: context.siteId,
      })
    } finally {
      clearTimeout(timeout)
    }
  }

  private hashPayload(payload: unknown): string {
    const json = JSON.stringify(payload)
    return crypto.createHash('sha256').update(json).digest('hex')
  }

  private async updateSuccessState(): Promise<void> {
    await this.pool.query(
      `
      UPDATE edge_config_sync_state
      SET last_success_at = NOW(), last_error_at = NULL, last_error = NULL, consecutive_failures = 0
      WHERE id = 1
      `
    )
  }

  private async updateFailureState(message: string): Promise<void> {
    await this.pool.query(
      `
      UPDATE edge_config_sync_state
      SET last_error_at = NOW(), last_error = $1, consecutive_failures = consecutive_failures + 1
      WHERE id = 1
      `,
      [message]
    )
  }
}
