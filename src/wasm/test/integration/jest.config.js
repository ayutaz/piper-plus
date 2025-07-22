/** @type {import('jest').Config} */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'jsdom',
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx'],
  testMatch: ['**/*.test.ts', '**/*.test.js'],
  transform: {
    '^.+\\.tsx?$': ['ts-jest', {
      tsconfig: {
        esModuleInterop: true,
        allowSyntheticDefaultImports: true
      }
    }]
  },
  setupFilesAfterEnv: ['<rootDir>/setup.js'],
  testTimeout: 30000, // 30 seconds for integration tests
  collectCoverageFrom: [
    '../../**/*.{ts,js}',
    '!../../**/test/**',
    '!../../**/build/**',
    '!../../**/dist/**'
  ]
};