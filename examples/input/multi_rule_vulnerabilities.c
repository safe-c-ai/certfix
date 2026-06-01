#include <stdio.h>
#include <string.h>

struct request_context {
    int authenticated;
    const char *user_name;
};

static int retry_budget_for(const struct request_context *request) {
    int retry_budget;
    if (request->authenticated) {
        retry_budget = 1;
    }
    /* EXP33-C violation: retry_budget is uninitialized for guest requests. */
    return retry_budget;
}

static void build_display_name(char *output, const char *user_name) {
    char short_name[8];
    /* STR31-C violation: strcpy can overflow short_name for long user names. */
    strcpy(short_name, user_name);
    snprintf(output, 32, "user:%s", short_name);
}

int run_multi_rule_demo(void) {
    struct request_context request = {0, "administrator"};
    char display_name[32];

    build_display_name(display_name, request.user_name);
    printf("%s retry_budget=%d\n", display_name, retry_budget_for(&request));
    return 0;
}
