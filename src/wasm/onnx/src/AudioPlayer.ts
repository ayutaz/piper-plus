/**
 * Audio Player
 * 
 * Handles audio playback using Web Audio API
 */

export class AudioPlayer {
  private audioContext: AudioContext | null = null;
  private currentSource: AudioBufferSourceNode | null = null;
  private gainNode: GainNode | null = null;
  
  /**
   * Initialize audio context
   */
  async initialize(): Promise<void> {
    if (this.audioContext) {
      return;
    }
    
    try {
      this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      
      // Create gain node for volume control
      this.gainNode = this.audioContext.createGain();
      this.gainNode.connect(this.audioContext.destination);
      
      // Resume context if suspended (for Chrome autoplay policy)
      if (this.audioContext.state === 'suspended') {
        await this.audioContext.resume();
      }
      
      console.log('Audio player initialized');
      
    } catch (error) {
      console.error('Failed to initialize audio context:', error);
      throw new Error('Audio initialization failed');
    }
  }
  
  /**
   * Play audio data
   */
  async play(audioData: Float32Array, sampleRate: number): Promise<void> {
    if (!this.audioContext || !this.gainNode) {
      await this.initialize();
    }
    
    // Stop any current playback
    this.stop();
    
    try {
      // Create audio buffer
      const audioBuffer = this.audioContext!.createBuffer(
        1, // mono
        audioData.length,
        sampleRate
      );
      
      // Copy audio data to buffer
      audioBuffer.copyToChannel(audioData, 0);
      
      // Create source node
      this.currentSource = this.audioContext!.createBufferSource();
      this.currentSource.buffer = audioBuffer;
      this.currentSource.connect(this.gainNode!);
      
      // Start playback
      this.currentSource.start(0);
      
      // Handle playback end
      this.currentSource.onended = () => {
        this.currentSource = null;
      };
      
    } catch (error) {
      console.error('Audio playback failed:', error);
      throw new Error('Failed to play audio');
    }
  }
  
  /**
   * Stop playback
   */
  stop(): void {
    if (this.currentSource) {
      try {
        this.currentSource.stop();
        this.currentSource.disconnect();
      } catch (error) {
        // Ignore errors if already stopped
      }
      this.currentSource = null;
    }
  }
  
  /**
   * Set volume (0.0 to 1.0)
   */
  setVolume(volume: number): void {
    if (this.gainNode) {
      this.gainNode.gain.value = Math.max(0, Math.min(1, volume));
    }
  }
  
  /**
   * Get current volume
   */
  getVolume(): number {
    return this.gainNode ? this.gainNode.gain.value : 1.0;
  }
  
  /**
   * Get audio context state
   */
  getState(): string {
    return this.audioContext ? this.audioContext.state : 'uninitialized';
  }
  
  /**
   * Convert audio data to WAV format
   */
  toWAV(audioData: Float32Array, sampleRate: number): ArrayBuffer {
    const length = audioData.length;
    const arrayBuffer = new ArrayBuffer(44 + length * 2);
    const view = new DataView(arrayBuffer);
    
    // WAV header
    const writeString = (offset: number, string: string) => {
      for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
      }
    };
    
    // RIFF chunk descriptor
    writeString(0, 'RIFF');
    view.setUint32(4, 36 + length * 2, true);
    writeString(8, 'WAVE');
    
    // Format sub-chunk
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true); // Sub-chunk size
    view.setUint16(20, 1, true); // Audio format (PCM)
    view.setUint16(22, 1, true); // Number of channels
    view.setUint32(24, sampleRate, true); // Sample rate
    view.setUint32(28, sampleRate * 2, true); // Byte rate
    view.setUint16(32, 2, true); // Block align
    view.setUint16(34, 16, true); // Bits per sample
    
    // Data sub-chunk
    writeString(36, 'data');
    view.setUint32(40, length * 2, true);
    
    // Convert float samples to 16-bit PCM
    let offset = 44;
    for (let i = 0; i < length; i++) {
      const sample = Math.max(-1, Math.min(1, audioData[i]));
      view.setInt16(offset, sample * 0x7FFF, true);
      offset += 2;
    }
    
    return arrayBuffer;
  }
  
  /**
   * Download audio as WAV file
   */
  download(audioData: Float32Array, sampleRate: number, filename = 'audio.wav'): void {
    const wavBuffer = this.toWAV(audioData, sampleRate);
    const blob = new Blob([wavBuffer], { type: 'audio/wav' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    
    URL.revokeObjectURL(url);
  }
  
  /**
   * Dispose of resources
   */
  dispose(): void {
    this.stop();
    
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
    
    this.gainNode = null;
  }
}