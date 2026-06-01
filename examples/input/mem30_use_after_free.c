#include <stdio.h>
#include <stdlib.h>

static void print_label(const char *label) {
    printf("%s\n", label);
}

static char *make_message(const char *prefix, int id) {
    char *p = (char *)malloc(32);
    if (p == NULL) {
        return NULL;
    }
    snprintf(p, 32, "%s-%d", prefix, id);
    return p;
}

int run_mem30_demo(void) {
    char *p = make_message("primary", 7);
    if (p == NULL) {
        return -1;
    }

    /* MEM30-C violation: p is freed before print_label uses it. */
    free(p);
    print_label(p);
    return 0;
}
