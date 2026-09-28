import express from 'express'
import { jwtAuthMiddleware } from '../middlewares/authMiddleware'
import { bindDeviceToBatch, getBatchContext, removeDeviceBinding } from '../services/batchContextService'

const router = express.Router()
router.use(jwtAuthMiddleware)

router.get('/batch-context', async (req, res) => {
  const tenantId = res.locals.tenantId || req.query.tenantId
  if (typeof tenantId !== 'string') return res.status(400).json({ error: { code: 'VALIDATION_ERROR', message: 'tenantId is required', traceId: res.locals.traceId || 'unknown' } })
  const since = Number(req.query.sinceRevision || 0)
  const result = await getBatchContext(tenantId, req.query.farmId as string | undefined, req.query.barnId as string | undefined, Number.isSafeInteger(since) && since >= 0 ? since : 0)
  const farmScope = typeof req.query.farmId === 'string' ? req.query.farmId : 'all'
  const barnScope = typeof req.query.barnId === 'string' ? req.query.barnId : 'all'
  const etag = `\"batch-context-${tenantId}-${farmScope}-${barnScope}-${result.nextRevision}\"`
  if (req.headers['if-none-match'] === etag) return res.status(304).end()
  res.setHeader('ETag', etag)
  res.json(result)
})

router.post('/batches/:id/bindings', async (req, res) => {
  const tenantId = res.locals.tenantId || req.body.tenantId
  if (typeof tenantId !== 'string' || typeof req.body.deviceId !== 'string') return res.status(400).json({ error: { code: 'VALIDATION_ERROR', message: 'tenantId and deviceId are required', traceId: res.locals.traceId || 'unknown' } })
  const binding = await bindDeviceToBatch(tenantId, req.params.id, req.body.deviceId, req.body.stationId)
  if (!binding) return res.status(422).json({ error: { code: 'VALIDATION_ERROR', message: 'Batch, device, and station must share tenant/farm/barn scope', traceId: res.locals.traceId || 'unknown' } })
  res.status(201).json(binding)
})

router.delete('/batches/:id/bindings/:bindingId', async (req, res) => {
  const tenantId = res.locals.tenantId || req.query.tenantId
  if (typeof tenantId !== 'string') return res.status(400).json({ error: { code: 'VALIDATION_ERROR', message: 'tenantId is required', traceId: res.locals.traceId || 'unknown' } })
  if (!await removeDeviceBinding(tenantId, req.params.id, req.params.bindingId)) return res.status(404).json({ error: { code: 'NOT_FOUND', message: 'Binding not found', traceId: res.locals.traceId || 'unknown' } })
  res.status(204).end()
})

export default router
