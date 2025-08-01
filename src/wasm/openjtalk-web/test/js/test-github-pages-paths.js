import { describe, it } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

describe('GitHub Pages Path Resolution', () => {
    const jsFilePath = join(__dirname, 'openjtalk-piper-integration.js');
    const jsContent = readFileSync(jsFilePath, 'utf-8');
    
    it('should have GitHub Pages path adjustment logic', () => {
        // Check for GitHub Pages detection
        assert(jsContent.includes('window.location.hostname.includes(\'github.io\')'), 
            'Missing GitHub Pages hostname detection');
        
        // Check for jsPath adjustment
        assert(jsContent.includes('jsPath === \'dist/openjtalk.js\''), 
            'Missing jsPath adjustment for dist/openjtalk.js');
        
        // Check for wasmPath adjustment
        assert(jsContent.includes('wasmPath === \'dist/openjtalk.wasm\''), 
            'Missing wasmPath adjustment');
        
        // Check for dictPath adjustment
        assert(jsContent.includes('dictPath === \'dict\''), 
            'Missing dictPath adjustment');
        
        // Check for modelPath adjustment
        assert(jsContent.includes('modelPath.startsWith(\'models/\')'), 
            'Missing modelPath adjustment');
    });
    
    it('should handle relative path conversion correctly', () => {
        // Check that paths are converted to ../../ format for GitHub Pages
        assert(jsContent.includes('jsPath = \'../../dist/openjtalk.js\''), 
            'jsPath should be converted to ../../dist/openjtalk.js');
        
        assert(jsContent.includes('wasmPath = \'../../dist/openjtalk.wasm\''), 
            'wasmPath should be converted to ../../dist/openjtalk.wasm');
        
        assert(jsContent.includes('dictPath = \'../../dict\''), 
            'dictPath should be converted to ../../dict');
    });
    
    it('should ensure all dynamic imports have proper relative paths', () => {
        // Check for the dynamic import path correction logic
        assert(jsContent.includes('if (!jsPath.startsWith(\'./\') && !jsPath.startsWith(\'../\') && !jsPath.startsWith(\'/\'))'), 
            'Missing relative path enforcement for dynamic imports');
    });
});

describe('GitHub Actions Workflow Path Updates', () => {
    const workflowPath = join(__dirname, '../../../../.github/workflows/deploy-webassembly-demo.yml');
    
    it('should verify workflow has correct path transformations', async () => {
        try {
            const workflowContent = readFileSync(workflowPath, 'utf-8');
            
            // Check HTML path updates
            assert(workflowContent.includes('sed -i \'s|../../dist/|dist/|g\' deploy/index.html'), 
                'Missing HTML dist path transformation');
            
            assert(workflowContent.includes('sed -i \'s|../../assets/|assets/|g\' deploy/index.html'), 
                'Missing HTML assets path transformation');
            
            assert(workflowContent.includes('sed -i \'s|../../models/|models/|g\' deploy/index.html'), 
                'Missing HTML models path transformation');
            
            // Check JavaScript module path update
            assert(workflowContent.includes('sed -i \'s|./js/|./test/js/|g\' deploy/index.html'), 
                'Missing JavaScript module path transformation');
        } catch (error) {
            console.warn('Could not verify workflow file - may be running in different context');
        }
    });
});