export type BatchContextProvenance = {
  source: 'edge-policy-sync' | 'controlled-override'
  resolvedAt: string
  reason: string | null
  context?: Record<string, unknown>
  actor?: string
  overrideReason?: string
}

export type BatchContextResolution = {
  batchId: string | null
  revision: number | null
  resolution: 'resolved' | 'unassigned' | 'override'
  reason: string | null
  provenance: BatchContextProvenance
}

export class BatchContextAmbiguousError extends Error {
  constructor(public readonly candidateBatchIds: string[]) {
    super('BATCH_CONTEXT_AMBIGUOUS')
  }
}

export type BatchContextLookupInput = {
  tenantId: string
  deviceId: string
  stationId: string
}

function unassigned(reason: string): BatchContextResolution {
  return {
    batchId: null,
    revision: null,
    resolution: 'unassigned',
    reason,
    provenance: { source: 'edge-policy-sync', resolvedAt: new Date().toISOString(), reason },
  }
}

export async function resolveBatchContext(input: BatchContextLookupInput): Promise<BatchContextResolution> {
  if (process.env.BATCH_CONTEXT_AUTO_BIND_ENABLED !== 'true') {
    return unassigned('AUTO_BIND_DISABLED')
  }

  const baseUrl = process.env.BATCH_CONTEXT_RESOLVER_URL || 'http://edge-policy-sync:3000/api/v1/edge-config'
  const timeoutMs = Number(process.env.BATCH_CONTEXT_RESOLVER_TIMEOUT_MS || 1500)
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  const stationId = input.stationId || '-'

  try {
    const url = `${baseUrl.replace(/\/$/, '')}/batch-context/${encodeURIComponent(input.tenantId)}/${encodeURIComponent(input.deviceId)}/${encodeURIComponent(stationId)}`
    const response = await fetch(url, { signal: controller.signal })
    const body = await response.json().catch(() => null) as { data?: Record<string, unknown> } | null
    const data = body?.data

    if (response.status === 409 || data?.outcome === 'ambiguous') {
      const ids = Array.isArray(data?.candidateBatchIds)
        ? data.candidateBatchIds.filter((value): value is string => typeof value === 'string')
        : []
      throw new BatchContextAmbiguousError(ids)
    }
    if (response.status === 404 || data?.outcome === 'unassigned') {
      return unassigned(typeof data?.reason === 'string' ? data.reason : 'NO_ACTIVE_BINDING')
    }
    if (!response.ok || !data) {
      return unassigned(`RESOLVER_HTTP_${response.status}`)
    }
    if (data.outcome === 'stale') {
      return unassigned(typeof data.reason === 'string' ? data.reason : 'BATCH_CONTEXT_STALE')
    }
    const context = data.context as Record<string, unknown> | undefined
    if (data.outcome !== 'resolved' || !context || typeof context.batchId !== 'string') {
      return unassigned('RESOLVER_INVALID_RESPONSE')
    }

    const revision = typeof context.revision === 'number' && Number.isInteger(context.revision)
      ? context.revision
      : null
    return {
      batchId: context.batchId,
      revision,
      resolution: 'resolved',
      reason: null,
      provenance: {
        source: 'edge-policy-sync',
        resolvedAt: new Date().toISOString(),
        reason: null,
        context,
      },
    }
  } catch (error) {
    if (error instanceof BatchContextAmbiguousError) throw error
    return unassigned(error instanceof Error && error.name === 'AbortError' ? 'RESOLVER_TIMEOUT' : 'RESOLVER_UNAVAILABLE')
  } finally {
    clearTimeout(timeout)
  }
}

export function createControlledOverride(
  batchId: string,
  actor: string,
  overrideReason: string
): BatchContextResolution {
  return {
    batchId,
    revision: null,
    resolution: 'override',
    reason: 'CONTROLLED_OVERRIDE',
    provenance: {
      source: 'controlled-override',
      resolvedAt: new Date().toISOString(),
      reason: 'CONTROLLED_OVERRIDE',
      actor,
      overrideReason,
    },
  }
}
