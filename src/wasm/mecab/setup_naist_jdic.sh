#!/bin/bash
# Complete setup script for NAIST-JDIC dictionary in WebAssembly

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "=== NAIST-JDIC Dictionary Setup for WebAssembly ==="
echo ""

# Step 1: Download the dictionary
echo "Step 1: Downloading dictionary..."
./download_dict.sh

# Step 2: Build the compression tool if needed
echo ""
echo "Step 2: Building dictionary compression tool..."
cd ../build-tools
if [ ! -f "dict_compressor" ]; then
    echo "Compression tool not found, building..."
    cmake ..
    make dict_compressor
else
    echo "Compression tool already exists."
fi
cd ../mecab

# Step 3: Prepare dictionary for compression
echo ""
echo "Step 3: Preparing dictionary for compression..."
cd dict
./prepare_for_compression.sh
cd ..

# Step 4: Compress the dictionary
echo ""
echo "Step 4: Compressing dictionary..."
../build-tools/dict_compressor \
    -i dict/naist-jdic-prepared/dict.csv \
    -o dict/naist-jdic.compressed \
    --char-def dict/naist-jdic-prepared/char.def \
    --unk-def dict/naist-jdic-prepared/unk.def

# Step 5: Create a test script
echo ""
echo "Step 5: Creating test script..."
cat > test_naist_jdic.js << 'EOF'
// Test script for NAIST-JDIC dictionary with MeCab WebAssembly

async function testNAISTJDIC() {
    console.log('Loading MeCab with NAIST-JDIC dictionary...');
    
    try {
        // Initialize MeCab with NAIST-JDIC
        const mecab = await MeCab.create({
            dicdir: '/dict',
            rcfile: '/dict/mecabrc-naist-jdic'
        });
        
        // Test sentences
        const testSentences = [
            'こんにちは世界',
            '私は日本語を勉強しています。',
            'MeCabは形態素解析エンジンです。',
            '東京都渋谷区にある会社です。',
            '今日はいい天気ですね。'
        ];
        
        console.log('\nTesting NAIST-JDIC dictionary:\n');
        
        for (const sentence of testSentences) {
            console.log(`Input: ${sentence}`);
            console.log('Output:');
            const result = mecab.parse(sentence);
            console.log(result);
            console.log('---');
        }
        
        // Cleanup
        mecab.destroy();
        console.log('\nTest completed successfully!');
        
    } catch (error) {
        console.error('Error:', error);
    }
}

// Run test when module is loaded
if (typeof Module !== 'undefined') {
    Module.onRuntimeInitialized = testNAISTJDIC;
} else {
    console.error('MeCab module not loaded');
}
EOF

# Create an HTML test page
cat > test_naist_jdic.html << 'EOF'
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NAIST-JDIC Dictionary Test</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        h1 {
            color: #333;
            border-bottom: 2px solid #4CAF50;
            padding-bottom: 10px;
        }
        .test-container {
            background-color: white;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        #input {
            width: 100%;
            padding: 10px;
            font-size: 16px;
            border: 1px solid #ddd;
            border-radius: 4px;
            margin-bottom: 10px;
        }
        button {
            background-color: #4CAF50;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            font-size: 16px;
            cursor: pointer;
            margin-right: 10px;
        }
        button:hover {
            background-color: #45a049;
        }
        button:disabled {
            background-color: #ccc;
            cursor: not-allowed;
        }
        #output {
            background-color: #f9f9f9;
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 15px;
            font-family: monospace;
            white-space: pre-wrap;
            min-height: 200px;
        }
        .status {
            padding: 10px;
            border-radius: 4px;
            margin: 10px 0;
        }
        .status.loading {
            background-color: #fff3cd;
            color: #856404;
        }
        .status.success {
            background-color: #d4edda;
            color: #155724;
        }
        .status.error {
            background-color: #f8d7da;
            color: #721c24;
        }
    </style>
</head>
<body>
    <h1>NAIST-JDIC Dictionary Test for MeCab WebAssembly</h1>
    
    <div class="test-container">
        <h2>Dictionary Information</h2>
        <div id="dict-info" class="status loading">Loading dictionary information...</div>
    </div>
    
    <div class="test-container">
        <h2>Test MeCab with NAIST-JDIC</h2>
        <input type="text" id="input" placeholder="Enter Japanese text to analyze..." value="私は日本語を勉強しています。">
        <div>
            <button id="parseBtn" disabled>Parse Text</button>
            <button id="batchTestBtn" disabled>Run Batch Test</button>
        </div>
        <div id="output"></div>
    </div>

    <script src="dist/mecab_wasm.js"></script>
    <script src="dist/mecab-wrapper.js"></script>
    <script>
        let mecab = null;
        const output = document.getElementById('output');
        const parseBtn = document.getElementById('parseBtn');
        const batchTestBtn = document.getElementById('batchTestBtn');
        const dictInfo = document.getElementById('dict-info');
        const input = document.getElementById('input');

        async function initializeMeCab() {
            try {
                dictInfo.textContent = 'Initializing MeCab with NAIST-JDIC dictionary...';
                
                mecab = await MeCab.create({
                    dictPath: '/dict/naist-jdic.compressed'
                });
                
                dictInfo.className = 'status success';
                dictInfo.innerHTML = `
                    <strong>Dictionary loaded successfully!</strong><br>
                    Type: NAIST-JDIC (mecab-naist-jdic)<br>
                    Version: 1.11<br>
                    Status: Ready for parsing
                `;
                
                parseBtn.disabled = false;
                batchTestBtn.disabled = false;
                
            } catch (error) {
                dictInfo.className = 'status error';
                dictInfo.textContent = `Failed to load dictionary: ${error.message}`;
                console.error('Initialization error:', error);
            }
        }

        function parseText() {
            const text = input.value.trim();
            if (!text) {
                output.textContent = 'Please enter some text to parse.';
                return;
            }
            
            try {
                const result = mecab.parse(text);
                output.textContent = `Input: ${text}\n\nParsed output:\n${result}`;
            } catch (error) {
                output.textContent = `Error: ${error.message}`;
            }
        }

        function runBatchTest() {
            const testSentences = [
                'こんにちは世界',
                '私は日本語を勉強しています。',
                'MeCabは形態素解析エンジンです。',
                '東京都渋谷区にある会社です。',
                '今日はいい天気ですね。',
                '人工知能の研究が進んでいます。',
                '新しいプログラミング言語を学ぶ。'
            ];
            
            let results = 'Batch Test Results:\n\n';
            
            for (const sentence of testSentences) {
                try {
                    const parsed = mecab.parse(sentence);
                    results += `Input: ${sentence}\n${parsed}\n${'='.repeat(50)}\n\n`;
                } catch (error) {
                    results += `Input: ${sentence}\nError: ${error.message}\n${'='.repeat(50)}\n\n`;
                }
            }
            
            output.textContent = results;
        }

        parseBtn.addEventListener('click', parseText);
        batchTestBtn.addEventListener('click', runBatchTest);
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !parseBtn.disabled) {
                parseText();
            }
        });

        // Initialize when ready
        Module.onRuntimeInitialized = initializeMeCab;
    </script>
</body>
</html>
EOF

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Dictionary files created:"
echo "  - dict/naist-jdic/ (original dictionary)"
echo "  - dict/naist-jdic-prepared/ (prepared for compression)"
echo "  - dict/naist-jdic.compressed (compressed dictionary)"
echo ""
echo "Test files created:"
echo "  - test_naist_jdic.js (JavaScript test)"
echo "  - test_naist_jdic.html (Interactive test page)"
echo ""
echo "To test the dictionary:"
echo "  1. Build MeCab WebAssembly: ./build.sh"
echo "  2. Start test server: cd test && python3 server.py"
echo "  3. Open: http://localhost:8000/test_naist_jdic.html"