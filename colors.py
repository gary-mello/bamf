"""
Terminal color helpers built on colorama.

Import the short aliases (C, S, R) or individual names as needed:

    from colors import cyan, green, red, bold, dim, reset
    print(f"{bold}{cyan}Hello{reset}")
"""

from colorama import init as _init, Fore, Style

# Initialise once — strips ANSI on Windows when not supported
_init(autoreset=False)

# Foreground colors
cyan    = Fore.CYAN
green   = Fore.GREEN
yellow  = Fore.YELLOW
red     = Fore.RED
white   = Fore.WHITE
magenta = Fore.MAGENTA
blue    = Fore.BLUE

# Styles
bold    = Style.BRIGHT
dim     = Style.DIM
reset   = Style.RESET_ALL


def label(text: str) -> str:
    """Cyan label text."""
    return f"{cyan}{text}{reset}"


def value(text: str) -> str:
    """Bright white value text."""
    return f"{bold}{white}{text}{reset}"


def success(text: str) -> str:
    """Green success text."""
    return f"{green}{text}{reset}"


def warn(text: str) -> str:
    """Yellow warning text."""
    return f"{yellow}{text}{reset}"


def error(text: str) -> str:
    """Red error text."""
    return f"{red}{text}{reset}"


def header(text: str) -> str:
    """Bold cyan header."""
    return f"{bold}{cyan}{text}{reset}"


def muted(text: str) -> str:
    """Dim/muted text."""
    return f"{dim}{text}{reset}"
