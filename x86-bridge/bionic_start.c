extern int main(int argc, char **argv, char **envp);
struct Structors { void (*preinit_array)(void); void (*init_array)(void); void (*fini_array)(void); };
extern void __libc_init(void *raw_args, void (*onexit)(void), int (*slingshot)(int, char**, char**), struct Structors const * const structors) __attribute__((noreturn));
static const struct Structors s = { 0, 0, 0 };
void _start_c(void *raw_args) {
    __libc_init(raw_args, 0, main, &s);
}
__attribute__((naked)) void _start(void) {
    __asm__ volatile(
        "mov r0, sp\n"
        "b _start_c\n"
    );
}
