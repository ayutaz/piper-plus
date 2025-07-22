/** @type {import('jest').Config} */
module.exports = {
  testEnvironment: 'jsdom',
  moduleFileExtensions: ['js', 'json'],
  testMatch: ['**/*.test.js'],
  setupFilesAfterEnv: ['<rootDir>/setup.js'],
  testTimeout: 10000,
  collectCoverageFrom: [
    '../**/*.js',
    '!../build/**',
    '!../CMakeFiles/**'
  ]
};