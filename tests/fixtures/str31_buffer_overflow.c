#include <stdio.h>
#include <string.h>

int main(void) {
    char buf[8];
    strcpy(buf, "this string is way too long for buf");  /* buffer overflow */
    printf("%s\n", buf);
    return 0;
}
