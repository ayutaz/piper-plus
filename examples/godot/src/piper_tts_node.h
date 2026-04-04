#ifndef PIPER_TTS_NODE_H
#define PIPER_TTS_NODE_H

#include <godot_cpp/classes/audio_stream_player.hpp>
#include <godot_cpp/classes/audio_stream_generator.hpp>
#include <godot_cpp/classes/audio_stream_generator_playback.hpp>
#include <godot_cpp/core/class_db.hpp>

#include "piper_plus.h"

namespace godot {
} // namespace godot

class PiperTTS : public godot::AudioStreamPlayer {
    GDCLASS(PiperTTS, godot::AudioStreamPlayer)

public:
    PiperTTS();
    ~PiperTTS();

    // Lifecycle
    void _exit_tree() override;

    // Properties (exported to Inspector)
    void set_model_path(const godot::String &p_path);
    godot::String get_model_path() const;

    void set_config_path(const godot::String &p_path);
    godot::String get_config_path() const;

    void set_speaker_id(int p_id);
    int get_speaker_id() const;

    void set_language_id(int p_id);
    int get_language_id() const;

    void set_noise_scale(float p_val);
    float get_noise_scale() const;

    void set_length_scale(float p_val);
    float get_length_scale() const;

    // Methods
    bool load_model();
    void speak(const godot::String &p_text);
    void speak_streaming(const godot::String &p_text);

    // Query
    int get_num_speakers() const;
    int get_num_languages() const;
    bool is_model_loaded() const;

protected:
    static void _bind_methods();

private:
    void _ensure_engine();
    /// Idempotent: safe to call multiple times. Clears m_engine before freeing
    /// to prevent double-free when called from both _exit_tree() and ~PiperTTS().
    void _destroy_engine();
    void _push_samples_to_generator(const float *samples, int32_t num_samples, int32_t sample_rate);

    PiperPlusEngine *m_engine = nullptr;
    godot::String m_model_path;
    godot::String m_config_path;
    int m_speaker_id = 0;
    int m_language_id = -1;  // -1 = auto-detect
    float m_noise_scale = 0.667f;
    float m_length_scale = 1.0f;
};

#endif // PIPER_TTS_NODE_H
