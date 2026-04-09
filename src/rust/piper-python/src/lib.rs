//! Python bindings for Piper-Plus TTS inference
//!
//! PyO3 + numpy で PiperVoice の全機能を Python に公開する。
//! GIL は推論中に解放し、マルチスレッド Python からの利用を可能にする。

use std::path::Path;

use numpy::{IntoPyArray, PyArray1};
use pyo3::exceptions::{PyIOError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;

// ---------------------------------------------------------------------------
// Error conversion: PiperError -> PyErr
// ---------------------------------------------------------------------------

/// PiperError を Python 例外に変換する。
///
/// Rust の orphan rule により `impl From<PiperError> for PyErr` は直接書けない
/// (両方とも外部クレートの型) ため、変換関数として提供する。
///
/// - Config / validation 系 -> ValueError
/// - IO / WAV 系 -> IOError
/// - その他 (推論・モデルロード) -> RuntimeError
fn piper_err_to_pyerr(err: piper_core::PiperError) -> PyErr {
    match &err {
        piper_core::PiperError::ConfigNotFound { .. }
        | piper_core::PiperError::InvalidConfig { .. }
        | piper_core::PiperError::UnsupportedLanguage { .. }
        | piper_core::PiperError::UnknownPhoneme { .. }
        | piper_core::PiperError::PhonemeIdNotFound { .. } => {
            PyValueError::new_err(err.to_string())
        }
        piper_core::PiperError::AudioOutput(_) | piper_core::PiperError::WavWrite(_) => {
            PyIOError::new_err(err.to_string())
        }
        _ => PyRuntimeError::new_err(err.to_string()),
    }
}

// ---------------------------------------------------------------------------
// Send wrapper for raw pointer (GIL release support)
// ---------------------------------------------------------------------------

/// Wrapper around a raw mutable pointer that implements `Send`.
///
/// SAFETY: This is safe to use with `py.allow_threads` because that function
/// only releases the Python GIL -- the closure still executes on the **same**
/// OS thread that holds `&mut self`.  No cross-thread data race can occur.
/// The wrapper must NOT be stored or sent to another thread outside of
/// `allow_threads`.
struct SendPtr<T>(*mut T);

// SAFETY: SendPtr is only used within py.allow_threads which runs the
// closure on the same OS thread.  The Send impl exists solely to satisfy
// the Ungil bound.
unsafe impl<T> Send for SendPtr<T> {}

impl<T> SendPtr<T> {
    /// Dereference the pointer as a mutable reference.
    ///
    /// SAFETY: Caller must guarantee the pointer is valid and that no
    /// other references to the same data exist.
    #[allow(clippy::mut_from_ref)]
    unsafe fn as_mut(&self) -> &mut T {
        unsafe { &mut *self.0 }
    }
}

// ---------------------------------------------------------------------------
// SynthesisResult
// ---------------------------------------------------------------------------

/// Result of a TTS synthesis operation.
///
/// Contains the generated audio samples and timing information.
/// Audio can be accessed as numpy arrays (int16 or float32) or saved to WAV.
#[pyclass]
#[derive(Clone)]
struct SynthesisResult {
    /// Duration of the generated audio in seconds.
    #[pyo3(get)]
    audio_seconds: f64,

    /// Time spent on ONNX inference in seconds.
    #[pyo3(get)]
    infer_seconds: f64,

    /// Sample rate of the audio (e.g. 22050).
    #[pyo3(get)]
    sample_rate: u32,

    /// Real-time factor (infer_seconds / audio_seconds).
    /// Values below 1.0 mean faster than real-time.
    #[pyo3(get)]
    real_time_factor: f64,

    /// Raw PCM samples (int16), kept for numpy conversion.
    samples: Vec<i16>,
}

#[allow(clippy::useless_conversion, clippy::needless_question_mark)]
#[pymethods]
impl SynthesisResult {
    /// Return audio as a numpy int16 array (cloning the internal buffer).
    ///
    /// The array contains raw PCM samples suitable for direct playback
    /// or WAV encoding.  The internal buffer is preserved so that
    /// :meth:`audio_float32`, :meth:`save_wav`, or a second call to this
    /// method remain valid.  For a zero-copy alternative, see
    /// :meth:`take_audio_int16`.
    fn audio_int16<'py>(&self, py: Python<'py>) -> Bound<'py, PyArray1<i16>> {
        self.samples.clone().into_pyarray(py)
    }

    /// Move the internal int16 buffer into a numpy array without copying.
    ///
    /// This is more efficient than :meth:`audio_int16` because it avoids
    /// cloning the samples vector.  After calling this method the internal
    /// buffer is empty -- subsequent calls to :meth:`audio_int16`,
    /// :meth:`audio_float32`, or :meth:`save_wav` will return/use an
    /// empty array.
    fn take_audio_int16<'py>(&mut self, py: Python<'py>) -> Bound<'py, PyArray1<i16>> {
        std::mem::take(&mut self.samples).into_pyarray(py)
    }

    /// Return audio as a numpy float32 array, normalized to [-1.0, 1.0].
    ///
    /// Useful for downstream audio processing libraries that expect
    /// floating-point samples.
    fn audio_float32<'py>(&self, py: Python<'py>) -> Bound<'py, PyArray1<f32>> {
        let floats: Vec<f32> = self.samples.iter().map(|&s| s as f32 / 32768.0).collect();
        floats.into_pyarray(py)
    }

    /// Save audio to a WAV file.
    ///
    /// Args:
    ///     path: Output file path (e.g. "output.wav").
    fn save_wav(&self, path: &str) -> PyResult<()> {
        piper_core::audio::write_wav(Path::new(path), self.sample_rate, &self.samples)
            .map_err(piper_err_to_pyerr)
    }

    fn __repr__(&self) -> String {
        format!(
            "SynthesisResult(audio_seconds={:.3}, infer_seconds={:.3}, sample_rate={}, rtf={:.3}, samples={})",
            self.audio_seconds,
            self.infer_seconds,
            self.sample_rate,
            self.real_time_factor,
            self.samples.len(),
        )
    }
}

/// Build a Python SynthesisResult from the core SynthesisResult.
impl From<piper_core::SynthesisResult> for SynthesisResult {
    fn from(r: piper_core::SynthesisResult) -> Self {
        Self {
            audio_seconds: r.audio_seconds,
            infer_seconds: r.infer_seconds,
            sample_rate: r.sample_rate,
            real_time_factor: r.real_time_factor(),
            samples: r.audio,
        }
    }
}

// ---------------------------------------------------------------------------
// PiperVoice
// ---------------------------------------------------------------------------

/// A loaded TTS voice model.
///
/// Wraps the Rust `PiperVoice` and exposes text-to-speech synthesis to Python.
///
/// Example:
///     >>> voice = PiperVoice("model.onnx")
///     >>> result = voice.synthesize("Hello, world!")
///     >>> result.save_wav("hello.wav")
///     >>> audio = result.audio_float32()   # numpy array
#[pyclass]
struct PiperVoice {
    inner: piper_core::PiperVoice,
}

#[allow(clippy::useless_conversion, clippy::needless_question_mark)]
#[pymethods]
impl PiperVoice {
    /// Load a voice model from files.
    ///
    /// Args:
    ///     model_path: Path to ONNX model file.
    ///     config_path: Optional path to config.json. If omitted, the loader
    ///         searches for ``{model}.onnx.json`` or ``config.json`` in the
    ///         model directory.
    ///     device: Device string -- ``"cpu"``, ``"cuda"``, or ``"auto"``.
    ///         Currently only CPU is implemented; GPU selection is accepted
    ///         but falls back to CPU with a warning.
    ///
    /// Raises:
    ///     ValueError: If the config is missing or invalid.
    ///     RuntimeError: If the ONNX model fails to load.
    #[new]
    #[pyo3(signature = (model_path, config_path=None, device="cpu"))]
    fn new(model_path: &str, config_path: Option<&str>, device: &str) -> PyResult<Self> {
        let cfg = config_path.map(Path::new);
        let inner = piper_core::PiperVoice::load(Path::new(model_path), cfg, device)
            .map_err(piper_err_to_pyerr)?;
        Ok(Self { inner })
    }

    /// Synthesize text to audio.
    ///
    /// Returns a :class:`SynthesisResult` containing the generated PCM samples
    /// and timing information.  The audio can be retrieved as a numpy array
    /// via :meth:`SynthesisResult.audio_int16` or
    /// :meth:`SynthesisResult.audio_float32`.
    ///
    /// The GIL is released during ONNX inference so other Python threads
    /// can run concurrently.
    ///
    /// Args:
    ///     text: Input text to synthesize.
    ///     speaker_id: Speaker index for multi-speaker models (default: None).
    ///     language: Language code override (e.g. ``"ja"``, ``"en"``).
    ///         If omitted, the phonemizer auto-detects the language.
    ///     noise_scale: Noise scale for VITS stochastic synthesis (default: 0.667).
    ///     length_scale: Duration scale -- values > 1.0 produce slower speech (default: 1.0).
    ///     noise_w: Noise weight for duration predictor (default: 0.8).
    ///
    /// Returns:
    ///     SynthesisResult with audio samples and timing metadata.
    ///
    /// Raises:
    ///     ValueError: If the text produces unknown phonemes.
    ///     RuntimeError: If ONNX inference fails.
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (text, speaker_id=None, language=None, noise_scale=0.667, length_scale=1.0, noise_w=0.8))]
    fn synthesize(
        &mut self,
        py: Python<'_>,
        text: &str,
        speaker_id: Option<i64>,
        language: Option<&str>,
        noise_scale: f32,
        length_scale: f32,
        noise_w: f32,
    ) -> PyResult<SynthesisResult> {
        // Copy parameters into owned values for the closure (text is &str,
        // language is Option<&str> -- we need owned copies to move into
        // allow_threads).
        let text_owned = text.to_string();
        let language_owned = language.map(|s| s.to_string());

        // SAFETY: We wrap the raw pointer in SendPtr to satisfy the Ungil
        // bound required by allow_threads.  This is safe because
        // allow_threads only releases the GIL -- the closure still runs on
        // the same OS thread that holds &mut self, so no data race occurs.
        let inner_ptr = SendPtr(&mut self.inner as *mut piper_core::PiperVoice);

        let result = py.allow_threads(move || {
            let inner = unsafe { inner_ptr.as_mut() };
            #[allow(deprecated)]
            inner.synthesize_text(
                &text_owned,
                speaker_id,
                language_owned.as_deref(),
                noise_scale,
                length_scale,
                noise_w,
            )
        });

        Ok(result.map_err(piper_err_to_pyerr)?.into())
    }

    /// Synthesize multiple texts in a single call.
    ///
    /// This is more efficient than calling :meth:`synthesize` in a loop
    /// because the GIL is released once for the entire batch rather than
    /// once per text.
    ///
    /// The GIL is released during ONNX inference so other Python threads
    /// can run concurrently.
    ///
    /// Args:
    ///     texts: List of input texts to synthesize.
    ///     speaker_id: Speaker index for multi-speaker models (default: None).
    ///     language: Language code override (e.g. ``"ja"``, ``"en"``).
    ///         If omitted, the phonemizer auto-detects each text's language.
    ///     noise_scale: Noise scale for VITS stochastic synthesis (default: 0.667).
    ///     length_scale: Duration scale -- values > 1.0 produce slower speech (default: 1.0).
    ///     noise_w: Noise weight for duration predictor (default: 0.8).
    ///
    /// Returns:
    ///     List of SynthesisResult, one per input text, in the same order.
    ///
    /// Raises:
    ///     ValueError: If any text produces unknown phonemes.
    ///     RuntimeError: If ONNX inference fails.
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (texts, speaker_id=None, language=None, noise_scale=0.667, length_scale=1.0, noise_w=0.8))]
    fn synthesize_batch(
        &mut self,
        py: Python<'_>,
        texts: Vec<String>,
        speaker_id: Option<i64>,
        language: Option<String>,
        noise_scale: f32,
        length_scale: f32,
        noise_w: f32,
    ) -> PyResult<Vec<SynthesisResult>> {
        let inner_ptr = SendPtr(&mut self.inner as *mut piper_core::PiperVoice);

        let results = py.allow_threads(move || {
            let inner = unsafe { inner_ptr.as_mut() };
            let mut out = Vec::with_capacity(texts.len());
            for text in &texts {
                #[allow(deprecated)]
                let r = inner.synthesize_text(
                    text,
                    speaker_id,
                    language.as_deref(),
                    noise_scale,
                    length_scale,
                    noise_w,
                )?;
                out.push(r);
            }
            Ok::<_, piper_core::PiperError>(out)
        });

        Ok(results
            .map_err(piper_err_to_pyerr)?
            .into_iter()
            .map(SynthesisResult::from)
            .collect())
    }

    /// Synthesize text and save directly to a WAV file.
    ///
    /// This is a convenience method combining :meth:`synthesize` and
    /// :meth:`SynthesisResult.save_wav`.  Default synthesis parameters
    /// (noise_scale=0.667, length_scale=1.0, noise_w=0.8) are used.
    ///
    /// The GIL is released during ONNX inference.
    ///
    /// Args:
    ///     text: Input text to synthesize.
    ///     output_path: Path for the output WAV file.
    ///     speaker_id: Speaker index for multi-speaker models (default: None).
    ///
    /// Returns:
    ///     SynthesisResult with audio metadata (the WAV file is also written).
    ///
    /// Raises:
    ///     IOError: If the WAV file cannot be written.
    ///     RuntimeError: If ONNX inference fails.
    #[pyo3(signature = (text, output_path, speaker_id=None))]
    fn synthesize_to_file(
        &mut self,
        py: Python<'_>,
        text: &str,
        output_path: &str,
        speaker_id: Option<i64>,
    ) -> PyResult<SynthesisResult> {
        let text_owned = text.to_string();
        let output_owned = output_path.to_string();

        let inner_ptr = SendPtr(&mut self.inner as *mut piper_core::PiperVoice);

        let result = py.allow_threads(move || {
            let inner = unsafe { inner_ptr.as_mut() };
            inner.text_to_wav_file(&text_owned, Path::new(&output_owned), speaker_id)
        });

        Ok(result.map_err(piper_err_to_pyerr)?.into())
    }

    /// The sample rate of the loaded model (e.g. 22050).
    #[getter]
    fn sample_rate(&self) -> u32 {
        self.inner.config().audio.sample_rate
    }

    /// The number of speakers in the model.
    ///
    /// Returns 1 for single-speaker models.
    #[getter]
    fn num_speakers(&self) -> usize {
        self.inner.config().num_speakers
    }

    /// The number of languages supported by the model.
    ///
    /// Returns 1 for monolingual models, >1 for multilingual models.
    #[getter]
    fn num_languages(&self) -> usize {
        self.inner.config().num_languages
    }

    /// List of available language codes (e.g. ``["ja", "en", "zh"]``).
    ///
    /// Returns an empty list for monolingual models that do not declare
    /// a ``language_id_map`` in their config.
    #[getter]
    fn languages(&self) -> Vec<String> {
        let mut langs: Vec<String> = self
            .inner
            .config()
            .language_id_map
            .keys()
            .cloned()
            .collect();
        langs.sort();
        langs
    }

    /// List of valid speaker IDs.
    ///
    /// For models with a ``speaker_id_map``, returns the mapped IDs sorted
    /// numerically.  For models without a map, returns ``[0]`` through
    /// ``[num_speakers - 1]``.
    #[getter]
    fn speaker_ids(&self) -> Vec<i64> {
        let config = self.inner.config();
        if config.speaker_id_map.is_empty() {
            (0..config.num_speakers as i64).collect()
        } else {
            let mut ids: Vec<i64> = config.speaker_id_map.values().copied().collect();
            ids.sort();
            ids
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "PiperVoice(sample_rate={}, speakers={}, languages={})",
            self.inner.config().audio.sample_rate,
            self.inner.config().num_speakers,
            self.inner.config().num_languages,
        )
    }
}

// ---------------------------------------------------------------------------
// Module initialization
// ---------------------------------------------------------------------------

/// Piper-Plus: high-quality neural text-to-speech with 7-language support.
///
/// Quick start::
///
///     import piper_plus
///
///     voice = piper_plus.PiperVoice("model.onnx")
///     result = voice.synthesize("Hello, world!")
///     result.save_wav("hello.wav")
///
/// Classes:
///     PiperVoice -- Load a model and synthesize speech.
///     SynthesisResult -- Audio samples and timing metadata.
#[pymodule]
fn piper_plus(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PiperVoice>()?;
    m.add_class::<SynthesisResult>()?;
    Ok(())
}
