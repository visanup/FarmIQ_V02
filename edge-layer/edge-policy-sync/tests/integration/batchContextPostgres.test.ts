import assert from 'node:assert/strict'
import { createServer, Server } from 'node:http'
import { AddressInfo } from 'node:net'
import { after, before, describe, it } from 'node:test'
import { Pool } from 'pg'
import { PolicySyncConfig } from '../../src/config'
import { PolicySyncService } from '../../src/services/policySyncService'

const enabled = process.env.RUN_DB_INTEGRATION === 'true'
const tenantId = 'bces-003-integration'
const context = { tenantId, farmId: 'farm-test', barnId: 'barn-test', siteId: 'site-test' }

describe('Batch context sync with PostgreSQL and mock BFF', { skip: !enabled }, () => {
  const pool = new Pool({ connectionString: process.env.DATABASE_URL })
  let server: Server
  let service: PolicySyncService
  let requests = 0

  before(async () => {
    await cleanup()
    server = createServer((req, res) => {
      requests += 1
      if (req.headers['if-none-match'] === '"batch-10"') {
        res.statusCode = 304
        return res.end()
      }
      res.statusCode = 200
      res.setHeader('content-type', 'application/json')
      res.setHeader('etag', '"batch-10"')
      res.end(JSON.stringify({
        mode: 'snapshot', reset: false, nextRevision: 10,
        contexts: [{
          batchId: 'batch-test', tenantId, farmId: context.farmId, barnId: context.barnId,
          revision: 3, status: 'active', species: 'chicken', breedCode: 'ROSS-308', sex: 'female',
          startDate: '2026-09-01T00:00:00.000Z', endDate: null,
          deviceBindings: [{ bindingId: 'binding-test', deviceId: 'device-test', stationId: 'station-test' }],
          modelPolicy: { packageId: 'weight-v1', version: '1.0.0' },
        }],
      }))
    })
    await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
    const address = server.address() as AddressInfo
    const config: PolicySyncConfig = {
      appPort: 3000,
      databaseUrl: process.env.DATABASE_URL || '',
      bffBaseUrl: `http://127.0.0.1:${address.port}`,
      syncIntervalSeconds: 60,
      backoffCapSeconds: 600,
      requestTimeoutSeconds: 2,
      contexts: [context],
      batchContextCacheEnabled: true,
      batchContextTtlSeconds: 300,
    }
    service = new PolicySyncService(pool, config)
  })

  after(async () => {
    await cleanup()
    await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve()))
    await pool.end()
  })

  async function cleanup() {
    await pool.query('DELETE FROM edge_batch_binding_cache WHERE tenant_id=$1', [tenantId])
    await pool.query('DELETE FROM edge_batch_context_cache WHERE tenant_id=$1', [tenantId])
    await pool.query('DELETE FROM edge_batch_context_sync_state WHERE tenant_id=$1', [tenantId])
  }

  it('persists snapshot, handles duplicate 304, rejects old revision, and survives service recreation', async () => {
    await (service as any).syncBatchContext(context)
    await (service as any).syncBatchContext(context)

    const counts = await pool.query(
      `SELECT
         (SELECT COUNT(*)::int FROM edge_batch_context_cache WHERE tenant_id=$1) AS contexts,
         (SELECT COUNT(*)::int FROM edge_batch_binding_cache WHERE tenant_id=$1) AS bindings,
         (SELECT revision::int FROM edge_batch_context_sync_state WHERE tenant_id=$1 AND site_id=$2) AS revision`,
      [tenantId, context.siteId]
    )
    assert.deepEqual(counts.rows[0], { contexts: 1, bindings: 1, revision: 10 })
    assert.equal(requests, 2)

    await (service as any).applyBatchContextPayload(context, {
      mode: 'delta', reset: false, nextRevision: 9,
      contexts: [{
        batchId: 'batch-test', tenantId, farmId: context.farmId, barnId: context.barnId,
        revision: 2, status: 'active', species: 'chicken', breedCode: 'OLD-VALUE', sex: 'female',
        startDate: null, endDate: null,
        deviceBindings: [{ bindingId: 'binding-old', deviceId: 'device-old', stationId: 'station-test' }],
      }],
    }, '"batch-9"')

    const persisted = await pool.query(
      'SELECT breed_code, source_revision::int AS source_revision FROM edge_batch_context_cache WHERE tenant_id=$1',
      [tenantId]
    )
    assert.deepEqual(persisted.rows[0], { breed_code: 'ROSS-308', source_revision: 10 })

    const recreated = new PolicySyncService(pool, (service as any).config)
    const resolved = await recreated.resolveBatchContext(tenantId, 'device-test', 'station-test')
    assert.equal(resolved.outcome, 'resolved')
    assert.equal((resolved as any).context.batchId, 'batch-test')
  })
})
