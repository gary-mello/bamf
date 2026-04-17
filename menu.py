"""
Menu system — registry pattern.

Usage in main.py:
    register_section("RECON")
    register_option("List all repos", lambda: list_repos(client))
    register_option("Exit", None)   # None signals the exit option
    run_menu_loop()

Adding a new feature requires exactly one register_option() call.
"""

import os
from typing import Callable, Optional

from colors import bold, cyan, yellow, green, red, dim, reset, white, magenta


def _clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


# Sentinel for section header entries (not selectable, not numbered)
_SECTION = object()

# Internal registry: list of (label, handler | None | _SECTION, disabled)
_options: list[tuple[str, object, bool]] = []


def register_section(title: str) -> None:
    """Register a section header. Displayed as a divider, not selectable."""
    _options.append((title, _SECTION, False))


def register_option(label: str, handler: Optional[Callable], disabled: bool = False) -> None:
    """Register a menu option. Pass handler=None to mark it as the Exit option."""
    _options.append((label, handler, disabled))


def show_menu() -> None:
    """Print the numbered menu to stdout."""
    bar = f"{bold}{cyan}{'═' * 42}{reset}"
    print(bar)
    print(f"{bold}{cyan}{'╔╗ ╔═╗╔╦╗╔═╗':^42}{reset}")
    print(f"{bold}{cyan}{'╠╩╗╠═╣║║║╠╣ ':^42}{reset}")
    print(f"{bold}{cyan}{'╚═╝╩ ╩╩ ╩╚  ':^42}{reset}")
    print(bar)

    num = 1
    any_disabled = False
    for label, handler, disabled in _options:
        if handler is _SECTION:
            print(f"\n  {bold}{magenta}{label}{reset}  {dim}{'·' * (36 - len(label))}{reset}")
        elif handler is None:
            pass  # exit is handled via [x], not a numbered option
        elif disabled:
            print(f"  {dim}{num}. {label}  [no permission]{reset}")
            num += 1
            any_disabled = True
        else:
            print(f"  {yellow}{num}.{reset} {white}{label}{reset}")
            num += 1

    print(f"\n{bar}")
    print(f"  {dim}[x] exit{reset}")
    if any_disabled:
        print(f"\n  {dim}* Greyed-out features not available due to token permissions{reset}")


def dispatch(choice: int) -> bool:
    """Execute the handler for the given 1-based choice.

    Returns:
        False if the selected option is the Exit sentinel (handler is None),
        True otherwise.
    """
    num = 0
    for label, handler, disabled in _options:
        if handler is _SECTION:
            continue
        num += 1
        if num == choice:
            if handler is None:
                return False
            if disabled:
                print(f"\n  {dim}Token lacks required permissions for this feature.{reset}")
                return True
            handler()
            return True
    return False


def run_menu_loop() -> None:
    """Display the menu and process input until the user chooses Exit."""
    n = sum(1 for _, handler, _ in _options if handler is not _SECTION and handler is not None)

    while True:
        _clear()
        show_menu()
        raw = input(f"\n{bold}Select an option (1-{n}):{reset} ").strip()

        if raw.lower() == "x":
            print(f"\n{bold}{green}Goodbye!{reset}\n")
            break

        try:
            choice = int(raw)
        except ValueError:
            print(f"\n  {red}Please enter a number between 1 and {n}.{reset}\n")
            continue

        if not (1 <= choice <= n):
            print(f"\n  {red}Please enter a number between 1 and {n}.{reset}\n")
            continue

        dispatch(choice)
        input(f"\n{dim}Press Enter to return to menu...{reset}")
