import express from 'express'
import {
  ackModelSubscriptionHandler,
  bootstrapBaselineHandler,
  getDatasetContractHandler,
  getModelSubscriptionHandler,
  getSessionsHandler,
  getSessionByIdHandler,
  getAnalyticsHandler,
  resolveModelSubscriptionHandler,
  trainBaselineHandler,
  upsertModelSubscriptionHandler,
  getWeightAggregatesHandler,
  previewHistoricalAssociationHandler,
  confirmHistoricalAssociationHandler,
  enqueueHistoricalReprocessHandler,
  cancelHistoricalReprocessHandler,
} from '../controllers/weighvisionController'
import { jwtAuthMiddleware } from '../middlewares/authMiddleware'

const router = express.Router()

// Apply JWT auth middleware
router.use(jwtAuthMiddleware)

/**
 * GET /api/v1/weighvision/sessions
 * Proxy to cloud-weighvision-readmodel
 */
router.get('/sessions', getSessionsHandler)

/**
 * GET /api/v1/weighvision/sessions/:sessionId
 * Proxy to cloud-weighvision-readmodel
 */
router.get('/sessions/:sessionId', getSessionByIdHandler)

/**
 * GET /api/v1/weighvision/analytics
 * Proxy to cloud-weighvision-readmodel
 */
router.get('/analytics', getAnalyticsHandler)

/**
 * GET /api/v1/weighvision/weight-aggregates
 * Proxy to cloud-weighvision-readmodel
 */
router.get('/weight-aggregates', getWeightAggregatesHandler)
router.post('/historical-associations/preview', previewHistoricalAssociationHandler)
router.post('/historical-associations/confirm', confirmHistoricalAssociationHandler)
router.post('/historical-reprocess', enqueueHistoricalReprocessHandler)
router.delete('/historical-reprocess/:jobId', cancelHistoricalReprocessHandler)

router.get('/dataset-contract', getDatasetContractHandler)
router.post('/bootstrap-baseline', bootstrapBaselineHandler)
router.post('/train-baseline', trainBaselineHandler)
router.put('/model-subscriptions/sites/:siteId', upsertModelSubscriptionHandler)
router.get('/model-subscriptions/sites/:siteId', getModelSubscriptionHandler)
router.get('/model-subscriptions/sites/:siteId/resolve', resolveModelSubscriptionHandler)
router.post('/model-subscriptions/sites/:siteId/ack', ackModelSubscriptionHandler)

export default router
