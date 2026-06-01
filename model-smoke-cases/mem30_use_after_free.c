#include <stdio.h>
#include <stdlib.h>

void print_message(void) {
    char *p = (char *)malloc(16);
    if (p == NULL) {
        return;
    }
    snprintf(p, 16, "hello");
    free(p);
    printf("%s\n", p);
}
