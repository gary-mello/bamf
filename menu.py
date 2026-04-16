"""
Menu system — registry pattern.

Usage in main.py:
    register_option("List all repos", lambda: list_repos(client))
    register_option("Exit", None)   # None signals the exit option
    run_menu_loop()

Adding a new feature requires exactly one register_option() call.
"""

from typing import Callable, Optional


# Internal registry: list of (label, handler | None)
# None handler = exit sentinel
_options: list[tuple[str, Optional[Callable]]] = []


def register_option(label: str, handler: Optional[Callable]) -> None:
    """Register a menu option. Pass handler=None to mark it as the Exit option."""
    _options.append((label, handler))


def show_menu() -> None:
    """Print the numbered menu to stdout."""
    print("=" * 40)
    print("  GitHub CLI — Main Menu")
    print("=" * 40)
    for i, (label, _) in enumerate(_options, start=1):
        print(f"  {i}. {label}")
    print("=" * 40)


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
        raw = input(f"Select an option (1-{n}): ").strip()

        try:
            choice = int(raw)
        except ValueError:
            print(f"\n  Please enter a number between 1 and {n}.\n")
            continue

        if not (1 <= choice <= n):
            print(f"\n  Please enter a number between 1 and {n}.\n")
            continue

        keep_running = dispatch(choice)
        if not keep_running:
            print("\nGoodbye!\n")
            break
