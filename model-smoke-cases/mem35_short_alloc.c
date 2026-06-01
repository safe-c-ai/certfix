#include <stdlib.h>
#include <string.h>

char *copy_label(void) {
    char *p = (char *)malloc(4);
    if (p == NULL) {
        return NULL;
    }
    strcpy(p, "hello");
    return p;
}
