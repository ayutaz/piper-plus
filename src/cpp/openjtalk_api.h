#ifndef OPENJTALK_API_H_
#define OPENJTALK_API_H_

#ifdef __cplusplus
extern "C" {
#endif

#include <stdlib.h>

// Forward declarations
typedef struct _OpenJTalk OpenJTalk;
typedef struct _OJ_Label OJ_Label;

// OpenJTalk wrapper functions
OpenJTalk* openjtalk_initialize();
void openjtalk_finalize(OpenJTalk* oj);
OJ_Label* openjtalk_extract_fullcontext(OpenJTalk* oj, const char* text);

// OJ Label functions
size_t OJ_Label_get_size(OJ_Label* label);
const char* OJ_Label_get_string(OJ_Label* label, size_t index);
void OJ_Label_clear(OJ_Label* label);

#ifdef __cplusplus
}
#endif

#endif // OPENJTALK_API_H_