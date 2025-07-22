/** @type {import('jest').Config} */
module.exports = {
  testEnvironment: 'jsdom',
  moduleFileExtensions: ['js', 'json'],
  testMatch: ['**/*.test.js'],
  transform: {},
  moduleNameMapper: {
    '\\.(wasm)$': '<rootDir>/__mocks__/wasmMock.js'
  },
  setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
  testTimeout: 10000
};