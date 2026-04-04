#include "piper_tts_node.h"

#include <godot_cpp/classes/audio_stream_generator.hpp>
#include <godot_cpp/classes/audio_stream_generator_playback.hpp>
#include <godot_cpp/variant/utility_functions.hpp>

#include <cstring>

using namespace godot;

PiperTTS::PiperTTS() {
}

PiperTTS::~PiperTTS() {
    _destroy_engine();
}

void PiperTTS::_exit_tree() {
    _destroy_engine();
}

// --- Property accessors ---

void PiperTTS::set_model_path(const String &p_path) {
    m_model_path = p_path;
}

String PiperTTS::get_model_path() const {
    return m_model_path;
}

void PiperTTS::set_config_path(const String &p_path) {
    m_config_path = p_path;
}

String PiperTTS::get_config_path() const {
    return m_config_path;
}

void PiperTTS::set_speaker_id(int p_id) {
    m_speaker_id = p_id;
}

int PiperTTS::get_speaker_id() const {
    return m_speaker_id;
}

void PiperTTS::set_language_id(int p_id) {
    m_language_id = p_id;
}

int PiperTTS::get_language_id() const {
    return m_language_id;
}

void PiperTTS::set_noise_scale(float p_val) {
    m_noise_scale = p_val;
}

float PiperTTS::get_noise_scale() const {
    return m_noise_scale;
}

void PiperTTS::set_length_scale(float p_val) {
    m_length_scale = p_val;
}

float PiperTTS::get_length_scale() const {
    return m_length_scale;
}

// --- Query ---

int PiperTTS::get_num_speakers() const {
    if (!m_engine) return 0;
    return piper_plus_num_speakers(m_engine);
}

int PiperTTS::get_num_languages() const {
    if (!m_engine) return 0;
    return piper_plus_num_languages(m_engine);
}

bool PiperTTS::is_model_loaded() const {
    return m_engine != nullptr;
}

// --- Engine lifecycle ---

void PiperTTS::_ensure_engine() {
    if (m_engine) return;
    if (m_model_path.is_empty()) {
        UtilityFunctions::printerr("[PiperTTS] model_path is not set.");
        return;
    }
    load_model();
}

// Idempotent: safe to call multiple times (e.g., from both _exit_tree and ~PiperTTS).
// Sets m_engine to nullptr after freeing to prevent double-free.
void PiperTTS::_destroy_engine() {
    if (m_engine) {
        PiperPlusEngine *tmp = m_engine;
        m_engine = nullptr;  // Clear first to prevent re-entrant double-free
        piper_plus_free(tmp);
    }
}

bool PiperTTS::load_model() {
    _destroy_engine();

    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));

    CharString model_utf8 = m_model_path.utf8();
    CharString config_utf8 = m_config_path.utf8();

    config.model_path = model_utf8.get_data();
    if (!m_config_path.is_empty()) {
        config.config_path = config_utf8.get_data();
    }

    PiperPlusStatus rc = piper_plus_create(&config, &m_engine);
    if (rc != PIPER_PLUS_OK) {
        UtilityFunctions::printerr("[PiperTTS] Failed to load model: ",
                                   piper_plus_get_last_error());
        m_engine = nullptr;
        return false;
    }

    UtilityFunctions::print("[PiperTTS] Model loaded: ", m_model_path,
                            " (speakers=", piper_plus_num_speakers(m_engine),
                            ", languages=", piper_plus_num_languages(m_engine),
                            ", sample_rate=", piper_plus_sample_rate(m_engine), ")");
    return true;
}

// --- Synthesis helpers ---

void PiperTTS::_push_samples_to_generator(const float *samples, int32_t num_samples, int32_t sample_rate) {
    // Set up an AudioStreamGenerator matching the model's sample rate
    Ref<AudioStreamGenerator> gen;
    gen.instantiate();
    gen->set_mix_rate((float)sample_rate);
    gen->set_buffer_length((float)num_samples / (float)sample_rate + 0.5f);
    set_stream(gen);

    play();

    Ref<AudioStreamGeneratorPlayback> playback = get_stream_playback();
    if (playback.is_null()) {
        UtilityFunctions::printerr("[PiperTTS] Failed to get generator playback.");
        return;
    }

    // Push mono float samples as stereo Vector2 frames
    PackedVector2Array frames;
    frames.resize(num_samples);
    for (int32_t i = 0; i < num_samples; i++) {
        float s = samples[i];
        frames.set(i, Vector2(s, s));
    }
    playback->push_buffer(frames);
}

// --- Public methods ---

void PiperTTS::speak(const String &p_text) {
    _ensure_engine();
    if (!m_engine) return;

    CharString text_utf8 = p_text.utf8();

    PiperPlusSynthOptions opts = piper_plus_default_options();
    opts.speaker_id = m_speaker_id;
    opts.language_id = m_language_id;
    opts.noise_scale = m_noise_scale;
    opts.length_scale = m_length_scale;

    float *samples = nullptr;
    int32_t num_samples = 0;
    int32_t sample_rate = 0;

    PiperPlusStatus rc = piper_plus_synthesize(
        m_engine, text_utf8.get_data(), &opts,
        &samples, &num_samples, &sample_rate);

    if (rc != PIPER_PLUS_OK) {
        UtilityFunctions::printerr("[PiperTTS] Synthesis failed: ",
                                   piper_plus_get_last_error());
        return;
    }

    _push_samples_to_generator(samples, num_samples, sample_rate);
    piper_plus_free_audio(samples);

    emit_signal("synthesis_complete");
}

void PiperTTS::speak_streaming(const String &p_text) {
    _ensure_engine();
    if (!m_engine) return;

    CharString text_utf8 = p_text.utf8();

    PiperPlusSynthOptions opts = piper_plus_default_options();
    opts.speaker_id = m_speaker_id;
    opts.language_id = m_language_id;
    opts.noise_scale = m_noise_scale;
    opts.length_scale = m_length_scale;

    // Start iterative synthesis
    PiperPlusStatus rc = piper_plus_synth_start(m_engine, text_utf8.get_data(), &opts);
    if (rc != PIPER_PLUS_OK) {
        UtilityFunctions::printerr("[PiperTTS] Streaming start failed: ",
                                   piper_plus_get_last_error());
        return;
    }

    // Collect all chunks (streaming is synchronous on the calling thread)
    // We accumulate because AudioStreamGenerator needs total buffer length upfront.
    std::vector<float> all_samples;
    int32_t sample_rate = piper_plus_sample_rate(m_engine);

    while (true) {
        PiperPlusAudioChunk chunk;
        memset(&chunk, 0, sizeof(chunk));
        rc = piper_plus_synth_next(m_engine, &chunk);
        if (rc < 0) {
            UtilityFunctions::printerr("[PiperTTS] Streaming chunk failed: ",
                                       piper_plus_get_last_error());
            return;
        }

        if (chunk.num_samples > 0) {
            all_samples.insert(all_samples.end(),
                               chunk.samples, chunk.samples + chunk.num_samples);
            sample_rate = chunk.sample_rate;
        }

        if (rc == PIPER_PLUS_DONE || chunk.is_last) break;
    }

    if (!all_samples.empty()) {
        _push_samples_to_generator(all_samples.data(),
                                   (int32_t)all_samples.size(), sample_rate);
    }

    emit_signal("synthesis_complete");
}

// --- GDExtension bindings ---

void PiperTTS::_bind_methods() {
    // Properties
    ClassDB::bind_method(D_METHOD("set_model_path", "path"), &PiperTTS::set_model_path);
    ClassDB::bind_method(D_METHOD("get_model_path"), &PiperTTS::get_model_path);
    ADD_PROPERTY(PropertyInfo(Variant::STRING, "model_path", PROPERTY_HINT_FILE, "*.onnx"),
                 "set_model_path", "get_model_path");

    ClassDB::bind_method(D_METHOD("set_config_path", "path"), &PiperTTS::set_config_path);
    ClassDB::bind_method(D_METHOD("get_config_path"), &PiperTTS::get_config_path);
    ADD_PROPERTY(PropertyInfo(Variant::STRING, "config_path", PROPERTY_HINT_FILE, "*.json"),
                 "set_config_path", "get_config_path");

    ClassDB::bind_method(D_METHOD("set_speaker_id", "id"), &PiperTTS::set_speaker_id);
    ClassDB::bind_method(D_METHOD("get_speaker_id"), &PiperTTS::get_speaker_id);
    ADD_PROPERTY(PropertyInfo(Variant::INT, "speaker_id"), "set_speaker_id", "get_speaker_id");

    ClassDB::bind_method(D_METHOD("set_language_id", "id"), &PiperTTS::set_language_id);
    ClassDB::bind_method(D_METHOD("get_language_id"), &PiperTTS::get_language_id);
    ADD_PROPERTY(PropertyInfo(Variant::INT, "language_id"), "set_language_id", "get_language_id");

    ClassDB::bind_method(D_METHOD("set_noise_scale", "scale"), &PiperTTS::set_noise_scale);
    ClassDB::bind_method(D_METHOD("get_noise_scale"), &PiperTTS::get_noise_scale);
    ADD_PROPERTY(PropertyInfo(Variant::FLOAT, "noise_scale"), "set_noise_scale", "get_noise_scale");

    ClassDB::bind_method(D_METHOD("set_length_scale", "scale"), &PiperTTS::set_length_scale);
    ClassDB::bind_method(D_METHOD("get_length_scale"), &PiperTTS::get_length_scale);
    ADD_PROPERTY(PropertyInfo(Variant::FLOAT, "length_scale"), "set_length_scale", "get_length_scale");

    // Methods
    ClassDB::bind_method(D_METHOD("load_model"), &PiperTTS::load_model);
    ClassDB::bind_method(D_METHOD("speak", "text"), &PiperTTS::speak);
    ClassDB::bind_method(D_METHOD("speak_streaming", "text"), &PiperTTS::speak_streaming);

    // Query
    ClassDB::bind_method(D_METHOD("get_num_speakers"), &PiperTTS::get_num_speakers);
    ClassDB::bind_method(D_METHOD("get_num_languages"), &PiperTTS::get_num_languages);
    ClassDB::bind_method(D_METHOD("is_model_loaded"), &PiperTTS::is_model_loaded);

    // Signals
    ADD_SIGNAL(MethodInfo("synthesis_complete"));
}
