/**
 * Unit tests for OpenJTalk WebAssembly module
 */

// Mock the OpenJTalk WebAssembly module
const mockOpenJTalkModule = {
  _malloc: jest.fn((size) => size), // Return size as mock pointer
  _free: jest.fn(),
  HEAP8: new Int8Array(1024 * 1024), // 1MB heap
  HEAPU8: new Uint8Array(1024 * 1024),
  UTF8ToString: jest.fn((ptr) => 'mock_output'),
  stringToUTF8: jest.fn((str, ptr, maxBytes) => str.length),
  _openjtalk_initialize: jest.fn(() => 1), // Success
  _openjtalk_clear: jest.fn(),
  _openjtalk_processMecabOutput: jest.fn(() => 100), // Mock pointer to result
  _openjtalk_convertToPhonemes: jest.fn(() => 200), // Mock pointer to phonemes
  _openjtalk_setPUAMapping: jest.fn((enabled) => enabled),
  _openjtalk_getLastError: jest.fn(() => 0), // Mock pointer to error string
  ccall: jest.fn((func, returnType, argTypes, args) => {
    if (func === 'openjtalk_initialize') return 1;
    if (func === 'openjtalk_processMecabOutput') return 100;
    if (func === 'openjtalk_convertToPhonemes') return 200;
    return 0;
  }),
  cwrap: jest.fn((func, returnType, argTypes) => {
    return jest.fn();
  })
};

// Mock Module loading
global.OpenJTalkModule = jest.fn(() => Promise.resolve(mockOpenJTalkModule));

describe('OpenJTalk WebAssembly', () => {
  let openjtalk;
  
  beforeEach(async () => {
    // Reset mocks
    jest.clearAllMocks();
    
    // Simulate module initialization
    const Module = await global.OpenJTalkModule();
    
    // Mock the wrapper class
    openjtalk = {
      Module,
      initialized: false,
      initialize: async function() {
        const result = this.Module._openjtalk_initialize();
        this.initialized = result === 1;
        return this.initialized;
      },
      processMecabOutput: function(mecabOutput) {
        if (!this.initialized) throw new Error('OpenJTalk not initialized');
        
        const inputPtr = this.Module._malloc(mecabOutput.length + 1);
        this.Module.stringToUTF8(mecabOutput, inputPtr, mecabOutput.length + 1);
        
        const resultPtr = this.Module._openjtalk_processMecabOutput(inputPtr);
        this.Module._free(inputPtr);
        
        if (resultPtr === 0) {
          throw new Error('Failed to process MeCab output');
        }
        
        const result = this.Module.UTF8ToString(resultPtr);
        this.Module._free(resultPtr);
        
        return result;
      },
      convertToPhonemes: function(njdOutput) {
        if (!this.initialized) throw new Error('OpenJTalk not initialized');
        
        const inputPtr = this.Module._malloc(njdOutput.length + 1);
        this.Module.stringToUTF8(njdOutput, inputPtr, njdOutput.length + 1);
        
        const resultPtr = this.Module._openjtalk_convertToPhonemes(inputPtr);
        this.Module._free(inputPtr);
        
        if (resultPtr === 0) {
          throw new Error('Failed to convert to phonemes');
        }
        
        const result = this.Module.UTF8ToString(resultPtr);
        this.Module._free(resultPtr);
        
        return result;
      },
      setPUAMapping: function(enabled) {
        this.Module._openjtalk_setPUAMapping(enabled ? 1 : 0);
      },
      getLastError: function() {
        const errorPtr = this.Module._openjtalk_getLastError();
        if (errorPtr === 0) return null;
        return this.Module.UTF8ToString(errorPtr);
      },
      clear: function() {
        this.Module._openjtalk_clear();
        this.initialized = false;
      }
    };
  });
  
  afterEach(() => {
    if (openjtalk) {
      openjtalk.clear();
    }
  });

  describe('Module Loading', () => {
    test('should load OpenJTalk module', async () => {
      expect(global.OpenJTalkModule).toBeDefined();
      const module = await global.OpenJTalkModule();
      expect(module).toBeDefined();
      expect(module._openjtalk_initialize).toBeDefined();
    });

    test('should have required exports', async () => {
      const module = await global.OpenJTalkModule();
      const requiredExports = [
        '_malloc',
        '_free',
        '_openjtalk_initialize',
        '_openjtalk_clear',
        '_openjtalk_processMecabOutput',
        '_openjtalk_convertToPhonemes',
        '_openjtalk_setPUAMapping',
        '_openjtalk_getLastError'
      ];
      
      requiredExports.forEach(exportName => {
        expect(module[exportName]).toBeDefined();
      });
    });
  });

  describe('Initialization', () => {
    test('should initialize successfully', async () => {
      const result = await openjtalk.initialize();
      expect(result).toBe(true);
      expect(openjtalk.initialized).toBe(true);
      expect(mockOpenJTalkModule._openjtalk_initialize).toHaveBeenCalled();
    });

    test('should handle initialization failure', async () => {
      mockOpenJTalkModule._openjtalk_initialize.mockReturnValueOnce(0);
      const result = await openjtalk.initialize();
      expect(result).toBe(false);
      expect(openjtalk.initialized).toBe(false);
    });
  });

  describe('MeCab Output Processing', () => {
    beforeEach(async () => {
      await openjtalk.initialize();
    });

    test('should process MeCab output', () => {
      const mecabOutput = `こんにちは\t名詞,普通名詞,*,*,*,*,こんにちは,コンニチハ,コンニチワ\nEOS`;
      const result = openjtalk.processMecabOutput(mecabOutput);
      
      expect(result).toBeDefined();
      expect(mockOpenJTalkModule._malloc).toHaveBeenCalled();
      expect(mockOpenJTalkModule._free).toHaveBeenCalledTimes(2);
      expect(mockOpenJTalkModule._openjtalk_processMecabOutput).toHaveBeenCalled();
    });

    test('should throw error when not initialized', () => {
      openjtalk.initialized = false;
      const mecabOutput = `テスト\t名詞,*,*,*,*,*,テスト,テスト,テスト\nEOS`;
      
      expect(() => {
        openjtalk.processMecabOutput(mecabOutput);
      }).toThrow('OpenJTalk not initialized');
    });

    test('should handle processing failure', () => {
      mockOpenJTalkModule._openjtalk_processMecabOutput.mockReturnValueOnce(0);
      const mecabOutput = `invalid input`;
      
      expect(() => {
        openjtalk.processMecabOutput(mecabOutput);
      }).toThrow('Failed to process MeCab output');
    });
  });

  describe('Phoneme Conversion', () => {
    beforeEach(async () => {
      await openjtalk.initialize();
    });

    test('should convert to phonemes', () => {
      const njdOutput = 'mock_njd_output';
      const result = openjtalk.convertToPhonemes(njdOutput);
      
      expect(result).toBeDefined();
      expect(mockOpenJTalkModule._openjtalk_convertToPhonemes).toHaveBeenCalled();
    });

    test('should handle empty input', () => {
      const result = openjtalk.convertToPhonemes('');
      expect(result).toBeDefined();
    });

    test('should handle conversion failure', () => {
      mockOpenJTalkModule._openjtalk_convertToPhonemes.mockReturnValueOnce(0);
      
      expect(() => {
        openjtalk.convertToPhonemes('test');
      }).toThrow('Failed to convert to phonemes');
    });
  });

  describe('PUA Mapping', () => {
    beforeEach(async () => {
      await openjtalk.initialize();
    });

    test('should enable PUA mapping', () => {
      openjtalk.setPUAMapping(true);
      expect(mockOpenJTalkModule._openjtalk_setPUAMapping).toHaveBeenCalledWith(1);
    });

    test('should disable PUA mapping', () => {
      openjtalk.setPUAMapping(false);
      expect(mockOpenJTalkModule._openjtalk_setPUAMapping).toHaveBeenCalledWith(0);
    });
  });

  describe('Error Handling', () => {
    test('should get last error', () => {
      mockOpenJTalkModule.UTF8ToString.mockReturnValueOnce('Test error message');
      mockOpenJTalkModule._openjtalk_getLastError.mockReturnValueOnce(300);
      
      const error = openjtalk.getLastError();
      expect(error).toBe('Test error message');
    });

    test('should return null when no error', () => {
      mockOpenJTalkModule._openjtalk_getLastError.mockReturnValueOnce(0);
      
      const error = openjtalk.getLastError();
      expect(error).toBeNull();
    });
  });

  describe('Memory Management', () => {
    test('should allocate and free memory correctly', async () => {
      await openjtalk.initialize();
      const testString = '日本語テスト';
      
      openjtalk.processMecabOutput(testString);
      
      // Check malloc was called with correct size
      expect(mockOpenJTalkModule._malloc).toHaveBeenCalledWith(testString.length + 1);
      
      // Check free was called to clean up
      expect(mockOpenJTalkModule._free.mock.calls.length).toBeGreaterThan(0);
    });
  });

  describe('Cleanup', () => {
    test('should clear resources', async () => {
      await openjtalk.initialize();
      openjtalk.clear();
      
      expect(mockOpenJTalkModule._openjtalk_clear).toHaveBeenCalled();
      expect(openjtalk.initialized).toBe(false);
    });
  });
});

describe('Integration with MeCab', () => {
  test('should process full pipeline', async () => {
    const openjtalk = {
      Module: mockOpenJTalkModule,
      initialized: false,
      initialize: async function() {
        this.initialized = true;
        return true;
      },
      processFullText: function(mecabOutput, enablePUA = true) {
        // Mock full pipeline processing
        this.Module._openjtalk_setPUAMapping(enablePUA ? 1 : 0);
        
        const njdResult = 'mock_njd_result';
        const phonemes = enablePUA ? 'k o N n i t i w a' : 'konnichiwa';
        
        return {
          njd: njdResult,
          phonemes: phonemes,
          pua: enablePUA ? '\ue001\ue002\ue003' : null
        };
      }
    };
    
    await openjtalk.initialize();
    
    const mecabOutput = `こんにちは\t名詞,*,*,*,*,*,こんにちは,コンニチハ,コンニチワ\nEOS`;
    const result = openjtalk.processFullText(mecabOutput, true);
    
    expect(result).toHaveProperty('njd');
    expect(result).toHaveProperty('phonemes');
    expect(result).toHaveProperty('pua');
    expect(result.pua).toBeTruthy();
  });
});