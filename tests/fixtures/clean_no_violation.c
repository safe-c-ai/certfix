#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int *p = (int *)malloc(sizeof(int));
    if (p == NULL) {
        return 1;
    }
    *p = 42;
    printf("%d\n", *p);
    free(p);
    return 0;
}
