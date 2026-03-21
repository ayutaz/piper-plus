use std::path::Path;

use crate::error::PiperError;

/// float32 音声データを int16 に変換 (ピーク正規化)
/// C++ 版 piper.cpp と同じアルゴリズム
pub fn audio_float_to_int16(audio: &[f32]) -> Vec<i16> {
    if audio.is_empty() {
        return Vec::new();
    }

    // ピーク値を検出 (最小値 0.01 でゼロ除算防止)
    let max_val = audio.iter().map(|x| x.abs()).fold(0.01f32, f32::max);

    let scale = 32767.0 / max_val;

    let mut result = Vec::with_capacity(audio.len());
    for &x in audio {
        result.push((x * scale).clamp(-32768.0, 32767.0) as i16);
    }
    result
}

/// WAV ファイルを書き出す
pub fn write_wav(path: &Path, sample_rate: u32, audio: &[i16]) -> Result<(), PiperError> {
    let spec = hound::WavSpec {
        channels: 1,
        sample_rate,
        bits_per_sample: 16,
        sample_format: hound::SampleFormat::Int,
    };

    let mut writer =
        hound::WavWriter::create(path, spec).map_err(|e| PiperError::WavWrite(e.to_string()))?;

    for &sample in audio {
        writer
            .write_sample(sample)
            .map_err(|e| PiperError::WavWrite(e.to_string()))?;
    }

    writer
        .finalize()
        .map_err(|e| PiperError::WavWrite(e.to_string()))?;

    Ok(())
}

/// WAV データを stdout にバイナリで書き出す (パイプ用)
pub fn write_wav_to_stdout(sample_rate: u32, audio: &[i16]) -> Result<(), PiperError> {
    use std::io::Write;

    let mut stdout = std::io::stdout().lock();

    // WAV ヘッダ (44 bytes)
    let data_size = (audio.len() * 2) as u32;
    let file_size = data_size + 36;

    // RIFF header
    stdout.write_all(b"RIFF")?;
    stdout.write_all(&file_size.to_le_bytes())?;
    stdout.write_all(b"WAVE")?;

    // fmt chunk
    stdout.write_all(b"fmt ")?;
    stdout.write_all(&16u32.to_le_bytes())?; // chunk size
    stdout.write_all(&1u16.to_le_bytes())?; // PCM format
    stdout.write_all(&1u16.to_le_bytes())?; // mono
    stdout.write_all(&sample_rate.to_le_bytes())?;
    stdout.write_all(&(sample_rate * 2).to_le_bytes())?; // byte rate
    stdout.write_all(&2u16.to_le_bytes())?; // block align
    stdout.write_all(&16u16.to_le_bytes())?; // bits per sample

    // data chunk
    stdout.write_all(b"data")?;
    stdout.write_all(&data_size.to_le_bytes())?;
    let mut buf = Vec::with_capacity(audio.len() * 2);
    for &sample in audio {
        buf.extend_from_slice(&sample.to_le_bytes());
    }
    stdout.write_all(&buf)?;

    stdout.flush()?;
    Ok(())
}

/// raw PCM int16 データを stdout にバイナリで書き出す (WAV ヘッダなし)
pub fn write_raw_to_stdout(audio: &[i16]) -> Result<(), PiperError> {
    use std::io::Write;

    let mut stdout = std::io::stdout().lock();
    let mut buf = Vec::with_capacity(audio.len() * 2);
    for &sample in audio {
        buf.extend_from_slice(&sample.to_le_bytes());
    }
    stdout.write_all(&buf)?;
    stdout.flush()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_audio_float_to_int16_silence() {
        let audio = vec![0.0f32; 100];
        let result = audio_float_to_int16(&audio);
        assert_eq!(result.len(), 100);
        assert!(result.iter().all(|&x| x == 0));
    }

    #[test]
    fn test_audio_float_to_int16_peak_normalization() {
        let audio = vec![0.5f32, -0.5, 1.0, -1.0];
        let result = audio_float_to_int16(&audio);
        assert_eq!(result.len(), 4);
        // 最大値 1.0 → 32767 にスケール
        assert_eq!(result[2], 32767);
        assert_eq!(result[3], -32767);
    }

    #[test]
    fn test_audio_float_to_int16_empty() {
        let result = audio_float_to_int16(&[]);
        assert!(result.is_empty());
    }

    #[test]
    fn test_audio_float_to_int16_clipping() {
        let audio = vec![2.0f32, -2.0]; // 範囲外の値
        let result = audio_float_to_int16(&audio);
        // ピーク正規化で 2.0 → 32767, -2.0 → -32767
        assert_eq!(result[0], 32767);
        assert_eq!(result[1], -32767);
    }
}
