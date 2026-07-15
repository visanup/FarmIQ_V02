const connectMock = jest.fn()

jest.mock('amqplib', () => ({
  connect: (...args: unknown[]) => connectMock(...args),
}))

describe('connectRabbitMQ', () => {
  beforeEach(() => {
    jest.resetModules()
    connectMock.mockReset()
  })

  it('retries until the broker becomes available', async () => {
    const channel = { close: jest.fn() }
    const connection = {
      createChannel: jest.fn().mockResolvedValue(channel),
      on: jest.fn(),
      close: jest.fn(),
    }

    connectMock
      .mockRejectedValueOnce(new Error('broker not ready'))
      .mockRejectedValueOnce(new Error('still starting'))
      .mockResolvedValue(connection)

    const rabbitmq = require('../../src/utils/rabbitmq') as typeof import('../../src/utils/rabbitmq')

    await rabbitmq.connectRabbitMQ(3, 1)

    expect(connectMock).toHaveBeenCalledTimes(3)
    expect(connection.createChannel).toHaveBeenCalledTimes(1)
    expect(rabbitmq.getChannel()).toBe(channel)
  })
})
