#include "openjtalk_api.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Include the individual OpenJTalk component headers
#include "text2mecab.h"
#include "mecab.h"
#include "njd.h"  
#include "jpcommon.h"
#include "mecab2njd.h"
#include "njd2jpcommon.h"
#include "njd_set_pronunciation.h"
#include "njd_set_digit.h"
#include "njd_set_accent_phrase.h"
#include "njd_set_accent_type.h"
#include "njd_set_long_vowel.h"
#include "njd_set_unvoiced_vowel.h"
#include "openjtalk_dictionary_manager.h"

// ============================================================================
// pyopenjtalk-plus compatibility: Python-level NJD post-processing ported to C
//
// pyopenjtalk-plus applies additional rules before/after the C-level NJD
// pipeline. Without these, fullcontext labels differ between C++ and Python.
// See: https://github.com/tsukumijima/pyopenjtalk-plus
// ============================================================================

// UTF-8 string constants for Japanese text comparisons
#define U8_SAHEN_SETSUZOKU   "\xe3\x82\xb5\xe5\xa4\x89\xe6\x8e\xa5\xe7\xb6\x9a"           /* サ変接続 */
#define U8_KAKUJOSHI         "\xe6\xa0\xbc\xe5\x8a\xa9\xe8\xa9\x9e"                         /* 格助詞 */
#define U8_SETSUZOKUJOSHI    "\xe6\x8e\xa5\xe7\xb6\x9a\xe5\x8a\xa9\xe8\xa9\x9e"           /* 接続助詞 */
#define U8_MEISHI            "\xe5\x90\x8d\xe8\xa9\x9e"                                     /* 名詞 */
#define U8_IPPAN             "\xe4\xb8\x80\xe8\x88\xac"                                     /* 一般 */
#define U8_FUKUSHI           "\xe5\x89\xaf\xe8\xa9\x9e"                                     /* 副詞 */
#define U8_SAHEN_SURU        "\xe3\x82\xb5\xe5\xa4\x89\xe3\x83\xbb\xe3\x82\xb9\xe3\x83\xab" /* サ変・スル */
#define U8_O                 "\xe3\x81\x8a"                                                 /* お */
#define U8_ON                "\xe5\xbe\xa1"                                                 /* 御 */
#define U8_GO                "\xe3\x81\x94"                                                 /* ご */
#define U8_P1                "P1"
#define U8_C1                "C1"
#define U8_C4                "C4"
#define U8_DOUSHI            "\xe5\x8b\x95\xe8\xa9\x9e"                                     /* 動詞 */
#define U8_RENYOU            "\xe9\x80\xa3\xe7\x94\xa8"                                     /* 連用 (prefix) */
#define U8_RERU              "\xe3\x82\x8c\xe3\x82\x8b"                                     /* れる */
#define U8_RARERU            "\xe3\x82\x89\xe3\x82\x8c\xe3\x82\x8b"                         /* られる */
#define U8_SERU              "\xe3\x81\x9b\xe3\x82\x8b"                                     /* せる */
#define U8_SASERU            "\xe3\x81\x95\xe3\x81\x9b\xe3\x82\x8b"                         /* させる */
#define U8_CHAU              "\xe3\x81\xa1\xe3\x82\x83\xe3\x81\x86"                         /* ちゃう */
#define U8_TA                "\xe3\x81\x9f"                                                 /* た */
#define U8_F2_AT_1           "F2@1"
#define U8_KEIYOUSHI         "\xe5\xbd\xa2\xe5\xae\xb9\xe8\xa9\x9e"                         /* 形容詞 */
#define U8_NARU              "\xe3\x81\xaa\xe3\x82\x8b"                                     /* なる */
#define U8_SURU              "\xe3\x81\x99\xe3\x82\x8b"                                     /* する */
#define U8_TOKUSHU_MASU      "\xe7\x89\xb9\xe6\xae\x8a\xe3\x83\xbb\xe3\x83\x9e\xe3\x82\xb9" /* 特殊・マス */
#define U8_TOKUSHU_NAI       "\xe7\x89\xb9\xe6\xae\x8a\xe3\x83\xbb\xe3\x83\x8a\xe3\x82\xa4" /* 特殊・ナイ */
#define U8_MIZENKEI          "\xe6\x9c\xaa\xe7\x84\xb6\xe5\xbd\xa2"                         /* 未然形 */
#define U8_SUGIRU            "\xe3\x81\x99\xe3\x81\x8e\xe3\x82\x8b"                         /* すぎる */

// Length of UTF-8 "連用" prefix (2 kanji × 3 bytes each)
#define U8_RENYOU_LEN 6

/**
 * Port of pyopenjtalk-plus's apply_original_rule_before_chaining().
 * Called after njd_set_pronunciation, before njd_set_digit.
 *
 * Rules applied:
 * 1. サ変接続/格助詞/接続助詞/名詞一般/副詞 + サ変・スル → chain_flag=1
 * 2. 接頭語(お/御/ご) P1 → adjust chain_rule and acc
 * 3. 動詞+動詞連続 → set chain_rule to C1/C4
 * 4. 連用形の acc 修正 (acc == mora_size > 1 → acc--)
 * 5. れる/られる/せる/させる/ちゃう + た → F2@1
 * 6. 形容詞 + なる/する → chain_flag=1
 */
static void apply_original_rule_before_chaining(NJD* njd) {
    NJDNode* node;
    for (node = njd->head; node != NULL && node->next != NULL; node = node->next) {
        NJDNode* next = node->next;
        const char* pos = NJDNode_get_pos(node);
        const char* pos_group1 = NJDNode_get_pos_group1(node);
        const char* next_ctype = NJDNode_get_ctype(next);

        /* Rule 1: サ変動詞の前にサ変接続等が来た場合は一つのアクセント句に */
        if ((strcmp(pos_group1, U8_SAHEN_SETSUZOKU) == 0 ||
             strcmp(pos_group1, U8_KAKUJOSHI) == 0 ||
             strcmp(pos_group1, U8_SETSUZOKUJOSHI) == 0 ||
             (strcmp(pos, U8_MEISHI) == 0 && strcmp(pos_group1, U8_IPPAN) == 0) ||
             strcmp(pos, U8_FUKUSHI) == 0) &&
            strcmp(next_ctype, U8_SAHEN_SURU) == 0) {
            NJDNode_set_chain_flag(next, 1);
        }

        /* Rule 2: 接頭語(お/御/ご)のchain_rule調整 */
        {
            const char* str = NJDNode_get_string(node);
            const char* chain_rule = NJDNode_get_chain_rule(node);
            if ((strcmp(str, U8_O) == 0 || strcmp(str, U8_ON) == 0 || strcmp(str, U8_GO) == 0) &&
                strcmp(chain_rule, U8_P1) == 0) {
                int next_acc = NJDNode_get_acc(next);
                int next_mora = NJDNode_get_mora_size(next);
                if (next_acc == 0 || next_acc == next_mora) {
                    NJDNode_set_chain_rule(next, U8_C4);
                    NJDNode_set_acc(next, 0);
                } else {
                    NJDNode_set_chain_rule(next, U8_C1);
                }
            }
        }

        /* Rule 3: 動詞が連続する場合、後ろの動詞のchain_ruleを設定 */
        {
            const char* next_pos = NJDNode_get_pos(next);
            if (strcmp(pos, U8_DOUSHI) == 0 && strcmp(next_pos, U8_DOUSHI) == 0) {
                int next_acc = NJDNode_get_acc(next);
                NJDNode_set_chain_rule(next, next_acc != 0 ? U8_C1 : U8_C4);
            }
        }

        /* Rule 4: 連用形のアクセント核修正 (acc == mora_size && mora_size > 1) */
        {
            const char* cform = NJDNode_get_cform(node);
            int acc = NJDNode_get_acc(node);
            int mora = NJDNode_get_mora_size(node);
            if (strncmp(cform, U8_RENYOU, U8_RENYOU_LEN) == 0 && acc == mora && mora > 1) {
                NJDNode_set_acc(node, acc - 1);
            }
        }

        /* Rule 5: れる/られる/せる/させる/ちゃう + た → F2@1 */
        {
            const char* orig = NJDNode_get_orig(node);
            const char* next_str = NJDNode_get_string(next);
            if ((strcmp(orig, U8_RERU) == 0 || strcmp(orig, U8_RARERU) == 0 ||
                 strcmp(orig, U8_SERU) == 0 || strcmp(orig, U8_SASERU) == 0 ||
                 strcmp(orig, U8_CHAU) == 0) &&
                strcmp(next_str, U8_TA) == 0) {
                NJDNode_set_chain_rule(next, U8_F2_AT_1);
            }
        }

        /* Rule 6: 形容詞 + なる/する → chain_flag=1 */
        {
            const char* next_orig = NJDNode_get_orig(next);
            if (strcmp(pos, U8_KEIYOUSHI) == 0 &&
                (strcmp(next_orig, U8_NARU) == 0 || strcmp(next_orig, U8_SURU) == 0)) {
                NJDNode_set_chain_flag(next, 1);
            }
        }
    }
}

/**
 * Port of pyopenjtalk-plus's modify_acc_after_chaining().
 * Called after the full NJD pipeline, before njd2jpcommon.
 *
 * Adjusts accent position when 特殊・マス follows an accented phrase head.
 * Example: 読みます → accent moves from mora 1 to mora 3 (ま)
 */
static void modify_acc_after_chaining(NJD* njd) {
    if (!njd->head) return;

    int acc = 0;
    int is_after_nuc = 0;
    int phase_len = 0;
    NJDNode* head = njd->head;

    NJDNode* node;
    for (node = njd->head; node != NULL; node = node->next) {
        int chain_flag = NJDNode_get_chain_flag(node);

        /* New accent phrase boundary */
        if (chain_flag == 0 || chain_flag == -1) {
            is_after_nuc = 0;
            head = node;
            acc = NJDNode_get_acc(node);
            phase_len = 0;
        }

        if (acc == 0) {
            continue;
        } else if (is_after_nuc) {
            const char* ctype = NJDNode_get_ctype(node);
            const char* cform = NJDNode_get_cform(node);
            const char* orig = NJDNode_get_orig(node);
            int mora = NJDNode_get_mora_size(node);

            if (strcmp(ctype, U8_TOKUSHU_MASU) == 0) {
                /* 特殊・マス: accent nucleus moves to ま */
                if (strcmp(cform, U8_MIZENKEI) != 0) {
                    NJDNode_set_acc(head, phase_len + 1);
                } else {
                    NJDNode_set_acc(head, phase_len + 2);
                }
            } else if (strcmp(ctype, U8_TOKUSHU_NAI) == 0) {
                /* 特殊・ナイ: accent stays at boundary */
                NJDNode_set_acc(head, phase_len);
            } else if (strcmp(orig, U8_RERU) == 0 || strcmp(orig, U8_RARERU) == 0 ||
                       strcmp(orig, U8_SUGIRU) == 0 ||
                       strcmp(orig, U8_SERU) == 0 || strcmp(orig, U8_SASERU) == 0) {
                /* Passive/causative/sugiru: add original accent offset */
                NJDNode_set_acc(head, phase_len + NJDNode_get_acc(node));
            } else {
                is_after_nuc = 0;
                acc = 0;
            }
            phase_len += mora;
        } else {
            int mora = NJDNode_get_mora_size(node);
            phase_len += mora;
            if (acc <= mora) {
                is_after_nuc = 1;
            } else {
                acc = acc - mora;
            }
        }
    }
}

// OpenJTalk wrapper structure
struct _OpenJTalk {
    Mecab mecab;
    NJD njd;
    JPCommon jpcommon;
    int initialized;
};

// HTS Label wrapper structure that holds JPCommon labels
struct _HTS_Label {
    JPCommon* jpcommon;
    int size;
};

OpenJTalk* openjtalk_initialize() {
    OpenJTalk* oj = (OpenJTalk*)malloc(sizeof(OpenJTalk));
    if (!oj) return NULL;
    
    oj->initialized = 0;
    
    // Initialize MeCab
    Mecab_initialize(&oj->mecab);
    
    // Initialize NJD
    NJD_initialize(&oj->njd);
    
    // Initialize JPCommon
    JPCommon_initialize(&oj->jpcommon);
    
    // Load MeCab dictionary
    const char* dic_path = get_openjtalk_dictionary_path();
    if (!dic_path) {
        fprintf(stderr, "Failed to get OpenJTalk dictionary path\n");
        openjtalk_finalize(oj);
        return NULL;
    }
    
    if (Mecab_load(&oj->mecab, dic_path) != TRUE) {
        fprintf(stderr, "Failed to load MeCab dictionary from %s\n", dic_path);
        openjtalk_finalize(oj);
        return NULL;
    }
    
    oj->initialized = 1;
    return oj;
}

void openjtalk_finalize(OpenJTalk* oj) {
    if (!oj) return;
    
    if (oj->initialized) {
        JPCommon_clear(&oj->jpcommon);
        NJD_clear(&oj->njd);
        Mecab_clear(&oj->mecab);
    }
    
    free(oj);
}

HTS_Label* openjtalk_extract_fullcontext(OpenJTalk* oj, const char* text) {
    if (!oj || !oj->initialized || !text) return NULL;
    
    // Allocate buffer for MeCab output (estimate size)
    size_t text_len = strlen(text);
    size_t buffer_size = text_len * 10; // Generous estimate for MeCab output
    char* mecab_output = (char*)malloc(buffer_size);
    if (!mecab_output) return NULL;
    
    // Convert text to MeCab format
    text2mecab(mecab_output, buffer_size, text);
    
    // Clear previous analysis
    NJD_clear(&oj->njd);
    NJD_initialize(&oj->njd);
    
    // Analyze with MeCab
    Mecab_analysis(&oj->mecab, mecab_output);
    
    // Convert MeCab output to NJD
    mecab2njd(&oj->njd, Mecab_get_feature(&oj->mecab), Mecab_get_size(&oj->mecab));
    
    // Process through NJD stages (matching pyopenjtalk-plus pipeline order)
    njd_set_pronunciation(&oj->njd);

    // pyopenjtalk-plus pre-processing: modify chain_flag/chain_rule/acc
    // before the standard accent phrase rules run
    apply_original_rule_before_chaining(&oj->njd);

    njd_set_digit(&oj->njd);
    njd_set_accent_phrase(&oj->njd);
    njd_set_accent_type(&oj->njd);
    njd_set_unvoiced_vowel(&oj->njd);
    njd_set_long_vowel(&oj->njd);

    // pyopenjtalk-plus post-processing: adjust accent positions
    // for マス/ナイ/passive/causative after chaining
    modify_acc_after_chaining(&oj->njd);

    // Clear previous JPCommon analysis
    JPCommon_refresh(&oj->jpcommon);

    // Convert to JPCommon
    njd2jpcommon(&oj->jpcommon, &oj->njd);
    
    // Make full-context labels
    JPCommon_make_label(&oj->jpcommon);
    
    // Create HTS_Label wrapper
    HTS_Label* label = (HTS_Label*)malloc(sizeof(HTS_Label));
    if (!label) {
        free(mecab_output);
        return NULL;
    }
    
    label->jpcommon = &oj->jpcommon;
    label->size = JPCommon_get_label_size(&oj->jpcommon);
    
    free(mecab_output);
    return label;
}

size_t HTS_Label_get_size(HTS_Label* label) {
    if (!label) return 0;
    return label->size;
}

const char* HTS_Label_get_string(HTS_Label* label, size_t index) {
    if (!label || !label->jpcommon || index >= label->size) return NULL;
    
    char** features = JPCommon_get_label_feature(label->jpcommon);
    if (!features) return NULL;
    
    return features[index];
}

void HTS_Label_clear(HTS_Label* label) {
    if (!label) return;
    // JPCommon cleanup is handled by openjtalk_finalize
    // Don't free the JPCommon here as it's owned by OpenJTalk
    free(label);
}