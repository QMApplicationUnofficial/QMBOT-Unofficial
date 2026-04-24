import asyncio
import time
import random

import discord
from discord.ext import commands

from config import XP_PER_MESSAGE
from storage import load_data

# ─────────────────────────────────────────
# Constants
# ─────────────────────────────────────────

CONFESSION_CHANNEL_ID = 1492170739955138630
CONFESSION_LOG_USER_ID = 734468552903360594


class Extras(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()

    # ─────────────────────────────────────────
    # Utility
    # ─────────────────────────────────────────

    @commands.hybrid_command()
    async def ping(self, ctx):
        """Check bot latency."""
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 Pong! `{latency}ms`")

    @commands.hybrid_command()
    async def uptime(self, ctx):
        """Show how long the bot has been running."""
        seconds = int(time.time() - self.start_time)
        hours, remainder = divmod(seconds, 3600)
        minutes = remainder // 60
        await ctx.send(f"⏱️ Uptime: `{hours}h {minutes}m`")

    @commands.hybrid_command()
    async def botinfo(self, ctx):
        """Display general bot information."""
        await ctx.send(
            f"🤖 **Bot Info**\n"
            f"Servers: `{len(self.bot.guilds)}`\n"
            f"Users:   `{len(self.bot.users)}`"
        )

    @commands.hybrid_command()
    async def serverinfo(self, ctx):
        """Display information about this server."""
        guild = ctx.guild
        await ctx.send(
            f"🏠 **Server Info**\n"
            f"Name:    `{guild.name}`\n"
            f"Members: `{guild.member_count}`\n"
            f"Created: `{guild.created_at.date()}`"
        )

    @commands.hybrid_command()
    async def userinfo(self, ctx, member: discord.Member = None):
        """Display information about a user."""
        member = member or ctx.author
        joined = member.joined_at.date() if member.joined_at else "Unknown"
        await ctx.send(
            f"👤 **User Info**\n"
            f"Name:   `{member}`\n"
            f"Joined: `{joined}`"
        )

    @commands.hybrid_command()
    async def gif(self, ctx, *, query: str):
        """Send a random GIF."""
        gifs = [
            "https://media.giphy.com/media/ICOgUNjpvO0PC/giphy.gif",
            "https://media.giphy.com/media/l0HlQ7LRalQqdWfao/giphy.gif",
            "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif",
        ]
        await ctx.send(random.choice(gifs))

    @commands.hybrid_command(name="messagecount")
    async def messagecount(self, ctx, member: discord.Member = None):
        """Show a user's message count since the last XP reset."""
        if not ctx.guild:
            return await ctx.send("⛔ This command only works in a server.")

        target = member or ctx.author
        data = load_data()
        guild_data = data.get(str(ctx.guild.id), {})
        user_data = guild_data.get(str(target.id), {})

        xp = int(user_data.get("xp", 0))
        messages = xp // XP_PER_MESSAGE

        await ctx.send(
            f"💬 **{target.display_name}** has sent **{messages:,}** messages since the last reset.\n"
        )

    @commands.hybrid_command()
    async def timer(self, ctx, seconds: int):
        """Start a countdown timer (max 300 seconds)."""
        if seconds <= 0:
            return await ctx.send("⛔ Timer must be greater than 0 seconds.")
        if seconds > 300:
            return await ctx.send("⛔ Maximum timer duration is 300 seconds.")

        await ctx.send(f"⏳ Timer started for `{seconds}` seconds...")
        await asyncio.sleep(seconds)
        await ctx.send(f"⏰ {ctx.author.mention} Your timer is up!")
        
# ─────────────────────────────────────────
# Setup
# ─────────────────────────────────────────

async def setup(bot):
    await bot.add_cog(Extras(bot))
