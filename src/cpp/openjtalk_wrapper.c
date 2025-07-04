#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>

#ifdef _WIN32
#include <windows.h>
#include <io.h>
#define F_OK 0
#define access _access
#define popen _popen
#define pclose _pclose
#define unlink _unlink
#else
#include <unistd.h>
#endif

#include "openjtalk_dictionary_manager.h"

// Global variable to store OpenJTalk binary path
static char g_openjtalk_bin_path[1024] = {0};

// Forward declaration
static void katakana_to_phonemes(const char* katakana, char* phonemes_out);

// Find OpenJTalk binary path
static const char* find_openjtalk_binary() {
    if (g_openjtalk_bin_path[0] != 0) {
        return g_openjtalk_bin_path;
    }
    
    // Check if open_jtalk binary exists
    const char* paths[] = {
#ifdef _WIN32
        "open_jtalk.exe",
        "bin\\open_jtalk.exe",
        ".\\open_jtalk.exe",
        "..\\bin\\open_jtalk.exe",
        "piper\\bin\\open_jtalk.exe",
#else
        "./open_jtalk",
        "./bin/open_jtalk",
        "../bin/open_jtalk",
        "./piper/bin/open_jtalk",
        "/usr/bin/open_jtalk",
        "/usr/local/bin/open_jtalk",
#endif
        NULL
    };
    
    for (int i = 0; paths[i] != NULL; i++) {
        if (access(paths[i], F_OK) == 0) {
            strcpy(g_openjtalk_bin_path, paths[i]);
            return g_openjtalk_bin_path;
        }
    }
    
    // Try to find in PATH
#ifdef _WIN32
    FILE* fp = popen("where open_jtalk.exe 2>NUL", "r");
#else
    FILE* fp = popen("which open_jtalk 2>/dev/null", "r");
#endif
    if (fp) {
        if (fgets(g_openjtalk_bin_path, sizeof(g_openjtalk_bin_path), fp) != NULL) {
            // Remove newline
            size_t len = strlen(g_openjtalk_bin_path);
            if (len > 0 && g_openjtalk_bin_path[len-1] == '\n') {
                g_openjtalk_bin_path[len-1] = '\0';
            }
            pclose(fp);
            return g_openjtalk_bin_path;
        }
        pclose(fp);
    }
    
    return NULL;
}

// Check if OpenJTalk binary is available
bool openjtalk_is_available() {
    return find_openjtalk_binary() != NULL;
}

// Ensure OpenJTalk dictionary is available
bool openjtalk_ensure_dictionary() {
    return ensure_openjtalk_dictionary() == 0;
}

// Convert text to phonemes using OpenJTalk
char* openjtalk_text_to_phonemes(const char* text) {
    if (!text || strlen(text) == 0) {
        return NULL;
    }
    
    // Get dictionary path
    const char* dic_path = get_openjtalk_dictionary_path();
    if (!dic_path) {
        fprintf(stderr, "Failed to get OpenJTalk dictionary path\n");
        return NULL;
    }
    
    // Create temporary files
    char input_file[256];
    char output_file[256];
    
#ifdef _WIN32
    // Windows doesn't have mkstemp, use tmpnam
    char* temp_dir = getenv("TEMP");
    if (!temp_dir) temp_dir = getenv("TMP");
    if (!temp_dir) temp_dir = ".";
    
    sprintf(input_file, "%s\\openjtalk_input_%d.txt", temp_dir, GetCurrentProcessId());
    sprintf(output_file, "%s\\openjtalk_output_%d.txt", temp_dir, GetCurrentProcessId());
#else
    strcpy(input_file, "/tmp/openjtalk_input_XXXXXX");
    strcpy(output_file, "/tmp/openjtalk_output_XXXXXX");
    
    int fd = mkstemp(input_file);
    if (fd == -1) return NULL;
    close(fd);
    
    fd = mkstemp(output_file);
    if (fd == -1) {
        unlink(input_file);
        return NULL;
    }
    close(fd);
#endif
    
    // Write input text to file
    FILE* fp = fopen(input_file, "w");
    if (!fp) {
        unlink(input_file);
        unlink(output_file);
        return NULL;
    }
    fprintf(fp, "%s", text);
    fclose(fp);
    
    // Get OpenJTalk binary path
    const char* openjtalk_bin = find_openjtalk_binary();
    if (!openjtalk_bin) {
        unlink(input_file);
        unlink(output_file);
        return NULL;
    }
    
    // Get HTS voice path
    const char* voice_path = get_openjtalk_voice_path();
    if (!voice_path) {
        unlink(input_file);
        unlink(output_file);
        return NULL;
    }
    
    // Construct OpenJTalk command
    // Use -ow /dev/null to suppress wave output and -ot to get trace/phoneme output
    char command[4096];
#ifdef _WIN32
    // Use cmd /c to ensure proper command execution on Windows
    snprintf(command, sizeof(command),
             "cmd /c \"\"%s\" -x \"%s\" -m \"%s\" -ow NUL -ot \"%s\" \"%s\"\"",
             openjtalk_bin, dic_path, voice_path, output_file, input_file);
#else
    snprintf(command, sizeof(command),
             "\"%s\" -x \"%s\" -m \"%s\" -ow /dev/null -ot \"%s\" \"%s\"",
             openjtalk_bin, dic_path, voice_path, output_file, input_file);
#endif
    
    // Debug: Print command
    fprintf(stderr, "Executing OpenJTalk command: %s\n", command);
    
    // Execute OpenJTalk
    int result = system(command);
    
    // Clean up input file
    unlink(input_file);
    
    if (result != 0) {
        fprintf(stderr, "OpenJTalk command failed with code: %d\n", result);
        unlink(output_file);
        return NULL;
    }
    
    // Read trace output file
    fp = fopen(output_file, "r");
    if (!fp) {
        fprintf(stderr, "Failed to open output file: %s\n", output_file);
        unlink(output_file);
        return NULL;
    }
    
    // Debug: Check file size
    fseek(fp, 0, SEEK_END);
    long file_size = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    fprintf(stderr, "Output file size: %ld bytes\n", file_size);
    
    // Allocate buffer based on file size
    char* file_content = malloc(file_size + 1);
    if (!file_content) {
        fclose(fp);
        unlink(output_file);
        return NULL;
    }
    
    // Read entire file
    size_t read_size = fread(file_content, 1, file_size, fp);
    file_content[read_size] = '\0';
    fclose(fp);
    
    // Allocate buffer for phonemes
    char* phonemes = malloc(4096);
    if (!phonemes) {
        free(file_content);
        unlink(output_file);
        return NULL;
    }
    
    phonemes[0] = '\0';
    
    // Parse morphological analysis output to extract katakana readings
    char* line = strtok(file_content, "\n");
    int in_text_analysis = 0;
    
    while (line != NULL) {
        // Debug: Print first few lines
        static int debug_line_count = 0;
        if (debug_line_count++ < 10) {
            fprintf(stderr, "Debug line: %s\n", line);
        }
        
        // Check for text analysis section
        if (strstr(line, "[Text analysis result]") != NULL) {
            in_text_analysis = 1;
            line = strtok(NULL, "\n");
            continue;
        }
        
        // Check for end of text analysis section
        if (in_text_analysis && line[0] == '[') {
            break;
        }
        
        if (in_text_analysis && strlen(line) > 0) {
            // Parse MeCab format: surface,pos1,pos2,...,base,reading,pronunciation,...
            // We want the katakana reading (9th field)
            char line_copy[1024];
            strncpy(line_copy, line, sizeof(line_copy) - 1);
            line_copy[sizeof(line_copy) - 1] = '\0';
            
            char* fields[20];
            int field_count = 0;
            char* save_ptr = NULL;
            
#ifdef _WIN32
            char* field = strtok_s(line_copy, ",", &save_ptr);
            
            while (field != NULL && field_count < 20) {
                fields[field_count++] = field;
                field = strtok_s(NULL, ",", &save_ptr);
            }
#else
            char* field = strtok_r(line_copy, ",", &save_ptr);
            
            while (field != NULL && field_count < 20) {
                fields[field_count++] = field;
                field = strtok_r(NULL, ",", &save_ptr);
            }
#endif
            
            // Get katakana reading (typically 9th field, index 8)
            if (field_count >= 9) {
                char* reading = fields[8];
                // Skip punctuation marks
                if (strcmp(reading, "、") != 0 && 
                    strcmp(reading, "。") != 0 && 
                    strcmp(reading, "*") != 0) {
                    // Convert katakana to phonemes
                    char phoneme_buffer[256];
                    katakana_to_phonemes(reading, phoneme_buffer);
                    
                    if (strlen(phoneme_buffer) > 0) {
                        if (strlen(phonemes) > 0) {
                            strcat(phonemes, " ");
                        }
                        strcat(phonemes, phoneme_buffer);
                    }
                }
            }
        }
        
        line = strtok(NULL, "\n");
    }
    
    fprintf(stderr, "Phonemes extracted: %s\n", phonemes);
    
    free(file_content);
    unlink(output_file);
    
    if (strlen(phonemes) == 0) {
        free(phonemes);
        return NULL;
    }
    
    return phonemes;
}

// Convert katakana to phoneme symbols
static void katakana_to_phonemes(const char* katakana, char* phonemes_out) {
    // Katakana to phoneme mapping table
    static const struct {
        const char* katakana;
        const char* phoneme;
    } katakana_map[] = {
        // Basic katakana
        {"ア", "a"}, {"イ", "i"}, {"ウ", "u"}, {"エ", "e"}, {"オ", "o"},
        {"カ", "k a"}, {"キ", "k i"}, {"ク", "k u"}, {"ケ", "k e"}, {"コ", "k o"},
        {"ガ", "g a"}, {"ギ", "g i"}, {"グ", "g u"}, {"ゲ", "g e"}, {"ゴ", "g o"},
        {"サ", "s a"}, {"シ", "t͡ɕ i"}, {"ス", "s u"}, {"セ", "s e"}, {"ソ", "s o"},
        {"ザ", "z a"}, {"ジ", "d͡ʑ i"}, {"ズ", "z u"}, {"ゼ", "z e"}, {"ゾ", "z o"},
        {"タ", "t a"}, {"チ", "t͡ɕ i"}, {"ツ", "t͡s u"}, {"テ", "t e"}, {"ト", "t o"},
        {"ダ", "d a"}, {"ヂ", "d͡ʑ i"}, {"ヅ", "d͡z u"}, {"デ", "d e"}, {"ド", "d o"},
        {"ナ", "n a"}, {"ニ", "ɲ i"}, {"ヌ", "n u"}, {"ネ", "n e"}, {"ノ", "n o"},
        {"ハ", "h a"}, {"ヒ", "ç i"}, {"フ", "f u"}, {"ヘ", "h e"}, {"ホ", "h o"},
        {"バ", "b a"}, {"ビ", "b i"}, {"ブ", "b u"}, {"ベ", "b e"}, {"ボ", "b o"},
        {"パ", "p a"}, {"ピ", "p i"}, {"プ", "p u"}, {"ペ", "p e"}, {"ポ", "p o"},
        {"マ", "m a"}, {"ミ", "m i"}, {"ム", "m u"}, {"メ", "m e"}, {"モ", "m o"},
        {"ヤ", "y a"}, {"ユ", "y u"}, {"ヨ", "y o"},
        {"ラ", "r a"}, {"リ", "r i"}, {"ル", "r u"}, {"レ", "r e"}, {"ロ", "r o"},
        {"ワ", "w a"}, {"ヰ", "w i"}, {"ヱ", "w e"}, {"ヲ", "w o"},
        {"ン", "N"},
        // Small katakana
        {"ッ", "q"},
        {"ャ", "y a"}, {"ュ", "y u"}, {"ョ", "y o"},
        {"ァ", "a"}, {"ィ", "i"}, {"ゥ", "u"}, {"ェ", "e"}, {"ォ", "o"},
        // Long vowel mark
        {"ー", ":"}, // This will be processed specially
        {NULL, NULL}
    };
    
    const char* input = katakana;
    char* output = phonemes_out;
    output[0] = '\0';
    
    while (*input) {
        int matched = 0;
        
        // Check for long vowel mark
        if (strncmp(input, "ー", 3) == 0) {
            // Long vowel mark - extend the previous vowel
            if (output > phonemes_out && output[-1] == ' ') {
                output--; // Remove trailing space
            }
            if (output > phonemes_out) {
                // Find the last vowel and make it long
                char* last_vowel = output - 1;
                while (last_vowel > phonemes_out && *last_vowel != ' ') {
                    last_vowel--;
                }
                if (*last_vowel == ' ') last_vowel++;
                
                // Add long vowel marker based on the last vowel
                if (*last_vowel == 'a') strcat(output, " ã");
                else if (*last_vowel == 'i') strcat(output, " ĩ");
                else if (*last_vowel == 'u') strcat(output, " ũ");
                else if (*last_vowel == 'e') strcat(output, " ẽ");
                else if (*last_vowel == 'o') strcat(output, " õ");
                output = output + strlen(output);
            }
            input += 3;
            matched = 1;
        }
        
        // Try to match katakana
        if (!matched) {
            for (int i = 0; katakana_map[i].katakana != NULL; i++) {
                int kana_len = strlen(katakana_map[i].katakana);
                if (strncmp(input, katakana_map[i].katakana, kana_len) == 0) {
                    if (output > phonemes_out) {
                        strcat(output, " ");
                        output++;
                    }
                    strcat(output, katakana_map[i].phoneme);
                    output += strlen(katakana_map[i].phoneme);
                    input += kana_len;
                    matched = 1;
                    break;
                }
            }
        }
        
        // Skip unrecognized characters
        if (!matched) {
            // Move to next UTF-8 character
            if ((*input & 0x80) == 0) {
                input++; // ASCII
            } else if ((*input & 0xE0) == 0xC0) {
                input += 2; // 2-byte UTF-8
            } else if ((*input & 0xF0) == 0xE0) {
                input += 3; // 3-byte UTF-8
            } else if ((*input & 0xF8) == 0xF0) {
                input += 4; // 4-byte UTF-8
            } else {
                input++; // Invalid, skip
            }
        }
    }
}

// Free phoneme string
void openjtalk_free_phonemes(char* phonemes) {
    if (phonemes) {
        free(phonemes);
    }
}