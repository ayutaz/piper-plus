//! Orchestrate real synthesis calls for SSML and phoneme silence boundaries.
use crate::{PiperError, SynthesisRequest, SynthesisResult};
use std::collections::HashMap;

fn empty(sample_rate: u32) -> SynthesisResult {
    SynthesisResult {
        audio: Vec::new(),
        sample_rate,
        infer_seconds: 0.0,
        audio_seconds: 0.0,
        durations: None,
        phoneme_ids: None,
        leading_silence_seconds: 0.0,
    }
}

fn append(out: &mut SynthesisResult, part: SynthesisResult, silence_seconds: f64) {
    out.infer_seconds += part.infer_seconds;
    out.audio.extend(part.audio);
    out.audio.resize(
        out.audio.len() + (silence_seconds * f64::from(out.sample_rate)).round() as usize,
        0,
    );
    out.audio_seconds = out.audio.len() as f64 / f64::from(out.sample_rate);
}

pub(crate) fn synthesize_ssml<F>(
    text: &str,
    sample_rate: u32,
    mut synthesize: F,
) -> Result<SynthesisResult, PiperError>
where
    F: FnMut(&str, f32) -> Result<SynthesisResult, PiperError>,
{
    let mut out = empty(sample_rate);
    for segment in crate::ssml::SsmlParser::parse(text) {
        let part = if segment.text.trim().is_empty() {
            empty(sample_rate)
        } else {
            synthesize(&segment.text, segment.rate)?
        };
        append(&mut out, part, f64::from(segment.break_ms) / 1000.0);
    }
    Ok(out)
}

/// Split original IDs (and aligned prosody) at requested boundaries, then
/// synthesize each phrase. This also works with models without durations.
/// Segmented audio has no single model duration tensor; do not fabricate one.
pub fn synthesize_phoneme_silence<F>(
    request: &SynthesisRequest,
    silence: &HashMap<String, f32>,
    id_map: &HashMap<String, Vec<i64>>,
    sample_rate: u32,
    mut synthesize: F,
) -> Result<SynthesisResult, PiperError>
where
    F: FnMut(&SynthesisRequest) -> Result<SynthesisResult, PiperError>,
{
    request.validate()?;
    if request
        .prosody_features
        .as_ref()
        .is_some_and(|p| p.len() != request.phoneme_ids.len())
    {
        return Err(PiperError::InvalidArgument {
            reason: "prosody length differs from phoneme IDs".into(),
        });
    }
    if silence.is_empty() {
        return synthesize(request);
    }
    let mut boundaries = Vec::new();
    for (token, seconds) in silence {
        if !seconds.is_finite() || *seconds < 0.0 {
            return Err(PiperError::InvalidArgument {
                reason: "phoneme silence must be finite and non-negative".into(),
            });
        }
        let ids = id_map
            .get(token)
            .filter(|ids| !ids.is_empty())
            .ok_or_else(|| PiperError::UnknownPhoneme {
                phoneme: token.clone(),
            })?;
        for end in ids.len()..=request.phoneme_ids.len() {
            if request.phoneme_ids[end - ids.len()..end] == ids[..] && *seconds > 0.0 {
                boundaries.push((end, *seconds));
            }
        }
    }
    boundaries.sort_by(|a, b| a.0.cmp(&b.0).then_with(|| b.1.total_cmp(&a.1)));
    boundaries.dedup_by_key(|(end, _)| *end);
    if boundaries.is_empty() {
        return synthesize(request);
    }
    if boundaries.last().map(|(end, _)| *end) != Some(request.phoneme_ids.len()) {
        boundaries.push((request.phoneme_ids.len(), 0.0));
    }
    let mut out = empty(sample_rate);
    let mut start = 0;
    for (end, seconds) in boundaries {
        let mut phrase = request.clone();
        phrase.phoneme_ids = request.phoneme_ids[start..end].to_vec();
        phrase.prosody_features = request
            .prosody_features
            .as_ref()
            .map(|p| p[start..end].to_vec());
        if phrase.phoneme_ids.first() != Some(&1) {
            phrase.phoneme_ids.insert(0, 1);
            if let Some(p) = &mut phrase.prosody_features {
                p.insert(0, [0; 3]);
            }
        }
        if phrase.phoneme_ids.last() != Some(&2) {
            phrase.phoneme_ids.push(2);
            if let Some(p) = &mut phrase.prosody_features {
                p.push([0; 3]);
            }
        }
        // A trailing EOS alone is a boundary marker, not an utterance.
        if phrase.phoneme_ids.iter().any(|id| *id != 1 && *id != 2) {
            append(&mut out, synthesize(&phrase)?, f64::from(seconds));
        }
        start = end;
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn ssml_routes_text_rate_and_break_into_audio() {
        let mut calls = Vec::new();
        let out = synthesize_ssml(
            "<speak>A<break time=\"500ms\"/><prosody rate=\"slow\">B</prosody></speak>",
            1000,
            |text, rate| {
                calls.push((text.to_string(), rate));
                let mut part = empty(1000);
                part.audio = vec![7; 10];
                Ok(part)
            },
        )
        .unwrap();
        assert_eq!(calls, vec![("A".into(), 1.0), ("B".into(), 1.25)]);
        assert_eq!(out.audio.len(), 520);
        assert!(out.audio[10..510].iter().all(|sample| *sample == 0));
    }
    #[test]
    fn phoneme_silence_splits_requests_and_preserves_conditioning() {
        let request = SynthesisRequest {
            phoneme_ids: vec![1, 10, 0, 11, 2],
            prosody_features: Some(vec![[3; 3]; 5]),
            speaker_embedding: Some(vec![0.5; 192]),
            ..Default::default()
        };
        let mut calls = 0;
        let result = synthesize_phoneme_silence(
            &request,
            &HashMap::from([("_".into(), 0.5)]),
            &HashMap::from([("_".into(), vec![0])]),
            1000,
            |part| {
                calls += 1;
                assert_eq!(
                    part.phoneme_ids.len(),
                    part.prosody_features.as_ref().unwrap().len()
                );
                assert_eq!(part.speaker_embedding, request.speaker_embedding);
                let mut out = empty(1000);
                out.audio = vec![9; 10];
                Ok(out)
            },
        )
        .unwrap();
        assert_eq!(calls, 2);
        assert_eq!(result.audio.len(), 520);
        assert_eq!(&result.audio[10..510], &[0; 500]);
    }
}
