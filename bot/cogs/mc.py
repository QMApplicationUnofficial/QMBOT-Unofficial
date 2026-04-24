import asyncio
import aiohttp
import discord
from discord.ext import commands

from config import (
    MC_NAME, MC_ADDRESS, MC_JAVA_PORT,
    MC_MODRINTH_URL, MC_MAP_URL, MC_RULES_URL, MC_DISCORD_URL,
    MC_VERSION, MC_LOADER, MC_MODPACK_NAME, MC_WHITELISTED, MC_REGION,
    MC_NOTES, MC_SHOW_BEDROCK, MC_BEDROCK_PORT
)


from ui_utils import C, E
EMBED_COLOR = C.MC


def make_embed(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=title, description=description, color=EMBED_COLOR)


def _safe_join_url(label: str, url: str) -> str:
    return f"{label}: {url}"


class MCLinksView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        if MC_MODRINTH_URL:
            self.add_item(discord.ui.Button(label="Modrinth", url=MC_MODRINTH_URL))
        if MC_MAP_URL:
            self.add_item(discord.ui.Button(label="Live Map", url=MC_MAP_URL))
        if MC_RULES_URL:
            self.add_item(discord.ui.Button(label="Rules", url=MC_RULES_URL))
        if MC_DISCORD_URL:
            self.add_item(discord.ui.Button(label="Discord", url=MC_DISCORD_URL))


async def fetch_mc_status_fallback(address: str):
    url = f"https://api.mcsrvstat.us/2/{address}"
    timeout = aiohttp.ClientTimeout(total=6)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Fallback API returned HTTP {resp.status}")
            return await resp.json()


class Minecraft(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="mc",
        description="Show Minecraft server info."
    )
    async def mc(self, ctx: commands.Context):
        address = MC_ADDRESS

        desc_lines = [
            f"**Java Join:** `{address}`",
            f"**Java Port:** `{MC_JAVA_PORT if MC_JAVA_PORT else 'SRV / default'}`",
        ]

        if MC_SHOW_BEDROCK:
            desc_lines += [
                "",
                f"**Bedrock Address:** `{address}`",
                f"**Bedrock Port:** `{MC_BEDROCK_PORT}`",
            ]

        desc_lines += [
            "",
            "Add the address in Multiplayer and join."
        ]

        embed = make_embed(MC_NAME, "\n".join(desc_lines))

        embed.add_field(name="Version", value=f"`{MC_VERSION}`", inline=True)
        embed.add_field(name="Loader", value=f"`{MC_LOADER}`", inline=True)
        embed.add_field(name="Modpack", value=f"`{MC_MODPACK_NAME}`", inline=True)

        embed.add_field(
            name="Access",
            value="Whitelist ON" if MC_WHITELISTED else "Public",
            inline=True
        )
        embed.add_field(name="Region", value=MC_REGION, inline=True)

        if MC_NOTES:
            embed.add_field(
                name="Notes",
                value="\n".join(f"• {x}" for x in MC_NOTES)[:1024],
                inline=False
            )

        link_lines = []
        if MC_MODRINTH_URL:
            link_lines.append(_safe_join_url("Modrinth", MC_MODRINTH_URL))
        if MC_MAP_URL:
            link_lines.append(_safe_join_url("Live Map", MC_MAP_URL))
        if MC_RULES_URL:
            link_lines.append(_safe_join_url("Rules", MC_RULES_URL))
        if MC_DISCORD_URL:
            link_lines.append(_safe_join_url("Discord", MC_DISCORD_URL))

        if link_lines:
            embed.add_field(
                name="Links",
                value="\n".join(link_lines)[:1024],
                inline=False
            )

        live_status_set = False

        try:
            from mcstatus import JavaServer

            def ping_java():
                if MC_JAVA_PORT:
                    server = JavaServer.lookup(f"{address}:{MC_JAVA_PORT}")
                else:
                    server = JavaServer.lookup(address)
                return server.status()

            status = await asyncio.to_thread(ping_java)

            online = getattr(status.players, "online", None)
            maxp = getattr(status.players, "max", None)

            motd_plain = None
            try:
                motd_plain = status.motd.to_plain()
            except Exception:
                motd_plain = None

            if online is not None and maxp is not None:
                embed.add_field(
                    name="Status",
                    value=f"Online  |  **{online}/{maxp}** players",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Status",
                    value="Online",
                    inline=False
                )

            if motd_plain:
                embed.add_field(
                    name="MOTD",
                    value=motd_plain[:1000],
                    inline=False
                )

            latency_ms = getattr(status, "latency", None)
            if latency_ms is not None:
                embed.add_field(
                    name="Ping",
                    value=f"`{latency_ms:.0f} ms`",
                    inline=True
                )

            live_status_set = True

        except ModuleNotFoundError:
            pass
        except Exception:
            pass

        if not live_status_set:
            try:
                data = await fetch_mc_status_fallback(address)

                if not data.get("online"):
                    embed.add_field(
                        name="Status",
                        value="Offline",
                        inline=False
                    )
                else:
                    players = data.get("players") or {}
                    online = players.get("online", "?")
                    maxp = players.get("max", "?")

                    embed.add_field(
                        name="Status",
                        value=f"Online  |  **{online}/{maxp}** players",
                        inline=False
                    )

                    motd = data.get("motd") or {}
                    clean = motd.get("clean")
                    if isinstance(clean, list) and clean:
                        embed.add_field(
                            name="MOTD",
                            value="\n".join(clean)[:1000],
                            inline=False
                        )

            except Exception:
                embed.add_field(
                    name="Status",
                    value="Unavailable right now.",
                    inline=False
                )

        embed.set_footer(text=f"Server address: {address}")

        await ctx.send(embed=embed, view=MCLinksView())


async def setup(bot: commands.Bot):
    await bot.add_cog(Minecraft(bot))
