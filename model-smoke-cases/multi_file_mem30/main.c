#include <stdio.h>
#include <stdlib.h>

#include "helpers.h"

void run_case(void) {
    char *p = (char *)malloc(LABEL_SIZE);
    if (p == NULL) {
        return;
    }
    snprintf(p, LABEL_SIZE, "hello");
    free(p);
    printf("%s\n", p);
}
