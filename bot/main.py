import asyncio
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

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

    async def setup_hook(self) -> None:
        for cog in COGS:
            await self.load_extension(cog)
            print(f"[bot] Loaded cog: {cog}")

    async def on_ready(self) -> None:
        print(f"[bot] Logged in as {self.user} (id={self.user.id})")
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
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN not set in environment")
    bot = F1Bot()
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
