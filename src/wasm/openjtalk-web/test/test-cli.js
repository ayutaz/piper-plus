#!/usr/bin/env node
/**
 * CLI test for OpenJTalk WebAssembly
 */

const fs = require('fs');
const path = require('path');
const { createRequire } = require('module');

// Test configuration
const PROJECT_DIR = path.join(__dirname, '..');
const DIST_DIR = path.join(PROJECT_DIR, 'dist');
const ASSETS_DIR = path.join(PROJECT_DIR, 'assets');

// Color codes for terminal output
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

async function loadWASMModule() {
    log('Loading WebAssembly module...', 'info');
    
    // Load the module using dynamic import
    const modulePath = path.join(DIST_DIR, 'openjtalk.js');
    const wasmPath = path.join(DIST_DIR, 'openjtalk.wasm');
    
    if (!fs.existsSync(modulePath)) {
        throw new Error(`Module not found: ${modulePath}`);
    }
    if (!fs.existsSync(wasmPath)) {
        throw new Error(`WASM file not found: ${wasmPath}`);
    }
    
    // Read WASM file
    const wasmBinary = fs.readFileSync(wasmPath);
    
    // Load module with Node.js specific settings
    const Module = require(modulePath);
    
    const moduleInstance = await Module({
        wasmBinary: wasmBinary,
        locateFile: (filename) => {
            if (filename.endsWith('.wasm')) {
                return wasmPath;
            }
            return filename;
        },
        // Node.js specific settings
        environment: 'node',
        preRun: [],
        postRun: []
    });
    
    log(`Module loaded successfully (WASM: ${wasmBinary.length} bytes)`, 'success');
    return moduleInstance;
}

function loadDictionaryFiles(Module) {
    log('Loading dictionary files...', 'info');
    
    const dictDir = path.join(ASSETS_DIR, 'dict');
    const dictFiles = [
        'char.bin', 'matrix.bin', 'sys.dic', 'unk.dic',
        'left-id.def', 'pos-id.def', 'rewrite.def', 'right-id.def'
    ];
    
    // Create directory in virtual FS
    try {
        Module.FS.mkdir('/dict');
    } catch (e) {
        // Directory may already exist
    }
    
    let totalSize = 0;
    for (const file of dictFiles) {
        const filePath = path.join(dictDir, file);
        if (!fs.existsSync(filePath)) {
            throw new Error(`Dictionary file not found: ${filePath}`);
        }
        
        const data = fs.readFileSync(filePath);
        Module.FS.writeFile(`/dict/${file}`, data);
        totalSize += data.length;
        log(`  Loaded ${file} (${data.length.toLocaleString()} bytes)`, 'info');
    }
    
    log(`Dictionary loaded successfully (Total: ${totalSize.toLocaleString()} bytes)`, 'success');
}

function initializeOpenJTalk(Module) {
    log('Initializing OpenJTalk...', 'info');
    
    const dictPtr = Module.allocateUTF8('/dict');

    const result = Module._openjtalk_initialize(dictPtr);

    Module._free(dictPtr);
    
    if (result === 0) {
        log('OpenJTalk initialized successfully!', 'success');
        return true;
    } else {
        throw new Error(`OpenJTalk initialization failed with code: ${result}`);
    }
}

function runTest(Module, testName, text, expectedPhonemes = null) {
    log(`Test: ${testName}`, 'test');
    log(`  Input: "${text}"`, 'info');
    
    try {
        const textPtr = Module.allocateUTF8(text);
        const labelsPtr = Module._openjtalk_synthesis_labels(textPtr);
        const labels = Module.UTF8ToString(labelsPtr);
        
        Module._openjtalk_free_string(labelsPtr);
        Module._free(textPtr);
        
        // Extract phonemes
        const phonemes = [];
        const lines = labels.split('\n').filter(line => line.trim());
        
        for (const line of lines) {
            const match = line.match(/\-([^+]+)\+/);
            if (match && match[1] !== 'sil') {
                phonemes.push(match[1]);
            }
        }
        
        log(`  Phonemes: ${phonemes.join(' ')}`, 'info');
        log(`  Labels: ${lines.length} lines`, 'info');
        
        if (expectedPhonemes) {
            const match = JSON.stringify(phonemes) === JSON.stringify(expectedPhonemes);
            if (match) {
                log(`  ✅ PASS - Phonemes match expected`, 'success');
            } else {
                log(`  ❌ FAIL - Expected: ${expectedPhonemes.join(' ')}`, 'error');
            }
            return match;
        } else {
            const pass = phonemes.length > 0;
            log(`  ${pass ? '✅ PASS' : '❌ FAIL'} - ${phonemes.length} phonemes extracted`, pass ? 'success' : 'error');
            return pass;
        }
        
    } catch (error) {
        log(`  ❌ ERROR: ${error.message}`, 'error');
        return false;
    }
}

async function main() {
    console.log(`${colors.bright}${colors.cyan}=== OpenJTalk WebAssembly CLI Test ===${colors.reset}\n`);
    
    let Module = null;
    let passCount = 0;
    let totalCount = 0;
    
    try {
        // Load module
        Module = await loadWASMModule();
        
        // Check exported functions
        log('Checking exported functions...', 'info');
        const functions = [
            '_openjtalk_initialize',
            '_openjtalk_synthesis_labels',
            '_openjtalk_clear',
            '_openjtalk_free_string',
            '_get_version',
            '_test_function'
        ];
        
        for (const func of functions) {
            const exists = func in Module;
            log(`  ${func}: ${exists ? '✓' : '✗'}`, exists ? 'success' : 'error');
        }
        
        // Test basic functions
        if (Module._get_version) {
            const versionPtr = Module._get_version();
            const version = Module.UTF8ToString(versionPtr);
            log(`Version: ${version}`, 'info');
        }
        
        if (Module._test_function) {
            const result = Module._test_function(25, 17);
            log(`Test function (25 + 17): ${result} ${result === 42 ? '✓' : '✗'}`, result === 42 ? 'success' : 'error');
        }
        
        // Load resources
        loadDictionaryFiles(Module);

        // Initialize
        initializeOpenJTalk(Module);
        
        // Run tests
        console.log(`\n${colors.bright}Running conversion tests...${colors.reset}`);
        
        const tests = [
            { name: 'Basic Hiragana', text: 'こんにちは' },
            { name: 'Katakana', text: 'コンピューター' },
            { name: 'Kanji', text: '今日は良い天気です' },
            { name: 'Numbers', text: '2024年8月1日' },
            { name: 'Mixed', text: 'OpenJTalkをWebAssemblyで動かす' },
            { name: 'Punctuation', text: 'はい、そうです！' },
            { name: 'Long text', text: '日本語の音声合成システムをウェブブラウザで動作させることができました。' }
        ];
        
        for (const test of tests) {
            if (runTest(Module, test.name, test.text)) {
                passCount++;
            }
            totalCount++;
        }
        
        // Summary
        console.log(`\n${colors.bright}=== Test Summary ===${colors.reset}`);
        log(`Total tests: ${totalCount}`, 'info');
        log(`Passed: ${passCount}`, 'success');
        log(`Failed: ${totalCount - passCount}`, passCount === totalCount ? 'info' : 'error');
        
        const successRate = (passCount / totalCount * 100).toFixed(1);
        log(`Success rate: ${successRate}%`, passCount === totalCount ? 'success' : 'warn');
        
        // Cleanup
        if (Module._openjtalk_clear) {
            Module._openjtalk_clear();
            log('OpenJTalk cleaned up', 'info');
        }
        
        process.exit(passCount === totalCount ? 0 : 1);
        
    } catch (error) {
        log(`Fatal error: ${error.message}`, 'error');
        console.error(error.stack);
        process.exit(1);
    }
}

// Run tests
main();