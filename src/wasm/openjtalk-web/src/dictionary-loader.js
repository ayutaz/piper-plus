/**
 * Dictionary loader for OpenJTalk WebAssembly
 * Handles loading and extracting dictionary files for browser use
 */

export class DictionaryLoader {
  constructor(module, { cacheManager = null, dictVersion = 'v1.0' } = {}) {
    this.module = module;
    this.cacheManager = cacheManager;
    this.dictVersion = dictVersion;
    this.dictFiles = [
      'char.bin',
      'matrix.bin', 
      'sys.dic',
      'unk.dic',
      'left-id.def',
      'pos-id.def',
      'rewrite.def',
      'right-id.def'
    ];
  }

  /**
   * Load dictionary from a tar.gz archive
   * @param {string} url - URL to dictionary archive
   * @returns {Promise<void>}
   */
  async loadFromArchive(url) {
    console.log('Loading dictionary archive from:', url);

    try {
      const fetchArchive = async () => {
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`Failed to fetch dictionary: ${response.statusText}`);
        }
        return await response.arrayBuffer();
      };

      if (this.cacheManager) {
        await this.cacheManager.getOrFetch(
          'dict/archive',
          this.dictVersion,
          fetchArchive
        );
      } else {
        await fetchArchive();
      }

      // For MVP, we'll load individual files
      // TODO: Implement tar.gz extraction in browser
      console.warn('Archive extraction not implemented - using individual files');

      // Load individual dictionary files instead
      await this.loadIndividualFiles(url.replace('/dict.tar.gz', '/dict'));

    } catch (error) {
      console.error('Failed to load dictionary archive:', error);
      throw error;
    }
  }

  /**
   * Load individual dictionary files
   * @param {string} baseUrl - Base URL for dictionary files
   * @returns {Promise<void>}
   */
  async loadIndividualFiles(baseUrl) {
    console.log('Loading individual dictionary files from:', baseUrl);
    
    // Ensure directory exists
    try {
      this.module.FS.mkdir('/dict');
    } catch (e) {
      // Directory might already exist
    }

    // Load each dictionary file
    const loadPromises = this.dictFiles.map(async (filename) => {
      try {
        const url = `${baseUrl}/${filename}`;

        const fetchFile = async () => {
          const response = await fetch(url);
          if (!response.ok) {
            throw new Error(`Failed to load ${filename}: ${response.statusText}`);
          }
          return await response.arrayBuffer();
        };

        let data;
        if (this.cacheManager) {
          const cacheKey = `dict/${filename}`;
          data = await this.cacheManager.getOrFetch(
            cacheKey,
            this.dictVersion,
            fetchFile,
            { priority: 'high' }
          );
        } else {
          data = await fetchFile();
        }

        const uint8Array = new Uint8Array(data);

        // Write to virtual file system
        this.module.FS.writeFile(`/dict/${filename}`, uint8Array);
        console.log(`Loaded ${filename} (${uint8Array.length} bytes)`);

      } catch (error) {
        console.error(`Failed to load ${filename}:`, error);
        throw error;
      }
    });

    await Promise.all(loadPromises);
    console.log('All dictionary files loaded successfully');
  }

  /**
   * Load dictionary from embedded data
   * @param {Object} dictData - Dictionary data object with file contents
   * @returns {void}
   */
  loadFromEmbedded(dictData) {
    console.log('Loading embedded dictionary data');
    
    // Ensure directory exists
    try {
      this.module.FS.mkdir('/dict');
    } catch (e) {
      // Directory might already exist
    }

    // Write each file to the virtual file system
    for (const [filename, data] of Object.entries(dictData)) {
      if (this.dictFiles.includes(filename)) {
        const uint8Array = new Uint8Array(data);
        this.module.FS.writeFile(`/dict/${filename}`, uint8Array);
        console.log(`Loaded ${filename} from embedded data (${uint8Array.length} bytes)`);
      }
    }
  }

  /**
   * Verify dictionary files are loaded
   * @returns {boolean} True if all files are present
   */
  verify() {
    try {
      const files = this.module.FS.readdir('/dict');
      const missingFiles = this.dictFiles.filter(f => !files.includes(f));
      
      if (missingFiles.length > 0) {
        console.error('Missing dictionary files:', missingFiles);
        return false;
      }
      
      console.log('Dictionary verification passed');
      return true;
      
    } catch (error) {
      console.error('Failed to verify dictionary:', error);
      return false;
    }
  }

  /**
   * Get dictionary file sizes for debugging
   * @returns {Object} File sizes
   */
  getFileSizes() {
    const sizes = {};
    
    try {
      for (const filename of this.dictFiles) {
        const stat = this.module.FS.stat(`/dict/${filename}`);
        sizes[filename] = stat.size;
      }
    } catch (error) {
      console.error('Failed to get file sizes:', error);
    }
    
    return sizes;
  }

  /**
   * Clear cached dictionary data (if cacheManager is available)
   * @returns {Promise<void>}
   */
  async clearCache() {
    if (this.cacheManager) {
      await this.cacheManager.clear();
    }
  }
}

/**
 * Simple tar archive extractor for browser
 * Only handles uncompressed tar files
 */
export class TarExtractor {
  /**
   * Extract files from a tar buffer
   * @param {ArrayBuffer} buffer - Tar file buffer
   * @returns {Map<string, Uint8Array>} Extracted files
   */
  static extract(buffer) {
    const files = new Map();
    const view = new DataView(buffer);
    let offset = 0;

    while (offset < buffer.byteLength - 512) {
      // Read header
      const header = new Uint8Array(buffer, offset, 512);
      
      // Check if we've reached the end (null block)
      if (header.every(byte => byte === 0)) {
        break;
      }

      // Parse filename (0-99)
      const filenameBytes = header.slice(0, 100);
      const filenameEnd = filenameBytes.indexOf(0);
      const filename = new TextDecoder().decode(
        filenameBytes.slice(0, filenameEnd > 0 ? filenameEnd : 100)
      );

      // Parse file size (124-135, octal)
      const sizeStr = new TextDecoder().decode(header.slice(124, 136)).trim();
      const fileSize = parseInt(sizeStr, 8) || 0;

      // Skip directories and empty files
      if (fileSize > 0 && !filename.endsWith('/')) {
        // Read file content
        const contentStart = offset + 512;
        const contentEnd = contentStart + fileSize;
        const content = new Uint8Array(buffer, contentStart, fileSize);
        
        files.set(filename, content);
      }

      // Move to next header (512-byte aligned)
      offset += 512 + Math.ceil(fileSize / 512) * 512;
    }

    return files;
  }
}

/**
 * Gzip decompressor using pako library
 * For production, we should use native DecompressionStream when available
 */
export async function decompressGzip(buffer) {
  // Check if native decompression is available
  if ('DecompressionStream' in globalThis) {
    const ds = new DecompressionStream('gzip');
    const decompressedStream = new Response(buffer).body.pipeThrough(ds);
    const decompressed = await new Response(decompressedStream).arrayBuffer();
    return decompressed;
  }
  
  // Fallback: would need pako or similar library
  throw new Error('Gzip decompression not available. Please include pako library or use a modern browser.');
}