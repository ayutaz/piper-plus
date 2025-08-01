import { describe, it } from 'node:test';
import assert from 'node:assert';

describe('Edge Cases and Potential Issues', () => {
    // Simulate the actual import.meta.url from GitHub Pages
    const githubPagesImportMetaUrl = 'https://ayutaz.github.io/piper-plus/test/js/openjtalk-piper-integration.js';
    
    it('should handle the exact path from GitHub Pages deployment', () => {
        // The actual path we see in the error logs
        const actualPath = 'dist/openjtalk.js';  // No ./ prefix
        
        // Apply the includes() logic
        const shouldConvert = actualPath.includes('dist/openjtalk.js');
        assert(shouldConvert, 'Path should match includes() condition');
        
        // After conversion
        const convertedPath = '../../dist/openjtalk.js';
        
        // Test URL resolution
        const resolvedUrl = new URL(convertedPath, githubPagesImportMetaUrl);
        assert.strictEqual(
            resolvedUrl.href, 
            'https://ayutaz.github.io/piper-plus/dist/openjtalk.js',
            'Should resolve to correct URL'
        );
    });
    
    it('should NOT match paths that are not exact matches', () => {
        const wrongPaths = [
            'dist/other-file.js',
            'other/dist/openjtalk.js.backup',
            'distX/openjtalk.js',
            'dist/openjtalk.js.backup',
            'prefix/dist/openjtalk.js'  // This would match endsWith
        ];
        
        wrongPaths.forEach(path => {
            // New logic: exact matches or endsWith
            const matches = path === 'dist/openjtalk.js' || 
                           path === './dist/openjtalk.js' || 
                           path === '../dist/openjtalk.js' ||
                           path.endsWith('/dist/openjtalk.js');
            
            if (path === 'prefix/dist/openjtalk.js') {
                assert(matches, `Path "${path}" SHOULD match with endsWith`);
            } else {
                assert(!matches, `Path "${path}" should NOT match`);
            }
        });
    });
    
    it('should verify the actual workflow transformation', () => {
        // What the workflow does: s|../../dist/|./dist/|g
        const originalPath = '../../dist/openjtalk.js';
        const workflowTransformed = originalPath.replace('../../dist/', './dist/');
        assert.strictEqual(workflowTransformed, './dist/openjtalk.js');
        
        // But we're seeing 'dist/openjtalk.js' without ./
        // This might be because the workflow sed command is different
    });
    
    it('should handle all possible HTMLconfig values', () => {
        const possibleHTMLPaths = [
            'dist/openjtalk.js',       // What we actually see
            './dist/openjtalk.js',      // What we expected
            '../dist/openjtalk.js',     // Unlikely but possible
            '../../dist/openjtalk.js'   // Original path
        ];
        
        possibleHTMLPaths.forEach(path => {
            if (path.includes('dist/openjtalk.js')) {
                const converted = '../../dist/openjtalk.js';
                const url = new URL(converted, githubPagesImportMetaUrl);
                assert.strictEqual(
                    url.href,
                    'https://ayutaz.github.io/piper-plus/dist/openjtalk.js',
                    `Path "${path}" should resolve correctly`
                );
            }
        });
    });
});

describe('Verify Current Implementation', () => {
    it('should confirm includes() is the right approach', () => {
        // Test both exact match and includes
        const testPath = 'dist/openjtalk.js';
        
        // Old approach (exact match) - would fail
        const exactMatch = testPath === './dist/openjtalk.js';
        assert(!exactMatch, 'Exact match would fail with current path');
        
        // New approach (includes) - should work
        const includesMatch = testPath.includes('dist/openjtalk.js');
        assert(includesMatch, 'Includes match should work');
    });
});