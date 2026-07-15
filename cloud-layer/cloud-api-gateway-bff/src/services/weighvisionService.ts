import { logger } from '../utils/logger'
import { getServiceBaseUrls } from './dashboardService'
import { callDownstreamJson, DownstreamOptions } from './dashboardService'

export interface WeighVisionServiceClient {
  getSessions(params: {
    tenantId: string
    farmId?: string
    barnId?: string
    batchId?: string
    stationId?: string
    status?: string
    from?: string
    to?: string
    limit?: number
    cursor?: string
    headers?: Record<string, string>
  }): Promise<any>

  getSessionById(tenantId: string, sessionId: string, headers?: Record<string, string>): Promise<any>

  getAnalytics(params: {
    tenantId: string
    farmId?: string
    barnId?: string
    batchId?: string
    startDate: string
    endDate: string
    aggregation?: 'daily' | 'weekly' | 'monthly'
    headers?: Record<string, string>
  }): Promise<any>

  getWeightAggregates(params: {
    tenantId: string
    farmId?: string
    barnId?: string
    batchId?: string
    start: string
    end: string
    headers?: Record<string, string>
  }): Promise<any>

  getDatasetContract(headers: Record<string, string>): Promise<any>
  bootstrapBaseline(headers: Record<string, string>): Promise<any>
  trainBaseline(body: unknown, headers: Record<string, string>): Promise<any>
  upsertModelSubscription(siteId: string, body: unknown, headers: Record<string, string>): Promise<any>
  getModelSubscription(siteId: string, headers: Record<string, string>): Promise<any>
  resolveModelSubscription(siteId: string, headers: Record<string, string>): Promise<any>
  ackModelSubscription(siteId: string, body: unknown, headers: Record<string, string>): Promise<any>
}

export function createWeighVisionServiceClient(): WeighVisionServiceClient {
  const {
    weighvisionReadModelBaseUrl,
    edgeWeighvisionSessionBaseUrl,
    mlModelServiceBaseUrl,
  } = getServiceBaseUrls()

  return {
    async getSessions(params) {
      const query: Record<string, string> = {
        tenantId: params.tenantId,
      }

      if (params.farmId) query.farmId = params.farmId
      if (params.barnId) query.barnId = params.barnId
      if (params.batchId) query.batchId = params.batchId
      if (params.stationId) query.stationId = params.stationId
      if (params.status) query.status = params.status
      if (params.from) query.from = params.from
      if (params.to) query.to = params.to
      if (params.limit) query.limit = String(params.limit)
      if (params.cursor) query.cursor = params.cursor

      const queryString = new URLSearchParams(query).toString()
      const url = `${weighvisionReadModelBaseUrl}/api/v1/weighvision/sessions?${queryString}`

      const options: DownstreamOptions = {
        method: 'GET',
        headers: params.headers || {},
      }

      const result = await callDownstreamJson(url, options)
      if (!result.ok || !result.data) {
        throw new Error(`Failed to fetch sessions: ${result.status}`)
      }
      return result.data
    },

    async getSessionById(tenantId, sessionId, headers) {
      const sessionUrl = `${weighvisionReadModelBaseUrl}/api/v1/weighvision/sessions/${sessionId}?tenantId=${tenantId}`
      const captureMetadataUrl = `${edgeWeighvisionSessionBaseUrl}/api/v1/weighvision/sessions/${sessionId}/metadata`

      const options: DownstreamOptions = {
        method: 'GET',
        headers: headers || {},
      }

      const [sessionResult, captureMetadataResult] = await Promise.all([
        callDownstreamJson<any>(sessionUrl, options),
        callDownstreamJson<any>(captureMetadataUrl, options),
      ])

      if (!sessionResult.ok || !sessionResult.data) {
        throw new Error(`Failed to fetch session: ${sessionResult.status}`)
      }

      const payload = sessionResult.data as Record<string, unknown>
      const captureMetadataItems = Array.isArray(captureMetadataResult.data?.items)
        ? captureMetadataResult.data.items
        : Array.isArray(captureMetadataResult.data)
          ? captureMetadataResult.data
          : []

      return captureMetadataItems.length > 0
        ? {
            ...payload,
            captureMetadata: captureMetadataItems,
          }
        : payload
    },

    async getAnalytics(params) {
      const query: Record<string, string> = {
        tenantId: params.tenantId,
        start_date: params.startDate,
        end_date: params.endDate,
      }

      if (params.farmId) query.farm_id = params.farmId
      if (params.barnId) query.barn_id = params.barnId
      if (params.batchId) query.batch_id = params.batchId
      if (params.aggregation) query.aggregation = params.aggregation

      const queryString = new URLSearchParams(query).toString()
      const url = `${weighvisionReadModelBaseUrl}/api/v1/weighvision/analytics?${queryString}`

      const options: DownstreamOptions = {
        method: 'GET',
        headers: params.headers || {},
      }

      const result = await callDownstreamJson(url, options)
      if (!result.ok || !result.data) {
        throw new Error(`Failed to fetch analytics: ${result.status}`)
      }
      return result.data
    },

    async getWeightAggregates(params) {
      const query: Record<string, string> = {
        tenant_id: params.tenantId,
        start: params.start,
        end: params.end,
      }

      if (params.farmId) query.farm_id = params.farmId
      if (params.barnId) query.barn_id = params.barnId
      if (params.batchId) query.batch_id = params.batchId

      const queryString = new URLSearchParams(query).toString()
      const url = `${weighvisionReadModelBaseUrl}/api/v1/weighvision/weight-aggregates?${queryString}`

      const options: DownstreamOptions = {
        method: 'GET',
        headers: params.headers || {},
      }

      const result = await callDownstreamJson(url, options)
      if (!result.ok || !result.data) {
        throw new Error(`Failed to fetch weight aggregates: ${result.status}`)
      }
      return result.data
    },

    async getDatasetContract(headers) {
      const result = await callDownstreamJson(
        `${mlModelServiceBaseUrl}/api/v1/ml/weighvision/dataset-contract`,
        { method: 'GET', headers }
      )
      if (!result.ok || !result.data) {
        throw new Error(`Failed to fetch dataset contract: ${result.status}`)
      }
      return result.data
    },

    async bootstrapBaseline(headers) {
      const result = await callDownstreamJson(
        `${mlModelServiceBaseUrl}/api/v1/ml/weighvision/bootstrap-baseline`,
        { method: 'POST', headers }
      )
      if (!result.ok || !result.data) {
        throw new Error(`Failed to bootstrap baseline: ${result.status}`)
      }
      return result.data
    },

    async trainBaseline(body, headers) {
      const result = await callDownstreamJson(
        `${mlModelServiceBaseUrl}/api/v1/ml/weighvision/train-baseline`,
        { method: 'POST', headers, body }
      )
      if (!result.ok || !result.data) {
        throw new Error(`Failed to train baseline: ${result.status}`)
      }
      return result.data
    },

    async upsertModelSubscription(siteId, body, headers) {
      const result = await callDownstreamJson(
        `${mlModelServiceBaseUrl}/api/v1/ml/weighvision/model-subscriptions/sites/${encodeURIComponent(siteId)}`,
        { method: 'PUT', headers, body }
      )
      if (!result.ok || !result.data) {
        throw new Error(`Failed to upsert model subscription: ${result.status}`)
      }
      return result.data
    },

    async getModelSubscription(siteId, headers) {
      const result = await callDownstreamJson(
        `${mlModelServiceBaseUrl}/api/v1/ml/weighvision/model-subscriptions/sites/${encodeURIComponent(siteId)}`,
        { method: 'GET', headers }
      )
      if (!result.ok || !result.data) {
        throw new Error(`Failed to fetch model subscription: ${result.status}`)
      }
      return result.data
    },

    async resolveModelSubscription(siteId, headers) {
      const result = await callDownstreamJson(
        `${mlModelServiceBaseUrl}/api/v1/ml/weighvision/model-subscriptions/sites/${encodeURIComponent(siteId)}/resolve`,
        { method: 'GET', headers }
      )
      if (!result.ok || !result.data) {
        throw new Error(`Failed to resolve model subscription: ${result.status}`)
      }
      return result.data
    },

    async ackModelSubscription(siteId, body, headers) {
      const result = await callDownstreamJson(
        `${mlModelServiceBaseUrl}/api/v1/ml/weighvision/model-subscriptions/sites/${encodeURIComponent(siteId)}/ack`,
        { method: 'POST', headers, body }
      )
      if (!result.ok || !result.data) {
        throw new Error(`Failed to acknowledge model subscription: ${result.status}`)
      }
      return result.data
    },
  }
}
