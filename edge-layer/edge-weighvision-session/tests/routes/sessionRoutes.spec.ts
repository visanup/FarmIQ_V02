import express, { type Request, type Response } from 'express'
import type { Server } from 'http'

jest.mock('../../src/controllers/sessionController', () => {
  const respond =
    (route: string) => async (req: Request, res: Response): Promise<void> => {
      res.status(200).json({
        route,
        method: req.method,
        params: req.params,
        body: req.body,
      })
    }

  return {
    createSession: respond('createSession'),
    getSession: respond('getSession'),
    getSessionCaptureMetadata: respond('getSessionCaptureMetadata'),
    bindWeight: respond('bindWeight'),
    bindMedia: respond('bindMedia'),
    attach: respond('attach'),
    publishInferenceOutcome: respond('publishInferenceOutcome'),
    finalizeSession: respond('finalizeSession'),
    upsertCaptureMetadata: respond('upsertCaptureMetadata'),
    getHealth: respond('getHealth'),
    getReady: respond('getReady'),
  }
})

import { registerSessionRoutes } from '../../src/routes/sessionRoutes'

async function withServer<T>(
  run: (baseUrl: string) => Promise<T>
): Promise<T> {
  const app = express()
  app.use(express.json())
  registerSessionRoutes(app, '/api')

  const server = await new Promise<Server>((resolve) => {
    const listeningServer = app.listen(0, () => resolve(listeningServer))
  })

  const address = server.address()
  if (!address || typeof address === 'string') {
    server.close()
    throw new Error('failed to resolve test server address')
  }

  const baseUrl = `http://127.0.0.1:${address.port}`

  try {
    return await run(baseUrl)
  } finally {
    await new Promise<void>((resolve, reject) => {
      server.close((error) => {
        if (error) {
          reject(error)
          return
        }
        resolve()
      })
    })
  }
}

describe('registerSessionRoutes', () => {
  it('serves metadata GET without falling through to 404', async () => {
    await withServer(async (baseUrl) => {
      const response = await fetch(
        `${baseUrl}/api/v1/weighvision/sessions/session-001/metadata`
      )

      expect(response.status).toBe(200)
      await expect(response.json()).resolves.toMatchObject({
        route: 'getSessionCaptureMetadata',
        method: 'GET',
        params: { sessionId: 'session-001' },
      })
    })
  })

  it('serves metadata POST without falling through to 404', async () => {
    await withServer(async (baseUrl) => {
      const response = await fetch(
        `${baseUrl}/api/v1/weighvision/sessions/session-001/metadata`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ captureId: 'cap-001' }),
        }
      )

      expect(response.status).toBe(200)
      await expect(response.json()).resolves.toMatchObject({
        route: 'upsertCaptureMetadata',
        method: 'POST',
        params: { sessionId: 'session-001' },
        body: { captureId: 'cap-001' },
      })
    })
  })

  it('serves inference outcome POST without falling through to 404', async () => {
    await withServer(async (baseUrl) => {
      const response = await fetch(
        `${baseUrl}/api/v1/weighvision/sessions/session-001/inference-outcome`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            tenantId: 'tenant-001',
            eventId: 'evt-001',
            occurredAt: '2026-07-14T11:00:00.000Z',
            modelVersion: 'wv-shadow-1.0.0',
          }),
        }
      )

      expect(response.status).toBe(200)
      await expect(response.json()).resolves.toMatchObject({
        route: 'publishInferenceOutcome',
        method: 'POST',
        params: { sessionId: 'session-001' },
        body: {
          tenantId: 'tenant-001',
          eventId: 'evt-001',
          occurredAt: '2026-07-14T11:00:00.000Z',
          modelVersion: 'wv-shadow-1.0.0',
        },
      })
    })
  })
})
