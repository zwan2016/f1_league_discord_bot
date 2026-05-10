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


# Channels where race zip uploads will be processed.
# Right-click a channel in Discord (Developer Mode on) → Copy Channel ID, paste below.
# Empty list = listen in ALL channels (useful for testing).
RACE_CHANNEL_IDS: list[int] = [
    # 1234567890123456789,  # e.g. #race-results
]
