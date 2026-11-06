#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "mpdecimal.h"

int
main(void)
{
    mpd_context_t ctx;
    mpd_defaultcontext(&ctx);
    ctx.prec = 40;
    uint32_t status = 0;
    mpd_t *a = mpd_qnew();
    mpd_t *b = mpd_qnew();
    mpd_t *result = mpd_qnew();
    if (a == NULL || b == NULL || result == NULL)
        return 2;
    mpd_qset_string(a, "123456789", &ctx, &status);
    mpd_qset_string(b, "987654321", &ctx, &status);
    mpd_qmul(result, a, b, &ctx, &status);
    char *text = mpd_to_sci(result, 1);
    if (status != 0 || text == NULL || strcmp(text, "121932631112635269") != 0)
        return 3;
    puts(text);
    free(text);
    mpd_del(result);
    mpd_del(b);
    mpd_del(a);
    return 0;
}
