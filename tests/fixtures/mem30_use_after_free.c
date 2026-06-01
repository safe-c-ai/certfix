#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void) {
    char *p = (char *)malloc(64);
    strcpy(p, "hello");
    free(p);
    printf("%s\n", p);  /* use after free */
    return 0;
}
