# Bot configuration — committed, no secrets here.
from pathlib import Path

_CONFIG_DIR = Path(__file__).parent


def load_token() -> str:
    """Read Discord bot token from config/discord_token (gitignored)."""
    token_file = _CONFIG_DIR / "discord_token"
    if not token_file.exists():
        raise FileNotFoundError(
            f"Discord token not found at {token_file}. "
            "Create config/discord_token containing your bot token."
        )
    return token_file.read_text().strip()


def _load_properties() -> dict[str, str]:
    """Parse config/bot.properties into a key→value dict."""
    props_file = _CONFIG_DIR / "bot.properties"
    props: dict[str, str] = {}
    if not props_file.exists():
        return props
    for line in props_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            props[k.strip()] = v.strip()
    return props


def load_max_queue_size(default: int = 5) -> int:
    """Read max_queue_size from config/bot.properties."""
    props = _load_properties()
    try:
        return int(props.get("max_queue_size", default))
    except ValueError:
        return default


def load_allowed_roles() -> set[str]:
    """Read allowed role names from config/roles (gitignored), one per line.
    Empty set = no restriction."""
    roles_file = _CONFIG_DIR / "roles"
    if not roles_file.exists():
        return set()
    roles = set()
    for line in roles_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            roles.add(line)
    return roles
