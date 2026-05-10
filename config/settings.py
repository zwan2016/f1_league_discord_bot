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


def load_race_channel_ids() -> set[int]:
    """Read channel IDs from config/channels (gitignored), one per line."""
    channels_file = _CONFIG_DIR / "channels"
    if not channels_file.exists():
        return set()
    ids = set()
    for line in channels_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            ids.add(int(line))
    return ids
