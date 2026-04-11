#!/usr/bin/env node
/**
 * Headless browser test for OpenJTalk WebAssembly
 * Uses Chrome DevTools Protocol for fast iteration
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Test configuration
const PORT = 8888;
const PROJECT_DIR = path.join(__dirname, '..');

// Color codes
const colors = {
    reset: '\x1b[0m',
    bright: '\x1b[1m',
    red: '\x1b[31m',
    green: '\x1b[32m',
    yellow: '\x1b[33m',
    blue: '\x1b[34m',
    magenta: '\x1b[35m',
    cyan: '\x1b[36m'
};

function log(message, type = 'info') {
    const color = {
        info: colors.blue,
        success: colors.green,
        error: colors.red,
        warn: colors.yellow,
        test: colors.magenta
    }[type] || colors.reset;
    
    console.log(`${color}[${new Date().toISOString().split('T')[1].split('.')[0]}] ${message}${colors.reset}`);
}

// Create a simple HTTP server
function startServer() {
    return new Promise((resolve) => {
        const server = http.createServer((req, res) => {
            // TODO: M2 で新テストページに差し替え
            let filePath = path.join(PROJECT_DIR, req.url === '/' ? '/demo/index.html' : req.url);
            
            // Security check
            if (!filePath.startsWith(PROJECT_DIR)) {
                res.writeHead(403);
                res.end('Forbidden');
                return;
            }
            
            fs.readFile(filePath, (err, data) => {
                if (err) {
                    res.writeHead(404);
                    res.end('Not found');
                    return;
                }
                
                // Set proper MIME types
                const ext = path.extname(filePath);
                const mimeTypes = {
                    '.html': 'text/html',
                    '.js': 'application/javascript',
                    '.mjs': 'application/javascript',
                    '.wasm': 'application/wasm',
                    '.json': 'application/json'
                };
                
                res.writeHead(200, {
                    'Content-Type': mimeTypes[ext] || 'application/octet-stream',
                    'Access-Control-Allow-Origin': '*'
                });
                res.end(data);
            });
        });
        
        server.listen(PORT, () => {
            log(`Test server running at http://localhost:${PORT}`, 'info');
            resolve(server);
        });
    });
}

// Create test HTML
function createTestHTML() {
    const html = `<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>OpenJTalk WebAssembly Headless Test</title>
</head>
<body>
    <h1>OpenJTalk WebAssembly Headless Test</h1>
    <pre id="output"></pre>
    
    <script type="module">
        // Test results
        window.testResults = {
            loaded: false,
            initialized: false,
            tests: [],
            errors: []
        };
        
        function log(message, type = 'info') {
            const output = document.getElementById('output');
            const timestamp = new Date().toISOString().split('T')[1].split('.')[0];
            output.textContent += \`[\${timestamp}] [\${type}] \${message}\\n\`;
            
            // Also log to console for headless access
            console.log(\`TEST_LOG: [\${type}] \${message}\`);
        }
        
        async function runTests() {
            try {
                log('Loading OpenJTalk WebAssembly module...', 'info');
                
                // Load module
                const Module = (await import('../dist/openjtalk.js')).default;
                const moduleInstance = await Module({
                    locateFile: (path) => {
                        if (path.endsWith('.wasm')) {
                            return '../dist/openjtalk.wasm';
                        }
                        return path;
                    }
                });
                
                window.testResults.loaded = true;
                log('Module loaded successfully', 'success');
                
                // Check functions
                const functions = [
                    '_openjtalk_initialize',
                    '_openjtalk_synthesis_labels',
                    '_openjtalk_clear',
                    '_openjtalk_free_string',
                    '_get_version',
                    '_test_function'
                ];
                
                for (const func of functions) {
                    const exists = func in moduleInstance;
                    log(\`Function \${func}: \${exists ? '✓' : '✗'}\`, exists ? 'success' : 'error');
                }
                
                // Load dictionary
                log('Loading dictionary files...', 'info');
                const FS = moduleInstance.FS;
                FS.mkdir('/dict');
                
                const dictFiles = [
                    'char.bin', 'matrix.bin', 'sys.dic', 'unk.dic',
                    'left-id.def', 'pos-id.def', 'rewrite.def', 'right-id.def'
                ];
                
                for (const file of dictFiles) {
                    const response = await fetch(\`../assets/dict/\${file}\`);
                    const data = await response.arrayBuffer();
                    FS.writeFile(\`/dict/\${file}\`, new Uint8Array(data));
                    log(\`Loaded \${file}\`, 'info');
                }
                
                // Initialize
                log('Initializing OpenJTalk...', 'info');
                const dictPtr = moduleInstance.allocateUTF8('/dict');
                const result = moduleInstance._openjtalk_initialize(dictPtr);
                moduleInstance._free(dictPtr);
                
                if (result === 0) {
                    window.testResults.initialized = true;
                    log('OpenJTalk initialized successfully', 'success');
                } else {
                    throw new Error(\`Initialization failed with code: \${result}\`);
                }
                
                // Run tests
                const tests = [
                    { name: 'Hiragana', text: 'こんにちは' },
                    { name: 'Katakana', text: 'コンピューター' },
                    { name: 'Kanji', text: '今日は良い天気です' },
                    { name: 'Numbers', text: '2024年' },
                    { name: 'Mixed', text: 'OpenJTalkテスト' }
                ];
                
                for (const test of tests) {
                    try {
                        const textPtr = moduleInstance.allocateUTF8(test.text);
                        const labelsPtr = moduleInstance._openjtalk_synthesis_labels(textPtr);
                        const labels = moduleInstance.UTF8ToString(labelsPtr);
                        
                        moduleInstance._openjtalk_free_string(labelsPtr);
                        moduleInstance._free(textPtr);
                        
                        // Extract phonemes
                        const phonemes = [];
                        const lines = labels.split('\\n').filter(line => line.trim());
                        for (const line of lines) {
                            const match = line.match(/\\-([^+]+)\\+/);
                            if (match && match[1] !== 'sil') {
                                phonemes.push(match[1]);
                            }
                        }
                        
                        const success = phonemes.length > 0;
                        window.testResults.tests.push({
                            name: test.name,
                            text: test.text,
                            phonemes: phonemes,
                            success: success
                        });
                        
                        log(\`Test "\${test.name}": \${success ? 'PASS' : 'FAIL'} - \${phonemes.join(' ')}\`, success ? 'success' : 'error');
                        
                    } catch (error) {
                        window.testResults.tests.push({
                            name: test.name,
                            text: test.text,
                            success: false,
                            error: error.message
                        });
                        log(\`Test "\${test.name}": ERROR - \${error.message}\`, 'error');
                    }
                }
                
                // Summary
                const passed = window.testResults.tests.filter(t => t.success).length;
                const total = window.testResults.tests.length;
                log(\`\\nTest Summary: \${passed}/\${total} passed\`, passed === total ? 'success' : 'warn');
                
                // Cleanup
                moduleInstance._openjtalk_clear();
                
                // Signal completion
                window.testResults.complete = true;
                console.log('TEST_COMPLETE:', JSON.stringify(window.testResults));
                
            } catch (error) {
                window.testResults.errors.push(error.message);
                log(\`Fatal error: \${error.message}\`, 'error');
                console.error('TEST_ERROR:', error);
                window.testResults.complete = true;
            }
        }
        
        // Run tests when page loads
        window.addEventListener('load', runTests);
    </script>
</body>
</html>`;
    
    // TODO: M2 で新テストページに差し替え (createTestHTML() が生成する一時ファイル)
    const testPath = path.join(PROJECT_DIR, 'test', 'headless-test-generated.html');
    fs.writeFileSync(testPath, html);
    return testPath;
}

// Run headless test using curl and simple parsing
async function runHeadlessTest() {
    const server = await startServer();
    const testPath = createTestHTML();
    
    try {
        log('Running headless browser test...', 'info');
        
        // Check if Chrome is available
        let chromePath = null;
        const possiblePaths = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/usr/bin/google-chrome',
            '/usr/bin/chromium-browser'
        ];
        
        for (const path of possiblePaths) {
            if (fs.existsSync(path)) {
                chromePath = path;
                break;
            }
        }
        
        if (!chromePath) {
            throw new Error('Chrome/Chromium not found. Please install Chrome.');
        }
        
        // Run Chrome in headless mode
        log('Launching headless Chrome...', 'info');
        const chromeOutput = execSync(
            // TODO: M2 で新テストページに差し替え
            `"${chromePath}" --headless --disable-gpu --no-sandbox --enable-logging --dump-dom http://localhost:${PORT}/test/headless-test-generated.html 2>&1 | grep -E "(TEST_LOG:|TEST_COMPLETE:|TEST_ERROR:)" || true`,
            { encoding: 'utf-8', shell: '/bin/bash' }
        );
        
        // Parse output
        const lines = chromeOutput.split('\n').filter(line => line.includes('TEST_'));
        let testComplete = false;
        let results = null;
        
        for (const line of lines) {
            if (line.includes('TEST_LOG:')) {
                const logMatch = line.match(/TEST_LOG: \[(\w+)\] (.+)/);
                if (logMatch) {
                    log(logMatch[2], logMatch[1]);
                }
            } else if (line.includes('TEST_COMPLETE:')) {
                const jsonMatch = line.match(/TEST_COMPLETE: (.+)/);
                if (jsonMatch) {
                    try {
                        results = JSON.parse(jsonMatch[1]);
                        testComplete = true;
                    } catch (e) {
                        log('Failed to parse test results', 'error');
                    }
                }
            } else if (line.includes('TEST_ERROR:')) {
                log(line, 'error');
            }
        }
        
        // Display summary
        if (results && testComplete) {
            console.log(`\n${colors.bright}=== Test Results ===${colors.reset}`);
            log(`Module loaded: ${results.loaded ? 'Yes' : 'No'}`, results.loaded ? 'success' : 'error');
            log(`Initialized: ${results.initialized ? 'Yes' : 'No'}`, results.initialized ? 'success' : 'error');
            
            if (results.tests && results.tests.length > 0) {
                const passed = results.tests.filter(t => t.success).length;
                const total = results.tests.length;
                log(`Tests passed: ${passed}/${total}`, passed === total ? 'success' : 'warn');
                
                // Return appropriate exit code
                process.exit(passed === total ? 0 : 1);
            }
        } else {
            log('Test did not complete successfully', 'error');
            process.exit(1);
        }
        
    } finally {
        // Cleanup
        server.close();
        if (fs.existsSync(testPath)) {
            fs.unlinkSync(testPath);
        }
    }
}

// Main
console.log(`${colors.bright}${colors.cyan}=== OpenJTalk WebAssembly Headless Test ===${colors.reset}\n`);
runHeadlessTest().catch(error => {
    log(`Fatal error: ${error.message}`, 'error');
    console.error(error);
    process.exit(1);
});