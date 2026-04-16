"""
Menu system — registry pattern.

Usage in main.py:
    register_option("List all repos", lambda: list_repos(client))
    register_option("Exit", None)   # None signals the exit option
    run_menu_loop()

Adding a new feature requires exactly one register_option() call.
"""

from typing import Callable, Optional

from colors import bold, cyan, yellow, green, red, dim, reset, white


# Internal registry: list of (label, handler | None)
# None handler = exit sentinel
_options: list[tuple[str, Optional[Callable]]] = []


def register_option(label: str, handler: Optional[Callable]) -> None:
    """Register a menu option. Pass handler=None to mark it as the Exit option."""
    _options.append((label, handler))


def show_menu() -> None:
    """Print the numbered menu to stdout."""
    bar = f"{bold}{cyan}{'═' * 42}{reset}"
    print(bar)
    print(f"{bold}{cyan}{'╔╗ ╔═╗╔╦╗╔═╗':^42}{reset}")
    print(f"{bold}{cyan}{'╠╩╗╠═╣║║║╠╣ ':^42}{reset}")
    print(f"{bold}{cyan}{'╚═╝╩ ╩╩ ╩╚  ':^42}{reset}")
    print(bar)
    for i, (label, handler) in enumerate(_options, start=1):
        if handler is None:
            # Exit option — muted
            print(f"  {dim}{i}. {label}{reset}")
        else:
            print(f"  {yellow}{i}.{reset} {white}{label}{reset}")
    print(bar)


def dispatch(choice: int) -> bool:
    """Execute the handler for the given 1-based choice.

    Returns:
        False if the selected option is the Exit sentinel (handler is None),
        True otherwise.
    """
    label, handler = _options[choice - 1]
    if handler is None:
        return False  # exit signal
    handler()
    return True


def run_menu_loop() -> None:
    """Display the menu and process input until the user chooses Exit."""
    n = len(_options)

    while True:
        show_menu()
        raw = input(f"\n{bold}Select an option (1-{n}):{reset} ").strip()

        try:
            choice = int(raw)
        except ValueError:
            print(f"\n  {red}Please enter a number between 1 and {n}.{reset}\n")
            continue

        if not (1 <= choice <= n):
            print(f"\n  {red}Please enter a number between 1 and {n}.{reset}\n")
            continue

        keep_running = dispatch(choice)
        if not keep_running:
            print(f"\n{bold}{green}Goodbye!{reset}\n")
            break
