import discord
from discord.ext import commands

from storage import load_swear_jar, save_swear_jar
from ui_utils import C, E, embed, error, success


class SwearJar(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="swearjar", description="Show the total swears recorded in the server.")
    async def swearjar(self, ctx):
        jar   = load_swear_jar()
        total = jar.get("total", 0)
        e = embed(
            "🫙  Swear Jar",
            f"This server has collectively sworn **{total:,}** times.\n\nEvery drop counts.",
            C.SWEAR,
            footer="Logged automatically from messages",
        )
        await ctx.send(embed=e)

    @commands.hybrid_command(name="swearleaderboard", description="Who swears the most?")
    async def swearleaderboard(self, ctx):
        jar   = load_swear_jar()
        users = jar.get("users", {})
        if not users:
            return await ctx.send(embed=embed("🧼  Swear Leaderboard", "No swears recorded yet. Impressive.", C.SWEAR))
        sorted_users = sorted(users.items(), key=lambda x: x[1].get("count", 0), reverse=True)[:10]
        medals = ["🥇", "🥈", "🥉"]
        lines  = []
        for i, (uid, data) in enumerate(sorted_users):
            try:
                user = await self.bot.fetch_user(int(uid))
                name = user.display_name
            except Exception:
                name = f"User {uid}"
            count = data.get("count", 0)
            medal = medals[i] if i < 3 else f"{i+1}."
            lines.append(f"{medal}  **{name}** — `{count:,}` swears")
        e = embed("🧼  Swear Leaderboard", "\n".join(lines), C.SWEAR, footer="Measured by raw swear count")
        await ctx.send(embed=e)

    @commands.hybrid_command(name="swearreset", description="Reset the swear jar (admin only).")
    @commands.has_permissions(administrator=True)
    async def swearreset(self, ctx):
        save_swear_jar({"total": 0, "users": {}})
        await ctx.send(embed=success("Swear Jar Reset", "🧹 The jar has been emptied. Fresh start."))

    @commands.hybrid_command(name="swearfine", description="Check how many times you've sworn.")
    async def swearfine(self, ctx):
        jar   = load_swear_jar()
        uid   = str(ctx.author.id)
        count = jar.get("users", {}).get(uid, {}).get("count", 0)
        e = embed(
            "💰  Your Swear Count",
            f"You have sworn **{count:,}** times, you filthy thing.",
            C.SWEAR,
        )
        await ctx.send(embed=e)


async def setup(bot):
    await bot.add_cog(SwearJar(bot))
