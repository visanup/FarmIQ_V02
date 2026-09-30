import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { PolicySyncConfig } from '../../src/config'
import { PolicySyncService } from '../../src/services/policySyncService'

const config: PolicySyncConfig = {
  appPort: 3000, databaseUrl: 'postgres://test', bffBaseUrl: 'http://bff',
  syncIntervalSeconds: 60, backoffCapSeconds: 600, requestTimeoutSeconds: 1,
  contexts: [], batchContextCacheEnabled: true, batchContextTtlSeconds: 300,
}

describe('PolicySyncService Batch context cache', () => {
  it('reports unassigned when no active binding exists', async () => {
    const pool: any = { query: async () => ({ rows: [] }) }
    const service = new PolicySyncService(pool, config)
    assert.deepEqual(await service.resolveBatchContext('t-1', 'd-1', 's-1'), {
      outcome: 'unassigned', reason: 'NO_ACTIVE_BINDING',
    })
  })

  it('reports ambiguity when more than one active Batch matches', async () => {
    const pool: any = { query: async () => ({ rows: [{ batch_id: 'batch-1' }, { batch_id: 'batch-2' }] }) }
    const service = new PolicySyncService(pool, config)
    assert.deepEqual(await service.resolveBatchContext('t-1', 'd-1', 's-1'), {
      outcome: 'ambiguous', reason: 'MULTIPLE_ACTIVE_BATCHES', candidateBatchIds: ['batch-1', 'batch-2'],
    })
  })

  it('continues offline lookup but marks an expired cache as stale', async () => {
    const pool: any = { query: async () => ({ rows: [{
      tenant_id: 't-1', farm_id: 'f-1', barn_id: 'b-1', batch_id: 'batch-1',
      device_id: 'd-1', station_id: 's-1', revision: 3, species: 'chicken',
      breed_code: 'ROSS-308', sex: 'female', start_date: new Date(), end_date: null,
      model_policy_json: {}, fetched_at: new Date(Date.now() - 600_000),
      expires_at: new Date(Date.now() - 1_000),
    }] }) }
    const result = await new PolicySyncService(pool, config).resolveBatchContext('t-1', 'd-1', 's-1')
    assert.equal(result.outcome, 'stale')
    assert.equal(result.reason, 'CACHE_EXPIRED')
    assert.equal((result as any).context.batchId, 'batch-1')
  })

  it('does not replace bindings when an older source revision loses the upsert condition', async () => {
    const calls: Array<[string, unknown[] | undefined]> = []
    const query = async (sql: string, params?: unknown[]) => {
      calls.push([sql, params])
      return sql.includes('INSERT INTO edge_batch_context_cache')
        ? { rowCount: 0, rows: [] }
        : { rowCount: 1, rows: [] }
    }
    const pool: any = { connect: async () => ({ query, release: () => undefined }) }
    const service = new PolicySyncService(pool, config)
    await (service as any).applyBatchContextPayload(
      { tenantId: 't-1', farmId: 'f-1', barnId: 'b-1', siteId: 'site-1' },
      { mode: 'delta', reset: false, nextRevision: 4, contexts: [{
        batchId: 'batch-1', tenantId: 't-1', farmId: 'f-1', barnId: 'b-1', revision: 2,
        status: 'active', species: 'chicken', breedCode: null, sex: null,
        startDate: null, endDate: null,
        deviceBindings: [{ bindingId: 'bind-1', deviceId: 'd-1', stationId: null }],
      }] },
      'etag-old',
    )
    const upsert = calls.find(([sql]) => sql.includes('INSERT INTO edge_batch_context_cache'))
    assert.match(upsert?.[0] || '', /source_revision <= EXCLUDED\.source_revision/)
    assert.equal(upsert?.[1]?.[5], 4)
    assert.equal(calls.some(([sql]) => sql.includes('DELETE FROM edge_batch_binding_cache')), false)
  })

  it('treats reset delta as a full snapshot', async () => {
    const calls: string[] = []
    const query = async (sql: string) => {
      calls.push(sql)
      return sql.includes('INSERT INTO edge_batch_context_cache')
        ? { rowCount: 1, rows: [{ batch_id: 'batch-1' }] }
        : { rowCount: 1, rows: [] }
    }
    const pool: any = { connect: async () => ({ query, release: () => undefined }) }
    const service = new PolicySyncService(pool, config)
    await (service as any).applyBatchContextPayload(
      { tenantId: 't-1', farmId: 'f-1', barnId: 'b-1', siteId: 'site-1' },
      { mode: 'delta', reset: true, nextRevision: 5, contexts: [] },
      'etag-reset',
    )
    assert.equal(calls.some((sql) => sql.includes("lifecycle='superseded'")), true)
    assert.equal(calls.some((sql) => sql.includes('SET active=FALSE')), true)
  })

  it('refreshes cache expiry when the BFF returns 304', async () => {
    const calls: string[] = []
    const client = {
      query: async (sql: string) => { calls.push(sql); return { rowCount: 1, rows: [] } },
      release: () => undefined,
    }
    const pool: any = {
      query: async () => ({ rows: [{ revision: 7, source_etag: 'etag-7' }] }),
      connect: async () => client,
    }
    const previousFetch = global.fetch
    global.fetch = async () => new Response(null, { status: 304 })
    try {
      const service = new PolicySyncService(pool, config)
      await (service as any).syncBatchContext({ tenantId: 't-1', farmId: 'f-1', barnId: 'b-1', siteId: 'site-1' })
      assert.equal(calls.some((sql) => sql.includes('expires_at=NOW()')), true)
      assert.equal(calls.some((sql) => sql.includes('edge_batch_context_sync_state')), true)
    } finally {
      global.fetch = previousFetch
    }
  })

  it('refreshes cache expiry when a successful 200 delta has no changes', async () => {
    const calls: string[] = []
    const client = {
      query: async (sql: string) => { calls.push(sql); return { rowCount: 1, rows: [] } },
      release: () => undefined,
    }
    const pool: any = {
      query: async () => ({ rows: [{ revision: 7, source_etag: 'etag-7' }] }),
      connect: async () => client,
    }
    const previousFetch = global.fetch
    global.fetch = async () => new Response(JSON.stringify({
      mode: 'delta', reset: false, nextRevision: 7, contexts: [],
    }), { status: 200, headers: { etag: 'etag-7' } })
    try {
      const service = new PolicySyncService(pool, config)
      await (service as any).syncBatchContext({ tenantId: 't-1', farmId: 'f-1', barnId: 'b-1', siteId: 'site-1' })
      assert.equal(calls.filter((sql) => sql.includes('expires_at=NOW()')).length, 1)
    } finally {
      global.fetch = previousFetch
    }
  })

  it('rejects a Batch context outside the configured tenant/farm/barn scope', () => {
    const service = new PolicySyncService({} as any, config)
    assert.throws(
      () => (service as any).validateBatchContextPayload(
        { tenantId: 't-1', farmId: 'f-1', barnId: 'b-1', siteId: 'site-1' },
        { mode: 'delta', reset: false, nextRevision: 1, contexts: [{
          batchId: 'batch-x', tenantId: 'other-tenant', farmId: 'f-1', barnId: 'b-1',
        }] },
      ),
      /Out-of-scope Batch context/,
    )
  })

  it('records a sync failure when the BFF request times out', async () => {
    const calls: Array<[string, unknown[] | undefined]> = []
    const pool: any = {
      query: async (sql: string, params?: unknown[]) => {
        calls.push([sql, params])
        if (sql.includes('SELECT revision')) return { rows: [{ revision: 4, source_etag: 'etag-4' }] }
        return { rows: [], rowCount: 1 }
      },
    }
    const previousFetch = global.fetch
    global.fetch = async (_input, init) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new Error('request aborted')))
    })
    try {
      const service = new PolicySyncService(pool, { ...config, requestTimeoutSeconds: 0.01 })
      await assert.rejects(
        () => (service as any).syncBatchContext({ tenantId: 't-1', farmId: 'f-1', barnId: 'b-1', siteId: 'site-1' }),
        /request aborted/,
      )
      const failure = calls.find(([sql]) => sql.includes('consecutive_failures = edge_batch_context_sync_state.consecutive_failures + 1'))
      assert.equal(failure?.[1]?.[0], 't-1')
      assert.equal(failure?.[1]?.[1], 'site-1')
    } finally {
      global.fetch = previousFetch
    }
  })
})
