/**
 * OpenJTalk WebAssembly API for browsers
 */

export class OpenJTalkWeb {
  constructor() {
    this.module = null;
    this.initialized = false;
    this.dictLoaded = false;
    this.voiceLoaded = false;
  }

  /**
   * Initialize OpenJTalk with dictionary and voice data
   * @param {Object} config - Configuration object
   * @param {string} config.wasmUrl - URL to the WASM file
   * @param {string} config.dictUrl - URL to the dictionary archive
   * @param {string} config.voiceUrl - URL to the HTS voice file
   * @returns {Promise<void>}
   */
  async initialize(config = {}) {
    try {
      console.log('Initializing OpenJTalk WebAssembly...');
      
      // Load the WebAssembly module
      const wasmUrl = config.wasmUrl || './openjtalk.wasm';
      const OpenJTalkModule = await import(config.jsUrl || './openjtalk.js');
      
      this.module = await OpenJTalkModule.default({
        locateFile: (path) => {
          if (path.endsWith('.wasm')) {
            return wasmUrl;
          }
          return path;
        }
      });
      
      console.log('WebAssembly module loaded');
      
      // Create virtual file system directories
      this.module.FS.mkdir('/tmp');
      this.module.FS.mkdir('/dict');
      this.module.FS.mkdir('/voice');
      
      // Load dictionary
      if (config.dictUrl) {
        await this.loadDictionary(config.dictUrl);
      }
      
      // Load voice
      if (config.voiceUrl) {
        await this.loadVoice(config.voiceUrl);
      }
      
      // Initialize OpenJTalk
      const result = this.module.ccall(
        'openjtalk_initialize',
        'number',
        ['string', 'string'],
        ['/dict', '/voice/voice.htsvoice']
      );
      
      if (result !== 0) {
        throw new Error(`OpenJTalk initialization failed with code: ${result}`);
      }
      
      this.initialized = true;
      console.log('OpenJTalk initialized successfully');
      
    } catch (error) {
      console.error('Failed to initialize OpenJTalk:', error);
      throw error;
    }
  }

  /**
   * Load dictionary files from URL
   * @param {string} url - Dictionary archive URL
   * @returns {Promise<void>}
   */
  async loadDictionary(url) {
    console.log('Loading dictionary from:', url);
    
    try {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Failed to fetch dictionary: ${response.statusText}`);
      }
      
      const arrayBuffer = await response.arrayBuffer();
      const data = new Uint8Array(arrayBuffer);
      
      // For now, assume the dictionary is pre-extracted
      // In production, we would decompress and extract files here
      const dictFiles = [
        'char.bin', 'matrix.bin', 'sys.dic', 'unk.dic',
        'left-id.def', 'pos-id.def', 'rewrite.def', 'right-id.def'
      ];
      
      // TODO: Implement proper dictionary extraction
      // For MVP, we'll need to serve individual files
      console.warn('Dictionary loading not fully implemented - need extraction logic');
      
      this.dictLoaded = true;
      
    } catch (error) {
      console.error('Failed to load dictionary:', error);
      throw error;
    }
  }

  /**
   * Load HTS voice file from URL
   * @param {string} url - Voice file URL
   * @returns {Promise<void>}
   */
  async loadVoice(url) {
    console.log('Loading voice from:', url);
    
    try {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Failed to fetch voice: ${response.statusText}`);
      }
      
      const arrayBuffer = await response.arrayBuffer();
      const data = new Uint8Array(arrayBuffer);
      
      // Write voice file to virtual file system
      this.module.FS.writeFile('/voice/voice.htsvoice', data);
      
      this.voiceLoaded = true;
      console.log('Voice loaded successfully');
      
    } catch (error) {
      console.error('Failed to load voice:', error);
      throw error;
    }
  }

  /**
   * Convert text to phoneme labels
   * @param {string} text - Japanese text to convert
   * @returns {Promise<string>} Phoneme labels
   */
  async textToPhonemes(text) {
    if (!this.initialized) {
      throw new Error('OpenJTalk not initialized');
    }
    
    if (!text || text.trim() === '') {
      return '';
    }
    
    try {
      // Call the synthesis labels function
      const labelsPtr = this.module.ccall(
        'openjtalk_synthesis_labels',
        'number',
        ['string'],
        [text]
      );
      
      if (!labelsPtr) {
        throw new Error('Failed to generate labels');
      }
      
      // Convert pointer to string
      const labels = this.module.UTF8ToString(labelsPtr);
      
      // Free the allocated string
      this.module.ccall(
        'openjtalk_free_string',
        null,
        ['number'],
        [labelsPtr]
      );
      
      return labels;
      
    } catch (error) {
      console.error('Failed to convert text to phonemes:', error);
      throw error;
    }
  }

  /**
   * Extract phonemes from labels
   * @param {string} labels - Full context labels from OpenJTalk
   * @returns {string[]} Array of phonemes
   */
  extractPhonemes(labels) {
    const lines = labels.split('\n').filter(line => line.trim());
    const phonemes = [];
    
    for (const line of lines) {
      // Extract phoneme from full context label
      // Format: xx^xx-phoneme+xx=xx/A:...
      const match = line.match(/\-([^+]+)\+/);
      if (match && match[1] !== 'sil') {
        phonemes.push(match[1]);
      }
    }
    
    return phonemes;
  }

  /**
   * Clean up resources
   */
  destroy() {
    if (this.initialized) {
      this.module.ccall('openjtalk_clear', null, [], []);
      this.initialized = false;
    }
    this.module = null;
  }
}