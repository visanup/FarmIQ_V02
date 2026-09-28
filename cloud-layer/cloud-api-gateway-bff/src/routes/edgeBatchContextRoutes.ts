import express from 'express'
import { NextFunction, Request, Response } from 'express'
import { jwtAuthMiddleware } from '../middlewares/authMiddleware'
import { getEdgeBatchContextHandler } from '../controllers/edgeBatchContextController'
const router = express.Router()
router.use(jwtAuthMiddleware)
router.use((req: Request, res: Response, next: NextFunction): void => {
  const roles: string[] = res.locals.roles || []
  if (process.env.NODE_ENV === 'production') {
    if (!roles.some((role) => role === 'edge_service' || role === 'platform_admin')) {
      res.status(403).json({ error: { code: 'FORBIDDEN', message: 'Edge service credential is required', traceId: res.locals.traceId || 'unknown' } })
      return
    }
    if (roles.includes('edge_service') && !res.locals.siteId) {
      res.status(403).json({ error: { code: 'FORBIDDEN', message: 'Edge credential must contain site_id scope', traceId: res.locals.traceId || 'unknown' } })
      return
    }
  }
  next()
})
router.get('/batch-context', getEdgeBatchContextHandler)
export default router
