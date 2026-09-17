import {
  Router,
  type Request,
  type Response,
  type RequestHandler,
} from 'express'
import * as sessionController from '../controllers/sessionController'

type AsyncHandler = (req: Request, res: Response) => Promise<unknown>
type RouteRegistrar = {
  get: (path: string, ...handlers: RequestHandler[]) => unknown
  post: (path: string, ...handlers: RequestHandler[]) => unknown
}

const wrapAsync = (fn: AsyncHandler): RequestHandler => {
  return (req, res, next) => {
    void fn(req, res).catch(next)
  }
}

function normalizeBasePath(basePath?: string): string {
  if (!basePath) {
    return ''
  }

  if (basePath === '/') {
    return ''
  }

  return basePath.endsWith('/') ? basePath.slice(0, -1) : basePath
}

export function registerSessionRoutes(
  target: RouteRegistrar,
  basePath?: string
): void {
  const prefix = normalizeBasePath(basePath)
  const sessionBasePath = `${prefix}/v1/weighvision/sessions`

  // Health/Ready
  target.get(`${prefix}/health`, wrapAsync(sessionController.getHealth))
  target.get(`${prefix}/ready`, wrapAsync(sessionController.getReady))

  // Sessions
  target.post(
    sessionBasePath,
    wrapAsync(sessionController.createSession)
  )

  // Register metadata endpoints before the generic session route so the
  // runtime path matcher cannot shadow the more specific branch.
  target.get(
    `${sessionBasePath}/:sessionId/metadata`,
    wrapAsync(sessionController.getSessionCaptureMetadata)
  )
  target.post(
    `${sessionBasePath}/:sessionId/metadata`,
    wrapAsync(sessionController.upsertCaptureMetadata)
  )

  target.get(
    `${sessionBasePath}/:sessionId`,
    wrapAsync(sessionController.getSession)
  )
  target.post(
    `${sessionBasePath}/:sessionId/bind-weight`,
    wrapAsync(sessionController.bindWeight)
  )
  target.post(
    `${sessionBasePath}/:sessionId/bind-media`,
    wrapAsync(sessionController.bindMedia)
  )
  target.post(
    `${sessionBasePath}/:sessionId/attach`,
    wrapAsync(sessionController.attach)
  )
  target.post(
    `${sessionBasePath}/:sessionId/inference-outcome`,
    wrapAsync(sessionController.publishInferenceOutcome)
  )
  target.post(
    `${sessionBasePath}/:sessionId/finalize`,
    wrapAsync(sessionController.finalizeSession)
  )
}

const router = Router()
registerSessionRoutes(router)

export default router
