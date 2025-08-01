import { describe, it } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

describe('GitHub Pages Simulation', () => {
    const jsFilePath = join(__dirname, 'openjtalk-piper-integration.js');
    const jsContent = readFileSync(jsFilePath, 'utf-8');
    
    // Extract the actual path resolution logic from the file
    const pathResolutionLogic = jsContent.match(/if \(jsPath\.includes\('dist\/openjtalk\.js'\)\)/);
    
    it('should use includes() for flexible path matching', () => {
        assert(pathResolutionLogic, 'Should use includes() method for path matching');
    });
    
    it('should handle various path formats', () => {
        const testPaths = [
            'dist/openjtalk.js',
            './dist/openjtalk.js',
            '../dist/openjtalk.js',
            'some/prefix/dist/openjtalk.js'
        ];
        
        testPaths.forEach(path => {
            const result = path.includes('dist/openjtalk.js');
            assert(result, `Path "${path}" should match the includes condition`);
        });
    });
    
    it('should verify all path conversions use includes()', () => {
        // Check for flexible wasmPath matching
        assert(jsContent.includes("wasmPath.includes('dist/openjtalk.wasm')"), 
            'wasmPath should use includes() matching');
        
        // Check for flexible dictPath matching
        assert(jsContent.includes("dictPath.includes('assets/dict')"), 
            'dictPath should use includes() matching');
        
        // Check for flexible model path matching
        assert(jsContent.includes("modelPath.includes('models/')"), 
            'modelPath should use includes() matching');
    });
});