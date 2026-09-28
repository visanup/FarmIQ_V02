import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { Registry } from 'prom-client'
import { PolicySyncConfig } from '../../src/config'
import { SyncScheduler } from '../../src/services/syncScheduler'

const config: PolicySyncConfig = {
  appPort: 3000,
  databaseUrl: 'postgres://test',
  bffBaseUrl: 'http://bff',
  syncIntervalSeconds: 60,
  backoffCapSeconds: 600,
  requestTimeoutSeconds: 1,
  contexts: [],
  batchContextCacheEnabled: true,
  batchContextTtlSeconds: 300,
}

describe('SyncScheduler retry policy', () => {
  it('backs off exponentially after consecutive sync failures', async () => {
    let scheduledDelayMs = 0
    const originalSetTimeout = global.setTimeout
    const originalRandom = Math.random
    global.setTimeout = ((_: (...args: any[]) => void, delay?: number) => {
      scheduledDelayMs = Number(delay)
      return { unref: () => undefined } as any
    }) as typeof setTimeout
    Math.random = () => 0
    try {
      const service: any = {
        setResolutionObserver: () => undefined,
        syncAll: async () => ({ ok: false, error: 'cloud unavailable' }),
        getSyncState: async () => ({
          state: { consecutive_failures: 3, last_success_at: null },
          cacheEntries: 0,
          batchCacheEntries: 0,
          batchCacheOldestAgeSeconds: null,
          batchState: null,
        }),
      }
      const scheduler = new SyncScheduler(service, config, new Registry())
      await (scheduler as any).runOnce()
      assert.equal(scheduledDelayMs, 240_000)
    } finally {
      global.setTimeout = originalSetTimeout
      Math.random = originalRandom
    }
  })
})
