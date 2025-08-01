#!/usr/bin/env node
/**
 * CLI test for OpenJTalk WebAssembly (ES Module version)
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

// Get __dirname equivalent in ES modules
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

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
    
    const wasmPath = path.join(DIST_DIR, 'openjtalk.wasm');
    
    if (!fs.existsSync(wasmPath)) {
        throw new Error(`WASM file not found: ${wasmPath}`);
    }
    
    // Read WASM file
    const wasmBinary = fs.readFileSync(wasmPath);
    
    // Import the ES6 module
    const OpenJTalkModule = (await import(path.join(DIST_DIR, 'openjtalk.js'))).default;
    
    // Create module instance with Node.js environment
    // Emscripten needs to detect Node.js environment
    globalThis.window = undefined;  // Ensure we're not detected as browser
    globalThis.importScripts = undefined;
    
    const moduleInstance = await OpenJTalkModule({
        wasmBinary: wasmBinary,
        locateFile: (filename) => {
            if (filename.endsWith('.wasm')) {
                return wasmPath;
            }
            return filename;
        },
        // Force Node.js environment
        ENVIRONMENT: 'node',
        // Provide Node.js specific functions
        print: (text) => console.log(text),
        printErr: (text) => console.error(text)
    });
    
    log(`Module loaded successfully (WASM: ${wasmBinary.length.toLocaleString()} bytes)`, 'success');
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

function loadVoiceFile(Module) {
    log('Loading voice file...', 'info');
    
    const voicePath = path.join(ASSETS_DIR, 'voice', 'mei_normal.htsvoice');
    if (!fs.existsSync(voicePath)) {
        throw new Error(`Voice file not found: ${voicePath}`);
    }
    
    // Create directory in virtual FS
    try {
        Module.FS.mkdir('/voice');
    } catch (e) {
        // Directory may already exist
    }
    
    const data = fs.readFileSync(voicePath);
    Module.FS.writeFile('/voice/mei_normal.htsvoice', data);
    
    log(`Voice file loaded successfully (${data.length.toLocaleString()} bytes)`, 'success');
}

function initializeOpenJTalk(Module) {
    log('Initializing OpenJTalk...', 'info');
    
    const dictPtr = Module.allocateUTF8('/dict');
    const voicePtr = Module.allocateUTF8('/voice/mei_normal.htsvoice');
    
    const result = Module._openjtalk_initialize(dictPtr, voicePtr);
    
    Module._free(dictPtr);
    Module._free(voicePtr);
    
    if (result === 0) {
        log('OpenJTalk initialized successfully!', 'success');
        return true;
    } else {
        throw new Error(`OpenJTalk initialization failed with code: ${result}`);
    }
}

function extractPhonemesFromLabels(labels) {
    const phonemes = [];
    const lines = labels.split('\n').filter(line => line.trim());
    
    for (const line of lines) {
        const match = line.match(/\-([^+]+)\+/);
        if (match && match[1] !== 'sil') {
            phonemes.push(match[1]);
        }
    }
    
    return phonemes;
}

function runTest(Module, testName, text, expectedPhonemes = null) {
    log(`Test: ${testName}`, 'test');
    log(`  Input: "${text}"`, 'info');
    
    try {
        const startTime = performance.now();
        
        const textPtr = Module.allocateUTF8(text);
        const labelsPtr = Module._openjtalk_synthesis_labels(textPtr);
        const labels = Module.UTF8ToString(labelsPtr);
        
        Module._openjtalk_free_string(labelsPtr);
        Module._free(textPtr);
        
        const endTime = performance.now();
        const processingTime = (endTime - startTime).toFixed(2);
        
        // Extract phonemes
        const phonemes = extractPhonemesFromLabels(labels);
        const lines = labels.split('\n').filter(line => line.trim());
        
        log(`  Phonemes: ${phonemes.join(' ')}`, 'info');
        log(`  Stats: ${lines.length} labels, ${phonemes.length} phonemes, ${processingTime}ms`, 'info');
        
        // Show first few labels as sample
        if (lines.length > 0) {
            log(`  Sample label: ${lines[0]}`, 'info');
        }
        
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

async function runBenchmark(Module) {
    log('\nRunning performance benchmark...', 'info');
    
    const texts = [
        'こんにちは',
        '今日は良い天気です',
        '日本語の音声合成システムをウェブブラウザで動作させることができました。'
    ];
    
    for (const text of texts) {
        const iterations = 10;
        const times = [];
        
        for (let i = 0; i < iterations; i++) {
            const startTime = performance.now();
            
            const textPtr = Module.allocateUTF8(text);
            const labelsPtr = Module._openjtalk_synthesis_labels(textPtr);
            Module._openjtalk_free_string(labelsPtr);
            Module._free(textPtr);
            
            const endTime = performance.now();
            times.push(endTime - startTime);
        }
        
        const avgTime = (times.reduce((a, b) => a + b, 0) / times.length).toFixed(2);
        const minTime = Math.min(...times).toFixed(2);
        const maxTime = Math.max(...times).toFixed(2);
        
        log(`  "${text}" (${text.length} chars)`, 'info');
        log(`    Average: ${avgTime}ms, Min: ${minTime}ms, Max: ${maxTime}ms`, 'info');
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
        loadVoiceFile(Module);
        
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
            { name: 'Long text', text: '日本語の音声合成システムをウェブブラウザで動作させることができました。' },
            { name: 'Empty text', text: '' },
            { name: 'Emoji', text: 'こんにちは😊' }
        ];
        
        for (const test of tests) {
            if (runTest(Module, test.name, test.text)) {
                passCount++;
            }
            totalCount++;
        }
        
        // Run benchmark
        await runBenchmark(Module);
        
        // Summary
        console.log(`\n${colors.bright}=== Test Summary ===${colors.reset}`);
        log(`Total tests: ${totalCount}`, 'info');
        log(`Passed: ${passCount}`, 'success');
        log(`Failed: ${totalCount - passCount}`, passCount === totalCount ? 'info' : 'error');
        
        const successRate = (passCount / totalCount * 100).toFixed(1);
        log(`Success rate: ${successRate}%`, passCount === totalCount ? 'success' : 'warn');
        
        // Memory usage
        if (Module.HEAP8) {
            const heapSize = Module.HEAP8.length;
            log(`Heap size: ${(heapSize / 1024 / 1024).toFixed(2)} MB`, 'info');
        }
        
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