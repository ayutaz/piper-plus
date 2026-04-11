#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

console.log('Testing wasm_open_jtalk reference implementation in Node.js');
console.log('=========================================================\n');

// First, let's check if the dictionary files are valid
const dictPath = path.join(__dirname, '..', 'tools', 'wasm_open_jtalk', 'etc', 'open_jtalk_dic_utf_8-1.11');
const files = ['sys.dic', 'unk.dic', 'char.bin', 'matrix.bin'];

console.log('Checking dictionary files:');
for (const file of files) {
    const filePath = path.join(dictPath, file);
    try {
        const stats = fs.statSync(filePath);
        const data = fs.readFileSync(filePath);
        console.log(`- ${file}: ${stats.size} bytes`);
        console.log(`  First 16 bytes (hex): ${data.slice(0, 16).toString('hex')}`);
    } catch (e) {
        console.log(`- ${file}: ERROR - ${e.message}`);
    }
}

console.log('\nComparing with our dictionary files:');
const ourDictPath = path.join(__dirname, '..', 'assets', 'dict');
for (const file of files) {
    const filePath = path.join(ourDictPath, file);
    try {
        const stats = fs.statSync(filePath);
        const data = fs.readFileSync(filePath);
        console.log(`- ${file}: ${stats.size} bytes`);
        console.log(`  First 16 bytes (hex): ${data.slice(0, 16).toString('hex')}`);
    } catch (e) {
        console.log(`- ${file}: ERROR - ${e.message}`);
    }
}

// Check for magic numbers
console.log('\nDictionary format check:');
const sysDicPath = path.join(dictPath, 'sys.dic');
const sysDicData = fs.readFileSync(sysDicPath);

// MeCab dictionary should have specific structure
console.log('sys.dic structure:');
console.log('- First 4 bytes (uint32): 0x' + sysDicData.readUInt32LE(0).toString(16));
console.log('- Bytes 4-8 (uint32): 0x' + sysDicData.readUInt32LE(4).toString(16));
console.log('- Bytes 8-12 (uint32): 0x' + sysDicData.readUInt32LE(8).toString(16));

console.log('\nKey observations:');
console.log('1. The dictionary files are quite large (sys.dic is ~103MB)');
console.log('2. The format does not start with standard MeCab magic number (0xDAC0)');
console.log('3. This suggests the dictionary might be pre-compiled for a specific version');
console.log('4. Both wasm_open_jtalk and our copies have the same format');

console.log('\nPossible issues in our implementation:');
console.log('1. Missing initialization of some internal structures');
console.log('2. Character encoding mismatch (though we are using UTF-8)');
console.log('3. text2mecab might not be producing correct output');
console.log('4. Missing call to JPCommon_make_label before getting labels');

console.log('\nNext steps:');
console.log('1. Check if we need to call Open_JTalk_load instead of individual components');
console.log('2. Verify the order of initialization');
console.log('3. Add more debug output to trace the exact failure point');
console.log('4. Test with the simplest possible input (single character)');