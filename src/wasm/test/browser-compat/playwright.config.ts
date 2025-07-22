import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for browser compatibility testing
 */
export default defineConfig({
  testDir: './tests',
  
  // Test timeout
  timeout: 60 * 1000, // 60 seconds per test
  
  // Expect timeout
  expect: {
    timeout: 10000
  },
  
  // Run tests in parallel
  fullyParallel: true,
  
  // Fail on CI if accidentally left test.only
  forbidOnly: !!process.env.CI,
  
  // Retry on CI
  retries: process.env.CI ? 2 : 0,
  
  // Number of workers
  workers: process.env.CI ? 1 : undefined,
  
  // Reporter
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'test-results/results.json' }],
    ['list']
  ],
  
  // Shared settings for all projects
  use: {
    // Base URL
    baseURL: 'http://localhost:8000',
    
    // Collect trace on failure
    trace: 'on-first-retry',
    
    // Screenshot on failure
    screenshot: 'only-on-failure',
    
    // Video on failure
    video: 'retain-on-failure',
    
    // Browser options
    launchOptions: {
      // Required for SharedArrayBuffer
      args: [
        '--enable-features=SharedArrayBuffer',
        '--disable-web-security',
      ]
    }
  },

  // Test projects for different browsers
  projects: [
    {
      name: 'chromium',
      use: { 
        ...devices['Desktop Chrome'],
        // Chrome-specific settings
        contextOptions: {
          // Required headers for SharedArrayBuffer
          extraHTTPHeaders: {
            'Cross-Origin-Embedder-Policy': 'require-corp',
            'Cross-Origin-Opener-Policy': 'same-origin'
          }
        }
      },
    },

    {
      name: 'firefox',
      use: { 
        ...devices['Desktop Firefox'],
        // Firefox-specific settings
        launchOptions: {
          firefoxUserPrefs: {
            // Enable SharedArrayBuffer
            'dom.postMessage.sharedArrayBuffer.bypassCOOP_COEP.insecure.enabled': true,
            // Enable WebAssembly SIMD
            'javascript.options.wasm_simd': true,
            // Enable WebGL
            'webgl.disabled': false,
            'webgl.enable-webgl2': true
          }
        }
      },
    },

    {
      name: 'webkit',
      use: { 
        ...devices['Desktop Safari'],
        // Safari-specific settings
        contextOptions: {
          // Safari requires user interaction for audio
          permissions: ['microphone']
        }
      },
    },

    // Additional browser variants for comprehensive testing
    {
      name: 'chrome-beta',
      use: { 
        ...devices['Desktop Chrome'],
        channel: 'chrome-beta'
      },
    },

    {
      name: 'edge',
      use: { 
        ...devices['Desktop Edge'],
      },
    },
  ],

  // Web server configuration
  webServer: {
    command: 'cd ../.. && python3 test/server.py',
    port: 8000,
    timeout: 120 * 1000,
    reuseExistingServer: !process.env.CI,
  },
});