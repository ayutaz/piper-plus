#include <emscripten.h>
#include <string>
#include <vector>
#include <memory>
#include <sstream>
#include <cstring>

// Forward declarations for OpenJTalk functions
extern "C" {
    int openjtalk_initialize(const char* dict_dir);
    char* openjtalk_synthesis_labels(const char* text);
    void openjtalk_clear();
    void openjtalk_free_string(char* str);
}

// Forward declarations for eSpeak-ng functions
extern "C" {
    typedef enum {
        espeakEVENT_LIST_TERMINATED = 0,
        espeakEVENT_WORD = 1,
        espeakEVENT_SENTENCE = 2,
        espeakEVENT_MARK = 3,
        espeakEVENT_PLAY = 4,
        espeakEVENT_END = 5,
        espeakEVENT_MSG_TERMINATED = 6,
        espeakEVENT_PHONEME = 7,
        espeakEVENT_SAMPLERATE = 8
    } espeak_EVENT_TYPE;

    typedef struct {
        espeak_EVENT_TYPE type;
        unsigned int unique_identifier;
        int text_position;
        int length;
        int audio_position;
        int sample;
        void* user_data;
        union {
            int number;
            const char *name;
            char string[8];
        } id;
    } espeak_EVENT;

    typedef enum {
        espeakCHARS_AUTO = 0,
        espeakCHARS_UTF8 = 1,
        espeakCHARS_8BIT = 2,
        espeakCHARS_WCHAR = 3,
        espeakCHARS_16BIT = 4
    } espeak_POSITION_TYPE;

    typedef enum {
        espeakPHONEMES_DEFAULT = 0x00,
        espeakPHONEMES_SHOW = 0x01,
        espeakPHONEMES_IPA = 0x02,
        espeakPHONEMES_TRACE = 0x08,
        espeakPHONEMES_MBROLA = 0x10,
        espeakPHONEMES_ARPABET = 0x20,
        espeakPHONEMES_TIE = 0x80
    } espeak_PHONEME_TYPE;

    int espeak_Initialize(int output, int buflength, const char *path, int options);
    void espeak_Terminate();
    int espeak_SetVoiceByName(const char *name);
    const char *espeak_TextToPhonemes(const void **textptr, int textmode, int phonememode);
}

// Language detection
enum class Language {
    JAPANESE,
    ENGLISH,
    OTHER
};

Language detectLanguage(const std::string& text) {
    // Simple language detection based on character ranges
    bool hasJapanese = false;
    bool hasEnglish = false;
    
    for (const char& c : text) {
        unsigned char uc = static_cast<unsigned char>(c);
        
        // Check for Japanese characters (simplified)
        if (uc >= 0x80) {
            // Multi-byte character, could be Japanese
            hasJapanese = true;
        } else if ((uc >= 'A' && uc <= 'Z') || (uc >= 'a' && uc <= 'z')) {
            hasEnglish = true;
        }
    }
    
    if (hasJapanese) {
        return Language::JAPANESE;
    } else if (hasEnglish) {
        return Language::ENGLISH;
    }
    
    return Language::OTHER;
}

// Exported functions
extern "C" {

EMSCRIPTEN_KEEPALIVE
int phonemizer_initialize_openjtalk(const char* dict_dir) {
    return openjtalk_initialize(dict_dir);
}

EMSCRIPTEN_KEEPALIVE
int phonemizer_initialize_espeak(const char* data_path) {
    // Initialize eSpeak-ng
    int result = espeak_Initialize(0, 0, data_path, 0);
    if (result < 0) {
        return result;
    }
    
    // Set default English voice
    espeak_SetVoiceByName("en");
    return 0;
}

EMSCRIPTEN_KEEPALIVE
char* phonemizer_text_to_phonemes(const char* text, const char* language_hint) {
    if (!text || strlen(text) == 0) {
        return strdup("ERROR: Empty text");
    }
    
    Language lang = Language::ENGLISH;
    
    // Use language hint if provided
    if (language_hint && strlen(language_hint) > 0) {
        if (strcmp(language_hint, "ja") == 0 || strcmp(language_hint, "japanese") == 0) {
            lang = Language::JAPANESE;
        } else if (strcmp(language_hint, "en") == 0 || strcmp(language_hint, "english") == 0) {
            lang = Language::ENGLISH;
        }
    } else {
        // Auto-detect language
        lang = detectLanguage(text);
    }
    
    if (lang == Language::JAPANESE) {
        // Use OpenJTalk for Japanese
        return openjtalk_synthesis_labels(text);
    } else {
        // Use eSpeak-ng for English and other languages
        const char* textptr = text;
        const char* phonemes = espeak_TextToPhonemes(
            (const void**)&textptr, 
            espeakCHARS_UTF8, 
            espeakPHONEMES_IPA
        );
        
        if (phonemes) {
            return strdup(phonemes);
        } else {
            return strdup("ERROR: Failed to generate phonemes");
        }
    }
}

EMSCRIPTEN_KEEPALIVE
void phonemizer_set_language(const char* language) {
    if (!language) return;
    
    if (strcmp(language, "en") == 0 || strcmp(language, "en-us") == 0) {
        espeak_SetVoiceByName("en");
    } else if (strcmp(language, "en-gb") == 0) {
        espeak_SetVoiceByName("en-gb");
    } else if (strcmp(language, "de") == 0) {
        espeak_SetVoiceByName("de");
    } else if (strcmp(language, "fr") == 0) {
        espeak_SetVoiceByName("fr");
    } else if (strcmp(language, "es") == 0) {
        espeak_SetVoiceByName("es");
    }
    // Japanese is handled by OpenJTalk, no voice setting needed
}

EMSCRIPTEN_KEEPALIVE
void phonemizer_free_string(char* str) {
    if (str) {
        free(str);
    }
}

EMSCRIPTEN_KEEPALIVE
void phonemizer_terminate() {
    openjtalk_clear();
    espeak_Terminate();
}

} // extern "C"