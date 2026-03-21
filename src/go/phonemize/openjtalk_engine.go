//go:build openjtalk

package phonemize

/*
#cgo LDFLAGS: -lopenjtalk -lstdc++ -lm

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// OpenJTalk component headers (from build/oj/include/openjtalk/)
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

// ============================================================================
// pyopenjtalk-plus compatibility rules (ported from openjtalk_api.c)
// ============================================================================

#define U8_SAHEN_SETSUZOKU   "\xe3\x82\xb5\xe5\xa4\x89\xe6\x8e\xa5\xe7\xb6\x9a"
#define U8_KAKUJOSHI         "\xe6\xa0\xbc\xe5\x8a\xa9\xe8\xa9\x9e"
#define U8_SETSUZOKUJOSHI    "\xe6\x8e\xa5\xe7\xb6\x9a\xe5\x8a\xa9\xe8\xa9\x9e"
#define U8_MEISHI            "\xe5\x90\x8d\xe8\xa9\x9e"
#define U8_IPPAN             "\xe4\xb8\x80\xe8\x88\xac"
#define U8_FUKUSHI           "\xe5\x89\xaf\xe8\xa9\x9e"
#define U8_SAHEN_SURU        "\xe3\x82\xb5\xe5\xa4\x89\xe3\x83\xbb\xe3\x82\xb9\xe3\x83\xab"
#define U8_O                 "\xe3\x81\x8a"
#define U8_ON                "\xe5\xbe\xa1"
#define U8_GO                "\xe3\x81\x94"
#define U8_P1                "P1"
#define U8_C1                "C1"
#define U8_C4                "C4"
#define U8_DOUSHI            "\xe5\x8b\x95\xe8\xa9\x9e"
#define U8_RENYOU            "\xe9\x80\xa3\xe7\x94\xa8"
#define U8_RERU              "\xe3\x82\x8c\xe3\x82\x8b"
#define U8_RARERU            "\xe3\x82\x89\xe3\x82\x8c\xe3\x82\x8b"
#define U8_SERU              "\xe3\x81\x9b\xe3\x82\x8b"
#define U8_SASERU            "\xe3\x81\x95\xe3\x81\x9b\xe3\x82\x8b"
#define U8_CHAU              "\xe3\x81\xa1\xe3\x82\x83\xe3\x81\x86"
#define U8_TA                "\xe3\x81\x9f"
#define U8_F2_AT_1           "F2@1"
#define U8_KEIYOUSHI         "\xe5\xbd\xa2\xe5\xae\xb9\xe8\xa9\x9e"
#define U8_NARU              "\xe3\x81\xaa\xe3\x82\x8b"
#define U8_SURU              "\xe3\x81\x99\xe3\x82\x8b"
#define U8_TOKUSHU_MASU      "\xe7\x89\xb9\xe6\xae\x8a\xe3\x83\xbb\xe3\x83\x9e\xe3\x82\xb9"
#define U8_TOKUSHU_NAI       "\xe7\x89\xb9\xe6\xae\x8a\xe3\x83\xbb\xe3\x83\x8a\xe3\x82\xa4"
#define U8_MIZENKEI          "\xe6\x9c\xaa\xe7\x84\xb6\xe5\xbd\xa2"
#define U8_SUGIRU            "\xe3\x81\x99\xe3\x81\x8e\xe3\x82\x8b"
#define U8_RENYOU_LEN 6

static void apply_original_rule_before_chaining(NJD* njd) {
    NJDNode* node;
    for (node = njd->head; node != NULL && node->next != NULL; node = node->next) {
        NJDNode* next = node->next;
        const char* pos = NJDNode_get_pos(node);
        const char* pos_group1 = NJDNode_get_pos_group1(node);
        const char* next_ctype = NJDNode_get_ctype(next);

        if ((strcmp(pos_group1, U8_SAHEN_SETSUZOKU) == 0 ||
             strcmp(pos_group1, U8_KAKUJOSHI) == 0 ||
             strcmp(pos_group1, U8_SETSUZOKUJOSHI) == 0 ||
             (strcmp(pos, U8_MEISHI) == 0 && strcmp(pos_group1, U8_IPPAN) == 0) ||
             strcmp(pos, U8_FUKUSHI) == 0) &&
            strcmp(next_ctype, U8_SAHEN_SURU) == 0) {
            NJDNode_set_chain_flag(next, 1);
        }

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

        {
            const char* next_pos = NJDNode_get_pos(next);
            if (strcmp(pos, U8_DOUSHI) == 0 && strcmp(next_pos, U8_DOUSHI) == 0) {
                int next_acc = NJDNode_get_acc(next);
                NJDNode_set_chain_rule(next, next_acc != 0 ? U8_C1 : U8_C4);
            }
        }

        {
            const char* cform = NJDNode_get_cform(node);
            int acc = NJDNode_get_acc(node);
            int mora = NJDNode_get_mora_size(node);
            if (strncmp(cform, U8_RENYOU, U8_RENYOU_LEN) == 0 && acc == mora && mora > 1) {
                NJDNode_set_acc(node, acc - 1);
            }
        }

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

        {
            const char* next_orig = NJDNode_get_orig(next);
            if (strcmp(pos, U8_KEIYOUSHI) == 0 &&
                (strcmp(next_orig, U8_NARU) == 0 || strcmp(next_orig, U8_SURU) == 0)) {
                NJDNode_set_chain_flag(next, 1);
            }
        }
    }
}

static void modify_acc_after_chaining(NJD* njd) {
    if (!njd->head) return;
    int acc = 0;
    int is_after_nuc = 0;
    int phase_len = 0;
    NJDNode* head = njd->head;
    NJDNode* node;
    for (node = njd->head; node != NULL; node = node->next) {
        int chain_flag = NJDNode_get_chain_flag(node);
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
                if (strcmp(cform, U8_MIZENKEI) != 0) {
                    NJDNode_set_acc(head, phase_len + 1);
                } else {
                    NJDNode_set_acc(head, phase_len + 2);
                }
            } else if (strcmp(ctype, U8_TOKUSHU_NAI) == 0) {
                NJDNode_set_acc(head, phase_len);
            } else if (strcmp(orig, U8_RERU) == 0 || strcmp(orig, U8_RARERU) == 0 ||
                       strcmp(orig, U8_SUGIRU) == 0 ||
                       strcmp(orig, U8_SERU) == 0 || strcmp(orig, U8_SASERU) == 0) {
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

// ============================================================================
// OpenJTalk CGO wrapper
// ============================================================================

typedef struct {
    Mecab mecab;
    NJD njd;
    JPCommon jpcommon;
    int initialized;
} GoOpenJTalk;

typedef struct {
    char** labels;
    int size;
} GoOJTResult;

static GoOpenJTalk* ojt_initialize(const char* dict_path) {
    if (!dict_path) return NULL;
    GoOpenJTalk* oj = (GoOpenJTalk*)calloc(1, sizeof(GoOpenJTalk));
    if (!oj) return NULL;
    Mecab_initialize(&oj->mecab);
    NJD_initialize(&oj->njd);
    JPCommon_initialize(&oj->jpcommon);
    if (Mecab_load(&oj->mecab, dict_path) != TRUE) {
        JPCommon_clear(&oj->jpcommon);
        NJD_clear(&oj->njd);
        Mecab_clear(&oj->mecab);
        free(oj);
        return NULL;
    }
    oj->initialized = 1;
    return oj;
}

static void ojt_finalize(GoOpenJTalk* oj) {
    if (!oj) return;
    if (oj->initialized) {
        JPCommon_clear(&oj->jpcommon);
        NJD_clear(&oj->njd);
        Mecab_clear(&oj->mecab);
    }
    free(oj);
}

static GoOJTResult* ojt_extract(GoOpenJTalk* oj, const char* text) {
    if (!oj || !oj->initialized || !text) return NULL;
    size_t buf_size = strlen(text) * 10 + 1;
    char* buf = (char*)malloc(buf_size);
    if (!buf) return NULL;
    text2mecab(buf, buf_size, text);
    NJD_clear(&oj->njd);
    NJD_initialize(&oj->njd);
    Mecab_analysis(&oj->mecab, buf);
    mecab2njd(&oj->njd, Mecab_get_feature(&oj->mecab), Mecab_get_size(&oj->mecab));
    njd_set_pronunciation(&oj->njd);
    apply_original_rule_before_chaining(&oj->njd);
    njd_set_digit(&oj->njd);
    njd_set_accent_phrase(&oj->njd);
    njd_set_accent_type(&oj->njd);
    njd_set_unvoiced_vowel(&oj->njd);
    njd_set_long_vowel(&oj->njd);
    modify_acc_after_chaining(&oj->njd);
    JPCommon_refresh(&oj->jpcommon);
    njd2jpcommon(&oj->jpcommon, &oj->njd);
    JPCommon_make_label(&oj->jpcommon);
    int size = JPCommon_get_label_size(&oj->jpcommon);
    char** features = JPCommon_get_label_feature(&oj->jpcommon);
    GoOJTResult* r = (GoOJTResult*)calloc(1, sizeof(GoOJTResult));
    if (!r) { free(buf); return NULL; }
    r->size = size;
    if (size > 0 && features) {
        r->labels = (char**)malloc(sizeof(char*) * size);
        if (!r->labels) { free(r); free(buf); return NULL; }
        int i;
        for (i = 0; i < size; i++) {
            r->labels[i] = strdup(features[i]);
        }
    }
    free(buf);
    return r;
}

static int ojt_result_size(const GoOJTResult* r) {
    return r ? r->size : 0;
}

static const char* ojt_result_get(const GoOJTResult* r, int idx) {
    if (!r || idx < 0 || idx >= r->size) return NULL;
    return r->labels[idx];
}

static void ojt_result_free(GoOJTResult* r) {
    if (!r) return;
    if (r->labels) {
        int i;
        for (i = 0; i < r->size; i++) free(r->labels[i]);
        free(r->labels);
    }
    free(r);
}
*/
import "C"

import (
	"fmt"
	"runtime"
	"sync"
	"unsafe"
)

// OpenJTalkEngine is a CGO-backed JapaneseG2PEngine.
// It is safe for concurrent use; the underlying OpenJTalk instance is
// protected by a mutex because MeCab's internal state is not thread-safe.
type OpenJTalkEngine struct {
	mu sync.Mutex
	oj *C.GoOpenJTalk
}

func init() {
	NewOpenJTalkEngine = newOpenJTalkEngine
}

func newOpenJTalkEngine(dictPath string) (JapaneseG2PEngine, error) {
	cPath := C.CString(dictPath)
	defer C.free(unsafe.Pointer(cPath))

	oj := C.ojt_initialize(cPath)
	if oj == nil {
		return nil, fmt.Errorf("failed to initialize OpenJTalk with dictionary %q", dictPath)
	}

	e := &OpenJTalkEngine{oj: oj}
	runtime.SetFinalizer(e, func(e *OpenJTalkEngine) { _ = e.Close() })
	return e, nil
}

// ExtractFullcontext returns fullcontext labels produced by OpenJTalk.
func (e *OpenJTalkEngine) ExtractFullcontext(text string) ([]string, error) {
	e.mu.Lock()
	defer e.mu.Unlock()

	if e.oj == nil {
		return nil, fmt.Errorf("OpenJTalkEngine is already closed")
	}

	cText := C.CString(text)
	defer C.free(unsafe.Pointer(cText))

	result := C.ojt_extract(e.oj, cText)
	if result == nil {
		return nil, fmt.Errorf("ojt_extract failed for text %q", text)
	}
	defer C.ojt_result_free(result)

	n := int(C.ojt_result_size(result))
	labels := make([]string, n)
	for i := 0; i < n; i++ {
		labels[i] = C.GoString(C.ojt_result_get(result, C.int(i)))
	}
	return labels, nil
}

// Close releases the underlying OpenJTalk instance.
func (e *OpenJTalkEngine) Close() error {
	e.mu.Lock()
	defer e.mu.Unlock()

	if e.oj != nil {
		C.ojt_finalize(e.oj)
		e.oj = nil
	}
	return nil
}
