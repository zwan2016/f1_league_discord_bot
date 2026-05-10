import asyncio

import discord
from discord.ext import commands

from config.settings import load_token, load_race_channel_ids, load_allowed_roles

COGS = [
    "bot.cogs.race",
]

intents = discord.Intents.default()
intents.message_content = True


class F1Bot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=commands.DefaultHelpCommand(),
        )
        self.race_channel_ids: set[int] = load_race_channel_ids()
        self.allowed_roles: set[str] = load_allowed_roles()

    async def setup_hook(self) -> None:
        for cog in COGS:
            await self.load_extension(cog)
            print(f"[bot] Loaded cog: {cog}")

    async def on_ready(self) -> None:
        print(f"[bot] Logged in as {self.user} (id={self.user.id})")
        if self.race_channel_ids:
            print(f"[bot] Watching channels: {self.race_channel_ids}")
        else:
            print("[bot] No RACE_CHANNEL_IDS set — listening in all channels")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="F1 25 race recordings",
            )
        )

    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        await ctx.send(f"❌ {error}")
        raise error


async def main() -> None:
    token = load_token()
    bot = F1Bot()
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
