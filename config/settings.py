# Bot configuration — edit this file to configure the bot.
from pathlib import Path

# Discord bot token — read from the sibling file, never committed.
def load_token() -> str:
    token_file = Path(__file__).parent / "discord_token"
    if not token_file.exists():
        raise FileNotFoundError(
            f"Discord token not found at {token_file}. "
            "Create config/discord_token containing your bot token."
        )
    return token_file.read_text().strip()


# The channel ID where race zip files will be posted and processed.
# Right-click the channel in Discord (with Developer Mode on) → Copy Channel ID.
RACE_CHANNEL_ID: int = 0  # 0 = listen in all channels
