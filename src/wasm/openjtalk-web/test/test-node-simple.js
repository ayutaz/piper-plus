#!/usr/bin/env node

const { readFileSync } = require('fs');
const path = require('path');

// Simple minimal test to check text2mecab behavior

console.log('OpenJTalk WebAssembly Node.js Test');
console.log('=====================================\n');

// Test inputs
const testCases = [
    { input: "こんにちは", desc: "Simple hiragana" },
    { input: "今日はいい天気ですね", desc: "Mixed sentence" },
    { input: "123", desc: "Numbers" },
    { input: "ABC", desc: "English" },
    { input: "こんにちは、世界！", desc: "With punctuation" }
];

// Expected output format from text2mecab
console.log('Expected text2mecab output format:');
console.log('Input text → MeCab format (word,reading,pos,etc.)');
console.log('---\n');

// Show what the browser is trying to do
console.log('Browser test flow:');
console.log('1. Load WASM module');
console.log('2. Initialize file system');
console.log('3. Load dictionary files');
console.log('4. Call openjtalk_initialize("/dict")');
console.log('5. Call openjtalk_synthesis_labels("こんにちは、世界！...")');
console.log('\n');

console.log('Current issue:');
console.log('- Initialization succeeds (Mecab, NJD, JPCommon, HTS Engine all OK)');
console.log('- text2mecab is called but output is not shown in logs');
console.log('- Mecab_analysis returns some value');
console.log('- Mecab_get_size returns 0 or very small value');
console.log('- No labels are generated (JPCommon_get_label_size returns 0)');
console.log('\n');

console.log('Possible causes:');
console.log('1. text2mecab not producing correct output for MeCab');
console.log('2. Dictionary format mismatch');
console.log('3. Character encoding issue (UTF-8 handling)');
console.log('4. Missing initialization step');
console.log('\n');

// Try to check dictionary format
try {
    const dictPath = path.join(__dirname, '..', 'assets', 'dict', 'sys.dic');
    const dictData = readFileSync(dictPath);
    console.log('Dictionary file check:');
    console.log(`- sys.dic size: ${dictData.length} bytes`);
    console.log(`- First 16 bytes (hex): ${dictData.slice(0, 16).toString('hex')}`);
    
    // Check if it starts with MeCab dictionary magic
    if (dictData[0] === 0xDA && dictData[1] === 0xC0) {
        console.log('- Appears to be a valid MeCab dictionary (starts with 0xDAC0)');
    } else {
        console.log('- Warning: Does not start with MeCab magic number');
    }
} catch (e) {
    console.log('Could not check dictionary:', e.message);
}
console.log('\n');

console.log('Next debugging steps:');
console.log('1. Add more debug output to text2mecab function');
console.log('2. Check if dictionary is being loaded correctly by MeCab');
console.log('3. Verify UTF-8 string handling in WASM');
console.log('4. Test with simpler input (single character)');