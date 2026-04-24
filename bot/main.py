import discord
from discord.ext import commands

from config import TOKEN


INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.voice_states = True
INTENTS.members = True


INITIAL_EXTENSIONS = [
    "cogs.listeners",
    "cogs.economy",
    "cogs.trivia",
    "cogs.games",
    "cogs.admin",
    "cogs.mc",
    "cogs.tasks",
    "cogs.social",
    "cogs.shop",
    "cogs.market",
    "cogs.swearjar",
    "cogs.logs",
    "cogs.fun",
    "cogs.xp",
    "cogs.extras",
    "cogs.modtools",
]


class QMULBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=INTENTS,
        )

    async def setup_hook(self):
        print("[Startup] Loading cogs...")

        for ext in INITIAL_EXTENSIONS:
            try:
                await self.load_extension(ext)
                print(f"[Cog] Loaded {ext}")
            except commands.ExtensionAlreadyLoaded:
                print(f"[Cog] Already loaded {ext}")
            except commands.ExtensionNotFound:
                print(f"[Cog] Missing {ext}")
            except commands.NoEntryPointError:
                print(f"[Cog] No setup() found in {ext}")
            except commands.ExtensionFailed as e:
                print(f"[Cog] Failed {ext}: {type(e.original).__name__}: {e.original}")
            except Exception as e:
                print(f"[Cog] Skipped {ext}: {type(e).__name__}: {e}")

        try:
            synced = await self.tree.sync()
            print(f"[Slash] Synced {len(synced)} global command(s).")
        except Exception as e:
            print(f"[Slash] Sync failed: {type(e).__name__}: {e}")


bot = QMULBot()


@bot.event
async def on_ready():
    print(f"{bot.user} is online and ready!")


def main():
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN not set in environment.")
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
