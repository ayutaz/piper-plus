/**
 * Tests for OpenJTalk-Piper Integration
 * Run with Node.js: node test-openjtalk-integration.js
 */

import { strict as assert } from 'assert';
import { describe, it, beforeEach } from 'node:test';

// Mock ONNX Runtime for testing
global.ort = {
    InferenceSession: {
        create: async () => ({
            inputNames: ['input', 'input_lengths', 'scales'],
            outputNames: ['output'],
            run: async (feeds) => ({
                output: {
                    data: new Float32Array(22050), // 1 second of audio at 22050Hz
                    dims: [1, 22050]
                }
            }),
            release: () => {}
        })
    },
    Tensor: class {
        constructor(type, data, dims) {
            this.type = type;
            this.data = data;
            this.dims = dims;
        }
    }
};

// Import after setting up mocks
import OpenJTalkPiperTTS from './openjtalk-piper-integration.js';

describe('OpenJTalkPiperTTS', () => {
    let tts;
    
    beforeEach(() => {
        tts = new OpenJTalkPiperTTS();
    });
    
    describe('Phoneme Extraction', () => {
        it('should extract phonemes from OpenJTalk labels', () => {
            const labels = `
                xx^xx-sil+k=o/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx/D:xx+xx_xx/E:xx_xx!xx_xx-xx/F:xx_xx#xx_xx@xx_xx|xx_xx/G:xx_xx%xx_xx_xx/H:xx_xx/I:xx-xx@xx+xx&xx-xx|xx+xx/J:xx_xx/K:xx+xx-xx
                xx^sil-k+o=N/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx/D:xx+xx_xx/E:xx_xx!xx_xx-xx/F:xx_xx#xx_xx@xx_xx|xx_xx/G:xx_xx%xx_xx_xx/H:xx_xx/I:xx-xx@xx+xx&xx-xx|xx+xx/J:xx_xx/K:xx+xx-xx
                sil^k-o+N=n/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx/D:xx+xx_xx/E:xx_xx!xx_xx-xx/F:xx_xx#xx_xx@xx_xx|xx_xx/G:xx_xx%xx_xx_xx/H:xx_xx/I:xx-xx@xx+xx&xx-xx|xx+xx/J:xx_xx/K:xx+xx-xx
                k^o-N+n=i/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx/D:xx+xx_xx/E:xx_xx!xx_xx-xx/F:xx_xx#xx_xx@xx_xx|xx_xx/G:xx_xx%xx_xx_xx/H:xx_xx/I:xx-xx@xx+xx&xx-xx|xx+xx/J:xx_xx/K:xx+xx-xx
                o^N-n+i=ch/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx/D:xx+xx_xx/E:xx_xx!xx_xx-xx/F:xx_xx#xx_xx@xx_xx|xx_xx/G:xx_xx%xx_xx_xx/H:xx_xx/I:xx-xx@xx+xx&xx-xx|xx+xx/J:xx_xx/K:xx+xx-xx
                N^n-i+ch=i/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx/D:xx+xx_xx/E:xx_xx!xx_xx-xx/F:xx_xx#xx_xx@xx_xx|xx_xx/G:xx_xx%xx_xx_xx/H:xx_xx/I:xx-xx@xx+xx&xx-xx|xx+xx/J:xx_xx/K:xx+xx-xx
                n^i-ch+i=w/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx/D:xx+xx_xx/E:xx_xx!xx_xx-xx/F:xx_xx#xx_xx@xx_xx|xx_xx/G:xx_xx%xx_xx_xx/H:xx_xx/I:xx-xx@xx+xx&xx-xx|xx+xx/J:xx_xx/K:xx+xx-xx
                i^ch-i+w=a/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx/D:xx+xx_xx/E:xx_xx!xx_xx-xx/F:xx_xx#xx_xx@xx_xx|xx_xx/G:xx_xx%xx_xx_xx/H:xx_xx/I:xx-xx@xx+xx&xx-xx|xx+xx/J:xx_xx/K:xx+xx-xx
                ch^i-w+a=sil/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx/D:xx+xx_xx/E:xx_xx!xx_xx-xx/F:xx_xx#xx_xx@xx_xx|xx_xx/G:xx_xx%xx_xx_xx/H:xx_xx/I:xx-xx@xx+xx&xx-xx|xx+xx/J:xx_xx/K:xx+xx-xx
                i^w-a+sil=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx/D:xx+xx_xx/E:xx_xx!xx_xx-xx/F:xx_xx#xx_xx@xx_xx|xx_xx/G:xx_xx%xx_xx_xx/H:xx_xx/I:xx-xx@xx+xx&xx-xx|xx+xx/J:xx_xx/K:xx+xx-xx
            `.trim();
            
            const phonemes = tts.extractPhonemes(labels);
            
            assert.deepEqual(phonemes, ['^', 'k', 'o', 'N', 'n', 'i', 'ch', 'i', 'w', 'a', '$']);
        });
        
        it('should handle empty labels', () => {
            const phonemes = tts.extractPhonemes('');
            assert.deepEqual(phonemes, ['^', '$']);
        });
        
        it('should skip sil phonemes', () => {
            const labels = 'xx^xx-sil+k=o/A:xx\nxx^sil-k+o=N/A:xx\nsil^k-o+N=n/A:xx';
            const phonemes = tts.extractPhonemes(labels);
            assert.deepEqual(phonemes, ['^', 'k', 'o', '$']);
        });
    });
    
    describe('Phoneme to ID Conversion', () => {
        beforeEach(() => {
            // Mock phoneme ID map
            tts.phonemeIdMap = {
                '_': [0], '^': [1], '$': [2], '?': [3], '#': [4],
                'a': [7], 'i': [8], 'u': [9], 'e': [10], 'o': [11],
                'k': [25], 'g': [28], 'n': [50], 'm': [52], 'r': [54], 'w': [56],
                'N': [22], 'q': [24],
                '\ue000': [17], '\ue001': [18], '\ue002': [19], '\ue003': [20], '\ue004': [21],
                '\ue005': [23], '\ue006': [26], '\ue00e': [39], '\ue00f': [40]
            };
        });
        
        it('should convert single-character phonemes', () => {
            const phonemes = ['k', 'o', 'n', 'i', 'w', 'a'];
            const ids = tts.phonemesToIds(phonemes);
            assert.deepEqual(ids, [25, 11, 50, 8, 56, 7]);
        });
        
        it('should convert multi-character phonemes', () => {
            const phonemes = ['k', 'a:', 'ts', 'u'];
            const ids = tts.phonemesToIds(phonemes);
            assert.deepEqual(ids, [25, 17, 39, 9]); // a: -> \ue000 -> 17, ts -> \ue00e -> 39
        });
        
        it('should handle special phonemes', () => {
            const phonemes = ['^', 'pau', 'cl', '$'];
            const ids = tts.phonemesToIds(phonemes);
            assert.deepEqual(ids, [1, 4, 23, 2]); // pau -> #, cl -> \ue005
        });
        
        it('should handle unknown phonemes with padding', () => {
            const phonemes = ['k', 'unknown', 'a'];
            const ids = tts.phonemesToIds(phonemes);
            assert.deepEqual(ids, [25, 0, 7]); // unknown -> 0 (padding)
        });
    });
    
    describe('WAV Generation', () => {
        it('should create valid WAV header', () => {
            const audioData = new Float32Array([0.1, 0.2, -0.1, -0.2]);
            const sampleRate = 22050;
            
            const wavBlob = tts.createWAV(audioData, sampleRate);
            
            assert(wavBlob instanceof Blob);
            assert.equal(wavBlob.type, 'audio/wav');
            // WAV header is 44 bytes + audio data (4 samples * 2 bytes)
            assert.equal(wavBlob.size, 44 + 8);
        });
        
        it('should handle empty audio data', () => {
            const audioData = new Float32Array(0);
            const wavBlob = tts.createWAV(audioData, 22050);
            
            assert(wavBlob instanceof Blob);
            assert.equal(wavBlob.size, 44); // Just header
        });
    });
    
    describe('Float to PCM Conversion', () => {
        it('should convert float32 to int16 PCM', () => {
            const float32 = new Float32Array([0.0, 0.5, -0.5, 1.0, -1.0]);
            const int16 = tts.floatTo16BitPCM(float32);
            
            assert(int16 instanceof Int16Array);
            assert.equal(int16.length, 5);
            assert.equal(int16[0], 0);
            assert.equal(int16[1], 16383); // 0.5 * 0x7FFF
            assert.equal(int16[2], -16384); // -0.5 * 0x8000
            assert.equal(int16[3], 32767); // 1.0 * 0x7FFF
            assert.equal(int16[4], -32768); // -1.0 * 0x8000
        });
        
        it('should clamp values outside -1 to 1 range', () => {
            const float32 = new Float32Array([2.0, -2.0]);
            const int16 = tts.floatTo16BitPCM(float32);
            
            assert.equal(int16[0], 32767); // Clamped to 1.0
            assert.equal(int16[1], -32768); // Clamped to -1.0
        });
    });
    
    describe('Multi-character Phoneme Mapping', () => {
        beforeEach(() => {
            tts.phonemeIdMap = {
                '\ue000': [17], // a:
                '\ue005': [23], // cl
                '\ue006': [26], // ky
                '\ue00e': [39], // ts
                '\ue00f': [40], // ch
                '#': [4],       // pau
                '_': [0]        // sil
            };
        });
        
        it('should map all Japanese special phonemes correctly', () => {
            const testCases = [
                { phoneme: 'a:', expected: [17] },
                { phoneme: 'cl', expected: [23] },
                { phoneme: 'ky', expected: [26] },
                { phoneme: 'ch', expected: [40] },
                { phoneme: 'ts', expected: [39] },
                { phoneme: 'pau', expected: [4] },
                { phoneme: 'sil', expected: [0] }
            ];
            
            testCases.forEach(({ phoneme, expected }) => {
                const ids = tts.phonemesToIds([phoneme]);
                assert.deepEqual(ids, expected, `Failed for phoneme: ${phoneme}`);
            });
        });
    });
});

// Run tests
console.log('Running OpenJTalk-Piper Integration Tests...\n');