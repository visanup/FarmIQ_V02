import { Request, Response } from 'express'
import { tenantRegistryServiceClient } from '../services/tenantRegistryService'
import { createWeighVisionServiceClient } from '../services/weighvisionService'
import { logger } from '../utils/logger'

const weighvisionService = createWeighVisionServiceClient()

function forwardHeaders(req: Request, res: Response): Record<string, string> {
  const result: Record<string, string> = {}
  if (req.headers.authorization) result.authorization = req.headers.authorization
  if (res.locals.requestId) result['x-request-id'] = res.locals.requestId
  if (res.locals.traceId) result['x-trace-id'] = res.locals.traceId
  return result
}

function modelServiceHeaders(req: Request, res: Response, tenantId: string): Record<string, string> {
  return { ...forwardHeaders(req, res), authorization: `Bearer ${tenantId}` }
}

function error(res: Response, status: number, code: string, message: string): void {
  res.status(status).json({ error: { code, message, traceId: res.locals.traceId || 'unknown' } })
}

export async function getEdgeBatchContextHandler(req: Request, res: Response): Promise<void> {
  const tenantId = res.locals.tenantId as string | undefined
  const credentialSiteId = res.locals.siteId as string | undefined
  const siteId = req.query.siteId as string | undefined
  const sinceRevision = Number(req.query.sinceRevision || 0)

  if (!tenantId || !siteId) {
    error(res, 403, 'FORBIDDEN', 'Authenticated tenant scope and siteId are required')
    return
  }
  if (credentialSiteId && credentialSiteId !== siteId) {
    error(res, 403, 'FORBIDDEN', 'Site is outside credential scope')
    return
  }
  if (!Number.isSafeInteger(sinceRevision) || sinceRevision < 0) {
    error(res, 400, 'VALIDATION_ERROR', 'sinceRevision must be a non-negative safe integer')
    return
  }

  try {
    let policy: any
    try {
      policy = await weighvisionService.resolveModelSubscription(siteId, modelServiceHeaders(req, res, tenantId)) as any
    } catch (policyError) {
      if (!res.locals.farmId || !res.locals.barnId) throw policyError
      policy = {
        tenantId,
        siteId,
        farmId: res.locals.farmId,
        barnId: res.locals.barnId,
        channel: 'fallback',
        activePackage: null,
        fallbackPackage: null,
        activationPolicy: {},
        fallbackPolicy: { order: ['last_known_good', 'stub_mode'] },
        fallbackReason: 'NO_SITE_SUBSCRIPTION',
      }
    }
    if (policy.tenantId !== tenantId || (credentialSiteId && policy.siteId !== credentialSiteId)) {
      error(res, 403, 'FORBIDDEN', 'Site is outside tenant scope')
      return
    }
    const result = await tenantRegistryServiceClient.getBatchContext({
      query: {
        tenantId,
        farmId: policy.farmId || '',
        barnId: policy.barnId || '',
        sinceRevision: String(sinceRevision),
      },
      headers: forwardHeaders(req, res),
    })
    if (!result.ok || !result.data) {
      error(res, result.status || 502, result.status === 404 ? 'NOT_FOUND' : 'SERVICE_UNAVAILABLE', 'Unable to load batch context')
      return
    }

    const body = result.data as { nextRevision: number; contexts: Array<Record<string, unknown>>; mode: string; reset: boolean }
    const packageKey = policy.activePackage?.id || policy.activePackage?.version || 'fallback'
    const etag = `\"edge-batch-context-${tenantId}-${siteId}-${body.nextRevision}-${packageKey}\"`
    if (req.headers['if-none-match'] === etag) { res.status(304).end(); return }

    const modelPolicy = {
      siteId,
      channel: policy.channel,
      activePackage: policy.activePackage || null,
      fallbackPackage: policy.fallbackPackage || null,
      activationPolicy: policy.activationPolicy || {},
      fallbackPolicy: policy.fallbackPolicy || {},
      fallbackOnly: !policy.activePackage,
      fallbackReason: policy.activePackage ? null : (policy.fallbackReason || 'NO_ACTIVE_PACKAGE'),
    }
    res.setHeader('ETag', etag)
    res.json({
      ...body,
      contexts: body.contexts.map((context) => ({
        ...context,
        modelPolicy: {
          ...modelPolicy,
          selectionContext: {
            species: context.species ?? null,
            breedCode: context.breedCode ?? null,
            sex: context.sex ?? null,
          },
        },
      })),
      modelPolicy,
    })
    logger.info('Edge batch context resolved', {
      requestId: res.locals.requestId,
      traceId: res.locals.traceId,
      tenantId,
      siteId,
      sinceRevision,
      nextRevision: body.nextRevision,
      contextCount: body.contexts.length,
    })
  } catch (caught) {
    logger.error('Unable to resolve edge batch context', { tenantId, siteId, traceId: res.locals.traceId, error: caught })
    error(res, 502, 'SERVICE_UNAVAILABLE', 'Unable to resolve edge batch context')
  }
}
