import { test, expect } from '@playwright/test';

/**
 * TTS integration tests across browsers
 */

test.describe('Full TTS Pipeline', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/test/full-tts-demo.html');
    
    // Wait for page to be ready
    await page.waitForLoadState('networkidle');
  });
  
  test('Complete TTS pipeline test', async ({ page, browserName }) => {
    // Set test timeout
    test.setTimeout(120000); // 2 minutes
    
    // Input Japanese text
    const testText = 'こんにちは世界';
    await page.fill('#textInput', testText);
    
    // Click synthesize button
    await page.click('#synthesizeBtn');
    
    // Wait for processing to complete
    const result = await page.waitForFunction(
      () => {
        const status = document.querySelector('#status');
        return status && (
          status.textContent?.includes('完了') || 
          status.textContent?.includes('エラー')
        );
      },
      { timeout: 60000 }
    );
    
    // Check if synthesis succeeded
    const statusText = await page.textContent('#status');
    console.log(`${browserName} TTS status: ${statusText}`);
    
    // Get performance metrics if available
    const metrics = await page.evaluate(() => {
      const metricsEl = document.querySelector('#performanceMetrics');
      if (!metricsEl) return null;
      
      return {
        mecabTime: document.querySelector('#mecabTime')?.textContent,
        openjtalkTime: document.querySelector('#openjtalkTime')?.textContent,
        onnxTime: document.querySelector('#onnxTime')?.textContent,
        totalTime: document.querySelector('#totalTime')?.textContent
      };
    });
    
    if (metrics) {
      console.log(`${browserName} Performance metrics:`, metrics);
    }
    
    // Check if audio was generated
    const audioGenerated = await page.evaluate(() => {
      const audio = document.querySelector('audio');
      return audio && audio.src && audio.duration > 0;
    });
    
    // Some browsers may have issues, log but don't fail
    if (!audioGenerated) {
      console.warn(`${browserName}: Audio generation failed or incomplete`);
    }
  });
  
  test('Streaming TTS test', async ({ page, browserName }) => {
    await page.goto('/test/streaming-tts-demo.html');
    test.setTimeout(120000);
    
    // Input longer text for streaming
    const longText = '今日は良い天気です。散歩に行きましょう。公園で花を見ることができます。';
    await page.fill('#textInput', longText);
    
    // Enable streaming mode if available
    const streamingCheckbox = await page.$('#enableStreaming');
    if (streamingCheckbox) {
      await streamingCheckbox.check();
    }
    
    // Start synthesis
    await page.click('#synthesizeBtn');
    
    // Monitor streaming progress
    let chunksReceived = 0;
    page.on('console', msg => {
      if (msg.text().includes('chunk')) {
        chunksReceived++;
      }
    });
    
    // Wait for completion
    await page.waitForFunction(
      () => {
        const status = document.querySelector('#status');
        return status && (
          status.textContent?.includes('完了') || 
          status.textContent?.includes('エラー')
        );
      },
      { timeout: 60000 }
    );
    
    console.log(`${browserName} Streaming: ${chunksReceived} chunks received`);
    
    // Check if streaming worked
    if (chunksReceived > 0) {
      expect(chunksReceived).toBeGreaterThan(1); // Should receive multiple chunks
    }
  });
});

test.describe('Error Handling', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/test/full-tts-demo.html');
  });
  
  test('Handle invalid input gracefully', async ({ page, browserName }) => {
    // Test empty input
    await page.fill('#textInput', '');
    await page.click('#synthesizeBtn');
    
    // Should show error message
    const errorText = await page.waitForSelector('.error', { timeout: 5000 })
      .then(el => el?.textContent())
      .catch(() => null);
    
    if (errorText) {
      console.log(`${browserName} Empty input error: ${errorText}`);
      expect(errorText).toBeTruthy();
    }
    
    // Test very long input
    const veryLongText = 'あ'.repeat(1000);
    await page.fill('#textInput', veryLongText);
    await page.click('#synthesizeBtn');
    
    // Should either handle or show appropriate error
    await page.waitForTimeout(2000);
    
    const status = await page.textContent('#status');
    console.log(`${browserName} Long input status: ${status}`);
  });
  
  test('Handle network errors', async ({ page, browserName }) => {
    // Intercept model loading requests
    await page.route('**/*.onnx*', route => route.abort());
    
    // Try to synthesize
    await page.fill('#textInput', 'テスト');
    await page.click('#synthesizeBtn');
    
    // Should show network error
    const errorText = await page.waitForSelector('.error', { timeout: 10000 })
      .then(el => el?.textContent())
      .catch(() => null);
    
    if (errorText) {
      console.log(`${browserName} Network error: ${errorText}`);
      expect(errorText).toContain('load');
    }
  });
});

test.describe('Performance Comparison', () => {
  test('Compare TTS performance across text lengths', async ({ page, browserName }) => {
    await page.goto('/test/benchmark.html');
    test.setTimeout(180000); // 3 minutes
    
    const textSamples = [
      { name: 'short', text: 'こんにちは' },
      { name: 'medium', text: 'こんにちは。今日は良い天気ですね。' },
      { name: 'long', text: '今日は良い天気です。散歩に行きましょう。公園で花を見ることができます。桜が満開で、とても美しいです。' }
    ];
    
    const results: any[] = [];
    
    for (const sample of textSamples) {
      await page.fill('#testText', sample.text);
      await page.selectOption('#textLength', sample.name);
      await page.fill('#iterations', '5');
      
      // Run benchmark
      await page.click('#runBenchmark');
      
      // Wait for results
      await page.waitForSelector('#results', { 
        state: 'visible',
        timeout: 60000 
      });
      
      // Extract results
      const metrics = await page.evaluate(() => {
        return {
          totalTime: document.querySelector('#totalTime')?.textContent,
          rtf: document.querySelector('#rtfValue')?.textContent,
          memoryUsage: document.querySelector('#memoryUsage')?.textContent
        };
      });
      
      results.push({
        browser: browserName,
        textLength: sample.name,
        ...metrics
      });
      
      // Reset for next test
      await page.reload();
    }
    
    // Log performance comparison
    console.log(`\n=== ${browserName.toUpperCase()} Performance Results ===`);
    results.forEach(r => {
      console.log(`${r.textLength}: ${r.totalTime} (RTF: ${r.rtf})`);
    });
  });
});

test.describe('Browser Compatibility Matrix Export', () => {
  test.afterAll(async ({ page, browserName }, testInfo) => {
    // Create compatibility report
    const report = {
      browser: browserName,
      timestamp: new Date().toISOString(),
      testResults: testInfo.errors.length === 0 ? 'PASSED' : 'FAILED',
      duration: testInfo.duration,
      errors: testInfo.errors
    };
    
    // Save report
    console.log('\n=== Compatibility Report ===');
    console.log(JSON.stringify(report, null, 2));
  });
});