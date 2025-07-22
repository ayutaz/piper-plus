/**
 * Unit tests for AudioPlayer
 */

import { AudioPlayer } from '../src/AudioPlayer';

// Mock AudioContext
class MockAudioContext {
  state = 'running';
  sampleRate = 44100;
  destination = {};
  
  createGain() {
    return {
      gain: { value: 1.0 },
      connect: jest.fn()
    };
  }
  
  createBuffer(channels: number, length: number, sampleRate: number) {
    return {
      numberOfChannels: channels,
      length,
      sampleRate,
      copyToChannel: jest.fn(),
      getChannelData: jest.fn(() => new Float32Array(length))
    };
  }
  
  createBufferSource() {
    return {
      buffer: null,
      connect: jest.fn(),
      start: jest.fn(),
      stop: jest.fn(),
      disconnect: jest.fn(),
      onended: null
    };
  }
  
  resume = jest.fn().mockResolvedValue(undefined);
  close = jest.fn().mockResolvedValue(undefined);
}

// Setup global AudioContext
(global as any).AudioContext = MockAudioContext;

describe('AudioPlayer', () => {
  let audioPlayer: AudioPlayer;
  
  beforeEach(() => {
    audioPlayer = new AudioPlayer();
  });
  
  afterEach(() => {
    audioPlayer.dispose();
  });

  describe('initialize', () => {
    test('should create audio context', async () => {
      await audioPlayer.initialize();
      expect(audioPlayer.getState()).toBe('running');
    });

    test('should handle multiple initialization calls', async () => {
      await audioPlayer.initialize();
      await audioPlayer.initialize();
      expect(audioPlayer.getState()).toBe('running');
    });

    test('should resume suspended context', async () => {
      const mockContext = new MockAudioContext();
      mockContext.state = 'suspended';
      (global as any).AudioContext = jest.fn(() => mockContext);
      
      const player = new AudioPlayer();
      await player.initialize();
      
      expect(mockContext.resume).toHaveBeenCalled();
    });
  });

  describe('play', () => {
    const testAudioData = new Float32Array([0.1, 0.2, 0.3, 0.4, 0.5]);
    const testSampleRate = 22050;
    
    beforeEach(async () => {
      await audioPlayer.initialize();
    });

    test('should play audio data', async () => {
      await expect(audioPlayer.play(testAudioData, testSampleRate))
        .resolves.not.toThrow();
    });

    test('should stop previous playback', async () => {
      await audioPlayer.play(testAudioData, testSampleRate);
      await audioPlayer.play(testAudioData, testSampleRate);
      // Should not throw
    });

    test('should initialize if not initialized', async () => {
      const newPlayer = new AudioPlayer();
      await expect(newPlayer.play(testAudioData, testSampleRate))
        .resolves.not.toThrow();
    });
  });

  describe('stop', () => {
    test('should stop playback without error', async () => {
      await audioPlayer.initialize();
      const testData = new Float32Array(100);
      await audioPlayer.play(testData, 22050);
      
      expect(() => audioPlayer.stop()).not.toThrow();
    });

    test('should handle stop when not playing', () => {
      expect(() => audioPlayer.stop()).not.toThrow();
    });
  });

  describe('volume control', () => {
    beforeEach(async () => {
      await audioPlayer.initialize();
    });

    test('should set volume', () => {
      audioPlayer.setVolume(0.5);
      expect(audioPlayer.getVolume()).toBe(0.5);
    });

    test('should clamp volume to valid range', () => {
      audioPlayer.setVolume(-1);
      expect(audioPlayer.getVolume()).toBe(0);
      
      audioPlayer.setVolume(2);
      expect(audioPlayer.getVolume()).toBe(1);
    });

    test('should handle volume before initialization', () => {
      const newPlayer = new AudioPlayer();
      expect(newPlayer.getVolume()).toBe(1.0);
    });
  });

  describe('WAV conversion', () => {
    test('should convert audio to WAV format', () => {
      const audioData = new Float32Array([0.5, -0.5, 0.3, -0.3]);
      const sampleRate = 44100;
      
      const wavBuffer = audioPlayer.toWAV(audioData, sampleRate);
      
      expect(wavBuffer).toBeInstanceOf(ArrayBuffer);
      expect(wavBuffer.byteLength).toBe(44 + audioData.length * 2); // Header + 16-bit samples
      
      // Check WAV header
      const view = new DataView(wavBuffer);
      const riff = String.fromCharCode(
        view.getUint8(0),
        view.getUint8(1),
        view.getUint8(2),
        view.getUint8(3)
      );
      expect(riff).toBe('RIFF');
    });

    test('should clamp audio values in WAV', () => {
      const audioData = new Float32Array([2.0, -2.0]); // Out of range
      const wavBuffer = audioPlayer.toWAV(audioData, 22050);
      
      const view = new DataView(wavBuffer);
      const sample1 = view.getInt16(44, true);
      const sample2 = view.getInt16(46, true);
      
      expect(sample1).toBe(32767); // Max positive
      expect(sample2).toBe(-32767); // Max negative (clamped symmetrically)
    });
  });

  describe('download', () => {
    test('should trigger download', () => {
      const mockCreateElement = jest.spyOn(document, 'createElement');
      const mockClick = jest.fn();
      const mockURL = {
        createObjectURL: jest.fn(() => 'blob:test'),
        revokeObjectURL: jest.fn()
      };
      
      Object.defineProperty(window, 'URL', {
        value: mockURL,
        writable: true
      });
      
      mockCreateElement.mockReturnValue({
        click: mockClick,
        href: '',
        download: ''
      } as any);
      
      const audioData = new Float32Array(100);
      audioPlayer.download(audioData, 22050, 'test.wav');
      
      expect(mockCreateElement).toHaveBeenCalledWith('a');
      expect(mockClick).toHaveBeenCalled();
      expect(mockURL.createObjectURL).toHaveBeenCalled();
      expect(mockURL.revokeObjectURL).toHaveBeenCalledWith('blob:test');
    });
  });

  describe('dispose', () => {
    test('should clean up resources', async () => {
      await audioPlayer.initialize();
      audioPlayer.dispose();
      
      expect(audioPlayer.getState()).toBe('uninitialized');
    });

    test('should handle multiple dispose calls', () => {
      audioPlayer.dispose();
      expect(() => audioPlayer.dispose()).not.toThrow();
    });
  });
});