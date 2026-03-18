import { describe, it } from 'node:test';
import assert from 'node:assert';

describe('Path Resolution Logic', () => {
    // Simulate the path resolution logic from openjtalk-piper-integration.js
    function resolvePathForGitHubPages(jsPath, isGitHubPages) {
        if (isGitHubPages) {
            // The actual condition from the code
            if (jsPath === './dist/openjtalk.js' || jsPath === 'dist/openjtalk.js') {
                return '../../dist/openjtalk.js';
            }
        } else {
            if (!jsPath.startsWith('./') && !jsPath.startsWith('../') && !jsPath.startsWith('/')) {
                return `./${jsPath}`;
            }
        }
        return jsPath;
    }
    
    it('should convert ./dist/openjtalk.js to ../../dist/openjtalk.js on GitHub Pages', () => {
        const result = resolvePathForGitHubPages('./dist/openjtalk.js', true);
        assert.strictEqual(result, '../../dist/openjtalk.js', 
            'Path ./dist/openjtalk.js should be converted to ../../dist/openjtalk.js');
    });
    
    it('should convert dist/openjtalk.js to ../../dist/openjtalk.js on GitHub Pages', () => {
        const result = resolvePathForGitHubPages('dist/openjtalk.js', true);
        assert.strictEqual(result, '../../dist/openjtalk.js',
            'Path dist/openjtalk.js should be converted to ../../dist/openjtalk.js');
    });
    
    it('should add ./ prefix for local development', () => {
        const result = resolvePathForGitHubPages('dist/openjtalk.js', false);
        assert.strictEqual(result, './dist/openjtalk.js',
            'Path dist/openjtalk.js should get ./ prefix for local development');
    });
    
    it('should not change already prefixed paths in local', () => {
        const result = resolvePathForGitHubPages('./dist/openjtalk.js', false);
        assert.strictEqual(result, './dist/openjtalk.js',
            'Already prefixed path should remain unchanged');
    });
});

describe('Import URL Resolution', () => {
    it('should calculate correct import URL for GitHub Pages', () => {
        // Simulate import.meta.url from test/js/openjtalk-piper-integration.js
        const importMetaUrl = 'https://ayutaz.github.io/piper-plus/test/js/openjtalk-piper-integration.js';
        const relativePath = '../../dist/openjtalk.js';
        
        const url = new URL(relativePath, importMetaUrl);
        assert.strictEqual(url.href, 'https://ayutaz.github.io/piper-plus/dist/openjtalk.js',
            'Should resolve to correct absolute URL');
    });
    
    it('should fail with wrong relative path', () => {
        const importMetaUrl = 'https://ayutaz.github.io/piper-plus/test/js/openjtalk-piper-integration.js';
        const wrongPath = './dist/openjtalk.js';
        
        const url = new URL(wrongPath, importMetaUrl);
        assert.strictEqual(url.href, 'https://ayutaz.github.io/piper-plus/test/js/dist/openjtalk.js',
            'Wrong path leads to incorrect URL');
    });
});

describe('Workflow Path Transformations', () => {
    it('should verify HTML path transformations', () => {
        const htmlPaths = [
            { from: '../../dist/openjtalk.js', to: './dist/openjtalk.js' },
            { from: '../../assets/dict', to: './assets/dict' },
            { from: '../../models/multilingual-test-medium.onnx', to: './models/multilingual-test-medium.onnx' }
        ];
        
        htmlPaths.forEach(({ from, to }) => {
            // Simulate sed command
            const result = from.replace(/^\.\.\/\.\.\//g, './');
            assert.strictEqual(result, to, `Path ${from} should transform to ${to}`);
        });
    });
});