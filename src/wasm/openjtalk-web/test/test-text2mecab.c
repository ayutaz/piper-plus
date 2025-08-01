#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "text2mecab.h"

// Simple test to verify text2mecab output
int main() {
    const char *test_texts[] = {
        "こんにちは",
        "今日はいい天気ですね",
        "OpenJTalkのテストです",
        "123",
        "hello",
        NULL
    };
    
    printf("Testing text2mecab function\n");
    printf("==========================\n\n");
    
    for (int i = 0; test_texts[i] != NULL; i++) {
        char buff[8192];
        memset(buff, 0, sizeof(buff));
        
        printf("Input: %s\n", test_texts[i]);
        text2mecab(buff, test_texts[i]);
        printf("Output: %s\n", buff);
        printf("Length: %zu\n", strlen(buff));
        printf("---\n");
    }
    
    return 0;
}