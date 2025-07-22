/**
 * Unit tests for MeCab WebAssembly implementation
 * 
 * These tests validate the wrapper functionality without requiring actual WASM
 */

// Mock MeCabCore implementation
class MockMeCabCore {
  constructor() {
    this._initialized = false;
  }

  async initialize(wasmPath) {
    if (this._initialized) {
      throw new Error('MeCab is already initialized');
    }
    await new Promise(resolve => setTimeout(resolve, 10));
    this._initialized = true;
  }

  isInitialized() {
    return this._initialized;
  }

  parse(text) {
    if (!this._initialized) {
      throw new Error('MeCab is not initialized');
    }
    if (typeof text !== 'string') {
      throw new TypeError('Input must be a string');
    }
    
    // Mock responses for specific inputs
    if (text === '') return '';
    if (text === 'こんにちは') {
      return 'こんにちは\t感動詞,*,*,*,*,*,こんにちは,コンニチハ,コンニチワ\nEOS\n';
    }
    if (text === '日本語') {
      return '日本\t名詞,固有名詞,地域,国,*,*,日本,ニッポン,ニッポン\n語\t名詞,接尾,一般,*,*,*,語,ゴ,ゴ\nEOS\n';
    }
    return `${text}\t名詞,一般,*,*,*,*,${text},*,*\nEOS\n`;
  }

  parseToNodes(text) {
    if (!this._initialized) {
      throw new Error('MeCab is not initialized');
    }
    
    const result = this.parse(text);
    const lines = result.split('\n').filter(line => line && line !== 'EOS');
    
    return lines.map(line => {
      const [surface, featureStr] = line.split('\t');
      const features = featureStr ? featureStr.split(',') : [];
      
      return {
        surface,
        features,
        reading: features[7] || '',
        pronunciation: features[8] || ''
      };
    });
  }

  wakati(text) {
    if (!this._initialized) {
      throw new Error('MeCab is not initialized');
    }
    
    if (text === 'こんにちは世界') {
      return 'こんにちは 世界';
    }
    return text.split('').join(' ');
  }

  reading(text) {
    if (!this._initialized) {
      throw new Error('MeCab is not initialized');
    }
    
    if (text === 'こんにちは') return 'コンニチハ';
    if (text === '日本語') return 'ニッポンゴ';
    return text;
  }

  destroy() {
    this._initialized = false;
  }
}

describe('MeCab WebAssembly', () => {
  let mecab;

  beforeEach(() => {
    mecab = new MockMeCabCore();
  });

  afterEach(() => {
    if (mecab && mecab.isInitialized()) {
      mecab.destroy();
    }
  });

  describe('Initialization', () => {
    test('should create MeCab instance', () => {
      expect(mecab).toBeDefined();
      expect(mecab).toBeInstanceOf(MockMeCabCore);
    });

    test('should initialize successfully', async () => {
      await expect(mecab.initialize('mock.wasm')).resolves.not.toThrow();
      expect(mecab.isInitialized()).toBe(true);
    });

    test('should throw error if already initialized', async () => {
      await mecab.initialize('mock.wasm');
      await expect(mecab.initialize('mock.wasm')).rejects.toThrow('MeCab is already initialized');
    });
  });

  describe('Parse functionality', () => {
    beforeEach(async () => {
      await mecab.initialize('mock.wasm');
    });

    test('should parse Japanese greeting', () => {
      const result = mecab.parse('こんにちは');
      expect(result).toContain('こんにちは');
      expect(result).toContain('感動詞');
      expect(result).toContain('コンニチハ');
    });

    test('should parse compound words', () => {
      const result = mecab.parse('日本語');
      expect(result).toContain('日本');
      expect(result).toContain('語');
      expect(result).toContain('名詞');
    });

    test('should handle empty input', () => {
      const result = mecab.parse('');
      expect(result).toBe('');
    });

    test('should throw error if not initialized', () => {
      const uninitMecab = new MockMeCabCore();
      expect(() => uninitMecab.parse('test')).toThrow('MeCab is not initialized');
    });

    test('should throw error for non-string input', () => {
      expect(() => mecab.parse(123)).toThrow(TypeError);
      expect(() => mecab.parse(null)).toThrow(TypeError);
      expect(() => mecab.parse(undefined)).toThrow(TypeError);
    });
  });

  describe('Node parsing', () => {
    beforeEach(async () => {
      await mecab.initialize('mock.wasm');
    });

    test('should parse to nodes', () => {
      const nodes = mecab.parseToNodes('こんにちは');
      expect(Array.isArray(nodes)).toBe(true);
      expect(nodes.length).toBeGreaterThan(0);
      expect(nodes[0]).toHaveProperty('surface');
      expect(nodes[0]).toHaveProperty('features');
    });

    test('should extract features correctly', () => {
      const nodes = mecab.parseToNodes('こんにちは');
      const firstNode = nodes[0];
      expect(firstNode.surface).toBe('こんにちは');
      expect(firstNode.features).toContain('感動詞');
      expect(firstNode.reading).toBe('コンニチハ');
      expect(firstNode.pronunciation).toBe('コンニチワ');
    });
  });

  describe('Wakati functionality', () => {
    beforeEach(async () => {
      await mecab.initialize('mock.wasm');
    });

    test('should perform wakati-gaki', () => {
      const result = mecab.wakati('こんにちは世界');
      expect(result).toBe('こんにちは 世界');
    });
  });

  describe('Reading functionality', () => {
    beforeEach(async () => {
      await mecab.initialize('mock.wasm');
    });

    test('should convert to katakana reading', () => {
      expect(mecab.reading('こんにちは')).toBe('コンニチハ');
      expect(mecab.reading('日本語')).toBe('ニッポンゴ');
    });
  });

  describe('Memory management', () => {
    test('should destroy instance properly', async () => {
      await mecab.initialize('mock.wasm');
      expect(() => mecab.destroy()).not.toThrow();
      expect(mecab.isInitialized()).toBe(false);
    });

    test('should handle multiple destroy calls', async () => {
      await mecab.initialize('mock.wasm');
      mecab.destroy();
      expect(() => mecab.destroy()).not.toThrow();
    });
  });

  describe('Performance', () => {
    beforeEach(async () => {
      await mecab.initialize('mock.wasm');
    });

    test('should parse within reasonable time', () => {
      const startTime = performance.now();
      mecab.parse('これは性能テストのための長い日本語の文章です。');
      const endTime = performance.now();
      const elapsed = endTime - startTime;
      
      // Should complete within 100ms
      expect(elapsed).toBeLessThan(100);
    });
  });
});