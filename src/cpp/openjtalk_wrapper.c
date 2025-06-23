#include "openjtalk_wrapper.h"
#include "openjtalk_api.h"

// Simple wrapper that delegates to the actual API implementation

OpenJTalk* openjtalk_initialize() {
    return openjtalk_initialize();
}

void openjtalk_finalize(OpenJTalk* oj) {
    openjtalk_finalize(oj);
}

HTS_Label_Wrapper* openjtalk_extract_fullcontext(OpenJTalk* oj, const char* text) {
    return (HTS_Label_Wrapper*)openjtalk_extract_fullcontext(oj, text);
}

size_t HTS_Label_get_size(HTS_Label_Wrapper* label) {
    return HTS_Label_get_size((HTS_Label*)label);
}

const char* HTS_Label_get_string(HTS_Label_Wrapper* label, size_t index) {
    return HTS_Label_get_string((HTS_Label*)label, index);
}

void HTS_Label_clear(HTS_Label_Wrapper* label) {
    HTS_Label_clear((HTS_Label*)label);
}