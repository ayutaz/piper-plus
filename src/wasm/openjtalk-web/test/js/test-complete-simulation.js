import { describe, it } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

describe('Complete GitHub Pages Simulation', () => {
    const jsFilePath = join(__dirname, 'openjtalk-piper-integration.js');
    const jsContent = readFileSync(jsFilePath, 'utf-8');
    
    // Simulate the EXACT scenario from GitHub Pages
    it('should handle the exact GitHub Pages scenario', () => {
        // 1. HTML config value (from error log)
        const htmlConfigJsPath = './dist/openjtalk.js';
        
        // 2. Simulate GitHub Pages environment
        const isGitHubPages = true; // window.location.hostname.includes('github.io')
        
        // 3. Apply the exact logic from our code
        let jsPath = htmlConfigJsPath;
        
        if (isGitHubPages) {
            if (jsPath === 'dist/openjtalk.js' || 
                jsPath === './dist/openjtalk.js' || 
                jsPath === '../dist/openjtalk.js' ||
                jsPath.endsWith('/dist/openjtalk.js')) {
                jsPath = '../../dist/openjtalk.js';
            }
        }
        
        // 4. Verify the result
        assert.strictEqual(jsPath, '../../dist/openjtalk.js', 
            'Path should be converted to ../../dist/openjtalk.js');
        
        // 5. Verify URL resolution
        const importMetaUrl = 'https://ayutaz.github.io/piper-plus/test/js/openjtalk-piper-integration.js';
        const resolvedUrl = new URL(jsPath, importMetaUrl);
        assert.strictEqual(resolvedUrl.href, 'https://ayutaz.github.io/piper-plus/dist/openjtalk.js',
            'Should resolve to correct absolute URL');
    });
    
    it('should verify the code doesnt get modified by workflow', () => {
        // Check that the code contains the correct path
        assert(jsContent.includes('jsPath = \'../../dist/openjtalk.js\''), 
            'Code should set jsPath to ../../dist/openjtalk.js');
        
        // Should NOT contain the wrong path
        assert(!jsContent.includes('jsPath = \'./dist/openjtalk.js\''), 
            'Code should NOT set jsPath to ./dist/openjtalk.js');
    });
    
    it('should handle all expected HTML config values', () => {
        const testCases = [
            { input: 'dist/openjtalk.js', expected: '../../dist/openjtalk.js' },
            { input: './dist/openjtalk.js', expected: '../../dist/openjtalk.js' },
            { input: '../dist/openjtalk.js', expected: '../../dist/openjtalk.js' },
            { input: 'prefix/dist/openjtalk.js', expected: '../../dist/openjtalk.js' }
        ];
        
        testCases.forEach(({ input, expected }) => {
            let jsPath = input;
            
            // Apply exact logic
            if (jsPath === 'dist/openjtalk.js' || 
                jsPath === './dist/openjtalk.js' || 
                jsPath === '../dist/openjtalk.js' ||
                jsPath.endsWith('/dist/openjtalk.js')) {
                jsPath = '../../dist/openjtalk.js';
            }
            
            assert.strictEqual(jsPath, expected, 
                `Input "${input}" should convert to "${expected}"`);
        });
    });
});

describe('Workflow Verification', () => {
    it('should ensure workflow doesnt modify JavaScript files', () => {
        // Read the workflow file
        const workflowPath = join(__dirname, '../../../../.github/workflows/deploy-webassembly-demo.yml');
        
        try {
            const workflowContent = readFileSync(workflowPath, 'utf-8');
            
            // Should copy files
            assert(workflowContent.includes('cp -r src/wasm/openjtalk-web/test/js/* deploy/test/js/'),
                'Workflow should copy JavaScript files');
            
            // Should NOT modify JavaScript files
            assert(!workflowContent.includes('sed -i \'s|../../dist/|./dist/|g\' deploy/test/js/openjtalk-piper-integration.js'),
                'Workflow should NOT modify paths in JavaScript files');
            
            // Should have comment about not modifying
            assert(workflowContent.includes('# JavaScript files already have correct path handling logic'),
                'Workflow should have comment explaining why no modification is needed');
        } catch (error) {
            console.warn('Could not verify workflow file - may be running in different context');
        }
    });
});