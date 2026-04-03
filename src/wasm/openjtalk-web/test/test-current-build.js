#!/usr/bin/env node
/**
 * 現在のビルド成果物をテストするNode.jsスクリプト
 */

const fs = require('fs');
const path = require('path');

// テスト結果を記録
const testResults = [];

function log(message, status = 'INFO') {
    const timestamp = new Date().toISOString();
    console.log(`[${timestamp}] [${status}] ${message}`);
    testResults.push({ timestamp, status, message });
}

function testFileExists(filePath, description) {
    const exists = fs.existsSync(filePath);
    const status = exists ? 'PASS' : 'FAIL';
    log(`${description}: ${exists ? '存在' : '不在'}`, status);
    return exists;
}

async function testModuleLoad() {
    log('=== WASMモジュールロードテスト ===');
    
    const distDir = path.join(__dirname, '../dist');
    const jsPath = path.join(distDir, 'openjtalk.js');
    const wasmPath = path.join(distDir, 'openjtalk.wasm');
    
    // ファイルの存在確認
    const jsExists = testFileExists(jsPath, 'JavaScriptファイル');
    const wasmExists = testFileExists(wasmPath, 'WASMファイル');
    
    if (!jsExists || !wasmExists) {
        log('必要なファイルが見つかりません。ビルドを実行してください。', 'ERROR');
        return false;
    }
    
    // ファイルサイズの確認
    const jsStats = fs.statSync(jsPath);
    const wasmStats = fs.statSync(wasmPath);
    log(`JSファイルサイズ: ${jsStats.size} bytes`);
    log(`WASMファイルサイズ: ${wasmStats.size} bytes`);
    
    // モジュールのロードテスト
    try {
        log('モジュールをロード中...');
        const Module = require(jsPath);
        
        // モジュールインスタンスの作成
        const instance = await Module({
            locateFile: (filename) => {
                if (filename.endsWith('.wasm')) {
                    return wasmPath;
                }
                return filename;
            }
        });
        
        log('モジュールのロードに成功', 'PASS');
        
        // エクスポートされた関数の確認
        const exportedFunctions = Object.keys(instance).filter(key => key.startsWith('_'));
        log(`エクスポートされた関数: ${exportedFunctions.length}個`);
        exportedFunctions.forEach(func => {
            log(`  - ${func}`);
        });
        
        // 基本的な関数のテスト
        if (instance._get_version) {
            const versionPtr = instance._get_version();
            const version = instance.UTF8ToString(versionPtr);
            log(`バージョン: ${version}`, 'PASS');
        }
        
        if (instance._test_function) {
            const result = instance._test_function(10, 20);
            const expected = 30;
            if (result === expected) {
                log(`テスト関数 (10 + 20): ${result} ✓`, 'PASS');
            } else {
                log(`テスト関数失敗: 期待値 ${expected}, 実際 ${result}`, 'FAIL');
            }
        }
        
        // OpenJTalk関数の存在確認
        const openjtalkFunctions = [
            '_openjtalk_initialize',
            '_openjtalk_synthesis_labels',
            '_openjtalk_clear',
            '_openjtalk_free_string'
        ];
        
        log('OpenJTalk関数の確認:');
        openjtalkFunctions.forEach(func => {
            const exists = func in instance;
            log(`  ${func}: ${exists ? '存在' : '不在'}`, exists ? 'PASS' : 'WARN');
        });
        
        return true;
        
    } catch (error) {
        log(`モジュールロードエラー: ${error.message}`, 'ERROR');
        log(`スタックトレース: ${error.stack}`, 'ERROR');
        return false;
    }
}

async function testProjectStructure() {
    log('=== プロジェクト構造テスト ===');
    
    const projectRoot = path.join(__dirname, '..');
    const requiredDirs = [
        'src',
        'build', 
        'dist',
        'test',
        'demo'
    ];
    
    const requiredFiles = [
        'build/build.sh',
        'build/build-simple.sh',
        'build/build-openjtalk.sh',
        'build/emscripten-flags.mk',
        'build/docker-build-simple.sh',
        'src/api.js',
        'src/simple_wrapper.cpp'
    ];
    
    log('必須ディレクトリの確認:');
    requiredDirs.forEach(dir => {
        const dirPath = path.join(projectRoot, dir);
        testFileExists(dirPath, `  ${dir}/`);
    });
    
    log('必須ファイルの確認:');
    requiredFiles.forEach(file => {
        const filePath = path.join(projectRoot, file);
        testFileExists(filePath, `  ${file}`);
    });
    
    return true;
}

async function generateTestReport() {
    log('=== テストレポート生成 ===');
    
    const reportPath = path.join(__dirname, 'test-report.json');
    const report = {
        timestamp: new Date().toISOString(),
        results: testResults,
        summary: {
            total: testResults.length,
            passed: testResults.filter(r => r.status === 'PASS').length,
            failed: testResults.filter(r => r.status === 'FAIL').length,
            warnings: testResults.filter(r => r.status === 'WARN').length,
            errors: testResults.filter(r => r.status === 'ERROR').length
        }
    };
    
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
    log(`テストレポートを生成: ${reportPath}`, 'PASS');
    
    // サマリーの表示
    console.log('\n=== テストサマリー ===');
    console.log(`総テスト数: ${report.summary.total}`);
    console.log(`成功: ${report.summary.passed}`);
    console.log(`失敗: ${report.summary.failed}`);
    console.log(`警告: ${report.summary.warnings}`);
    console.log(`エラー: ${report.summary.errors}`);
    
    return report.summary.failed === 0 && report.summary.errors === 0;
}

// メイン実行
async function main() {
    console.log('OpenJTalk WebAssembly 現在のビルドテスト\n');
    
    // プロジェクト構造のテスト
    await testProjectStructure();
    
    console.log('');
    
    // モジュールロードテスト
    await testModuleLoad();
    
    console.log('');
    
    // レポート生成
    const success = await generateTestReport();
    
    process.exit(success ? 0 : 1);
}

main().catch(error => {
    console.error('テスト実行エラー:', error);
    process.exit(1);
});