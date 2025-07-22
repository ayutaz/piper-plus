#!/usr/bin/env node

/**
 * WebSocket-based TTS server for handling large ONNX models
 * This server loads the model once and streams audio to clients
 */

import { createServer } from 'http';
import { WebSocketServer } from 'ws';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { readFile } from 'fs/promises';
import express from 'express';
import cors from 'cors';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const app = express();
const port = process.env.PORT || 8084;

// Enable CORS for all origins in development
app.use(cors());
app.use(express.json());

// Serve static files
app.use('/mecab', express.static(join(__dirname, '../../mecab/dist')));
app.use('/openjtalk', express.static(join(__dirname, '../../openjtalk/dist')));
app.use('/models', express.static(join(__dirname, '../models')));
app.use('/test', express.static(join(__dirname, '../test')));

// Health check endpoint
app.get('/health', (req, res) => {
    res.json({ 
        status: 'ok', 
        timestamp: new Date().toISOString(),
        memory: process.memoryUsage()
    });
});

// Create HTTP server
const server = createServer(app);

// Create WebSocket server
const wss = new WebSocketServer({ server });

// Model state (to be implemented with actual ONNX loading)
let modelLoaded = false;
let modelInfo = null;

// Load model configuration
async function loadModelConfig() {
    try {
        const configPath = join(__dirname, '../models/ja_JP/ja_JP-test-medium.onnx.json');
        const configData = await readFile(configPath, 'utf8');
        modelInfo = JSON.parse(configData);
        console.log('Model config loaded:', modelInfo.key);
        return true;
    } catch (error) {
        console.error('Failed to load model config:', error);
        return false;
    }
}

// Handle WebSocket connections
wss.on('connection', (ws) => {
    console.log('New WebSocket connection established');
    
    // Send initial status
    ws.send(JSON.stringify({
        type: 'status',
        modelLoaded,
        modelInfo: modelInfo ? {
            language: modelInfo.language,
            quality: modelInfo.quality,
            sampleRate: modelInfo.audio?.sample_rate || 22050
        } : null
    }));
    
    ws.on('message', async (message) => {
        try {
            const data = JSON.parse(message);
            
            switch (data.type) {
                case 'synthesize':
                    await handleSynthesize(ws, data);
                    break;
                    
                case 'phonemes':
                    await handlePhonemes(ws, data);
                    break;
                    
                case 'ping':
                    ws.send(JSON.stringify({ type: 'pong' }));
                    break;
                    
                default:
                    ws.send(JSON.stringify({
                        type: 'error',
                        error: `Unknown message type: ${data.type}`
                    }));
            }
        } catch (error) {
            console.error('WebSocket message error:', error);
            ws.send(JSON.stringify({
                type: 'error',
                error: error.message
            }));
        }
    });
    
    ws.on('close', () => {
        console.log('WebSocket connection closed');
    });
    
    ws.on('error', (error) => {
        console.error('WebSocket error:', error);
    });
});

// Handle synthesis request
async function handleSynthesize(ws, data) {
    const { text, options = {} } = data;
    
    if (!text) {
        ws.send(JSON.stringify({
            type: 'error',
            error: 'No text provided'
        }));
        return;
    }
    
    // Send progress updates
    ws.send(JSON.stringify({
        type: 'progress',
        stage: 'phonemes',
        percent: 20
    }));
    
    // Simulate phoneme processing
    const phonemes = simulatePhonemeConversion(text);
    
    ws.send(JSON.stringify({
        type: 'phonemes',
        phonemes: phonemes.display,
        phonemeIds: phonemes.ids
    }));
    
    ws.send(JSON.stringify({
        type: 'progress',
        stage: 'synthesis',
        percent: 50
    }));
    
    // Simulate audio generation (in production, this would use ONNX)
    const audioData = simulateAudioGeneration(phonemes.ids);
    
    // Stream audio in chunks
    const chunkSize = 8192; // 8KB chunks
    let offset = 0;
    
    while (offset < audioData.length) {
        const chunk = audioData.slice(offset, offset + chunkSize);
        
        ws.send(JSON.stringify({
            type: 'audio_chunk',
            data: Array.from(chunk), // Convert to array for JSON
            offset,
            total: audioData.length,
            sampleRate: 22050
        }));
        
        offset += chunkSize;
        
        // Small delay to simulate streaming
        await new Promise(resolve => setTimeout(resolve, 10));
    }
    
    ws.send(JSON.stringify({
        type: 'complete',
        duration: audioData.length / 22050,
        sampleCount: audioData.length
    }));
}

// Handle phoneme-only request
async function handlePhonemes(ws, data) {
    const { text } = data;
    
    if (!text) {
        ws.send(JSON.stringify({
            type: 'error',
            error: 'No text provided'
        }));
        return;
    }
    
    const phonemes = simulatePhonemeConversion(text);
    
    ws.send(JSON.stringify({
        type: 'phonemes',
        phonemes: phonemes.display,
        phonemeIds: phonemes.ids
    }));
}

// Simulate phoneme conversion (placeholder)
function simulatePhonemeConversion(text) {
    // This is a simplified simulation
    // In production, this would use MeCab + OpenJTalk
    
    const phonemeMap = {
        'こんにちは': 'k o N n i ch i h a',
        '世界': 's e k a i',
        '今日': 'ky o u',
        'は': 'h a',
        '良い': 'y o i',
        '天気': 't e N k i',
        'です': 'd e s u',
        'ね': 'n e',
        '。': 'pau',
        '！': 'pau',
        '、': 'pau'
    };
    
    let displayPhonemes = '';
    let phonemeIds = [1]; // Start token
    
    // Simple tokenization
    const tokens = text.split(/([。！、])/);
    
    for (const token of tokens) {
        if (phonemeMap[token]) {
            displayPhonemes += phonemeMap[token] + ' ';
            // Generate fake IDs
            const phonemes = phonemeMap[token].split(' ');
            for (const p of phonemes) {
                phonemeIds.push(Math.floor(Math.random() * 50) + 3);
            }
        } else if (token && !token.match(/[。！、]/)) {
            // Unknown token - generate random phonemes
            displayPhonemes += 'a i u e o ';
            phonemeIds.push(...[3, 4, 5, 6, 7]);
        }
    }
    
    phonemeIds.push(2); // End token
    
    return {
        display: displayPhonemes.trim(),
        ids: phonemeIds
    };
}

// Simulate audio generation (placeholder)
function simulateAudioGeneration(phonemeIds) {
    // Generate sine wave as placeholder audio
    const sampleRate = 22050;
    const duration = 0.1 * phonemeIds.length; // 0.1s per phoneme
    const samples = Math.floor(sampleRate * duration);
    const audioData = new Float32Array(samples);
    
    // Generate a simple tone
    const frequency = 440; // A4
    for (let i = 0; i < samples; i++) {
        audioData[i] = 0.3 * Math.sin(2 * Math.PI * frequency * i / sampleRate);
    }
    
    return audioData;
}

// Initialize server
async function initialize() {
    console.log('Initializing TTS server...');
    
    // Load model configuration
    modelLoaded = await loadModelConfig();
    
    // Start server
    server.listen(port, () => {
        console.log(`TTS server running on http://localhost:${port}`);
        console.log(`WebSocket endpoint: ws://localhost:${port}`);
        console.log('');
        console.log('Available endpoints:');
        console.log(`  - Health check: http://localhost:${port}/health`);
        console.log(`  - Test page: http://localhost:${port}/test/websocket-demo.html`);
        console.log(`  - WebSocket: ws://localhost:${port}`);
    });
}

// Handle graceful shutdown
process.on('SIGINT', () => {
    console.log('\nShutting down server...');
    server.close(() => {
        console.log('Server closed');
        process.exit(0);
    });
});

// Start the server
initialize();