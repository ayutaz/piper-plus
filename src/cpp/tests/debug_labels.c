/* Debug: Output raw fullcontext labels for comparison with Python */
#include <stdio.h>
#include <string.h>
#include "../openjtalk_api.h"
#include "../openjtalk_dictionary_manager.h"

int main() {
    const char* texts[] = {
        "\xe3\x81\x82\xe3\x82\x93\xe3\x81\xaa\xe3\x81\x84\xe3\x81\x97\xe3\x81\xbe\xe3\x81\x99\xe3\x80\x82",  /* あんないします。 */
        "\xe6\x9c\xac\xe3\x82\x92\xe8\xaa\xad\xe3\x81\xbf\xe3\x81\xbe\xe3\x81\x97\xe3\x81\x9f\xe3\x80\x82",  /* 本を読みました。 */
        NULL
    };

    if (ensure_openjtalk_dictionary() != 0) {
        fprintf(stderr, "ERROR: Dictionary not available\n");
        return 1;
    }

    for (int t = 0; texts[t]; t++) {
        printf("\n=== Text %d: %s ===\n", t+1, texts[t]);

        OpenJTalk* oj = openjtalk_initialize();
        if (!oj) {
            fprintf(stderr, "ERROR: Failed to initialize OpenJTalk\n");
            continue;
        }

        HTS_Label* label = openjtalk_extract_fullcontext(oj, texts[t]);
        if (!label) {
            fprintf(stderr, "ERROR: Failed to extract fullcontext\n");
            openjtalk_finalize(oj);
            continue;
        }

        size_t size = HTS_Label_get_size(label);
        printf("Label count: %zu\n", size);

        for (size_t i = 0; i < size; i++) {
            const char* s = HTS_Label_get_string(label, i);
            printf("[%2zu] %s\n", i, s ? s : "(null)");
        }

        HTS_Label_clear(label);
        openjtalk_finalize(oj);
    }

    return 0;
}
