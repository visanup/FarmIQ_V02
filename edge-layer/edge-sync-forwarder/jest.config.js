module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  testMatch: ['**/tests/**/*.{spec,test}.ts', '**/src/**/*.{spec,test}.ts'],
  // Keep the normal validation command deterministic; CI coverage remains
  // available through `npm run test:coverage`.
  collectCoverage: false,
  coverageDirectory: 'coverage',
  coverageReporters: ['text', 'lcov'],
  coverageThreshold: {
    global: {
      branches: 70,
      functions: 70,
      lines: 70,
      statements: 70,
    },
  },
  testTimeout: 30000, // 30 seconds for integration tests
};
