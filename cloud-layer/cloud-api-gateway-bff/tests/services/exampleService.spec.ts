import {
  createExample,
  getExamplesFromDatabase,
} from '../../src/services/exampleService'
import { PrismaClient } from '@prisma/client'
import { logger } from '../../src/utils/logger'

jest.mock('@prisma/client', () => {
  const mPrismaClient = {
    example: { create: jest.fn(), findMany: jest.fn() },
  }
  return { PrismaClient: jest.fn(() => mPrismaClient) }
})

jest.mock('../../src/utils/logger', () => ({
  logger: { info: jest.fn(), error: jest.fn() },
}))

const prisma = new PrismaClient()
const exampleDelegate = (prisma as unknown as {
  example: { create: jest.Mock; findMany: jest.Mock }
}).example

describe('exampleService', () => {
  afterEach(() => {
    jest.clearAllMocks()
  })

  describe('createExample', () => {
    it('should create a user and return the result', async () => {
      const payload = { name: 'John Doe', email: 'john@example.com', age: 30 }
      const mockResult = { id: 1, ...payload }
      exampleDelegate.create.mockResolvedValue(mockResult)
      const result = await createExample(payload)
      expect(exampleDelegate.create).toHaveBeenCalledWith({ data: payload })
      expect(logger.info).toHaveBeenCalledWith('++++++ Creating user ++++++++')
      expect(result).toEqual(mockResult)
    })

    it('should log an error and throw an exception if creation fails', async () => {
      const payload = { name: 'John Doe', email: 'john@example.com', age: 30 }
      const mockError = new Error('Database Error')
      exampleDelegate.create.mockRejectedValue(mockError)
      await expect(createExample(payload)).rejects.toThrow(mockError)
      expect(logger.error).toHaveBeenCalledWith(
        'Error creating user:',
        mockError
      )
    })
  })

  describe('getExamplesFromDatabase', () => {
    it('should fetch all examples and return them', async () => {
      const mockExamples = [
        { id: 1, name: 'Example 1', email: 'example1@example.com', age: 20 },
      ]
      exampleDelegate.findMany.mockResolvedValue(mockExamples)
      const result = await getExamplesFromDatabase()
      expect(exampleDelegate.findMany).toHaveBeenCalled()
      expect(logger.info).toHaveBeenCalledWith(
        '++++++ Get example data ++++++++'
      )
      expect(result).toEqual(mockExamples)
    })

    it('should log an error and throw an exception if fetching fails', async () => {
      const mockError = new Error('Database Error')
      exampleDelegate.findMany.mockRejectedValue(mockError)
      await expect(getExamplesFromDatabase()).rejects.toThrow(mockError)
      expect(logger.error).toHaveBeenCalledWith(
        'Error fetching examples:',
        mockError
      )
    })
  })
})
