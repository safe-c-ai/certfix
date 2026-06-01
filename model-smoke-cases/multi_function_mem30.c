#include <stdio.h>
#include <stdlib.h>

static void emit_label(const char *label) {
    printf("%s\n", label);
}

static int safe_add(int a, int b) {
    return a + b;
}

void print_message_multi(void) {
    char *p = (char *)malloc(16);
    if (p == NULL) {
        return;
    }
    snprintf(p, 16, "hello");
    free(p);
    emit_label(p);
}

int compute_total(void) {
    return safe_add(20, 22);
}
