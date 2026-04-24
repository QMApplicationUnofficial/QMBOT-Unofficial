import discord
from discord.ext import commands

from config import SUGGESTION_CHANNEL_ID, ANNOUNCEMENT_CHANNEL_ID, PACKAGE_USER_ID
from storage import load_suggestions, save_suggestions
from cogs.tasks import dm_package_to_user
from ui_utils import C, E, embed, error, success, warn


class Admin(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="suggest", description="Submit a suggestion for the server.")
    async def suggest(self, ctx, *, suggestion: str):
        channel = self.bot.get_channel(SUGGESTION_CHANNEL_ID)
        if not channel:
            return await ctx.send(embed=error("Suggest", "Suggestion channel not configured."))
        suggestions = load_suggestions()
        suggestions.append({"user": ctx.author.id, "text": suggestion})
        save_suggestions(suggestions)
        e = embed("💡  New Suggestion", suggestion, C.TRIVIA, footer=f"From {ctx.author.display_name}")
        msg = await channel.send(embed=e)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")
        await ctx.send(embed=success("Suggestion Submitted!", "Your idea has been sent to the team. ✅"))

    @commands.hybrid_command(name="announcement", description="Send a server announcement.")
    @commands.has_permissions(manage_guild=True)
    async def announcement(self, ctx, *, message: str):
        channel = self.bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        if not channel:
            return await ctx.send(embed=error("Announcement", "Announcement channel not configured."))
        e = embed(f"📢  Announcement", message, C.ADMIN, footer=f"Posted by {ctx.author.display_name}")
        await channel.send(embed=e)
        await ctx.send(embed=success("Announcement Posted!", "Your message has been sent. 📣"))

    @commands.hybrid_command(name="package", description="Send a manual data backup.")
    async def package(self, ctx):
        if ctx.author.id != PACKAGE_USER_ID:
            return await ctx.send(embed=error("Backup", "You're not authorised to do that."))
        ok = await dm_package_to_user(self.bot, PACKAGE_USER_ID, reason="Manual package command")
        if ok:
            await ctx.send(embed=success("Backup Sent!", "Data package delivered to your DMs. 📦"))
        else:
            await ctx.send(embed=error("Backup Failed", "Something went wrong creating the backup."))

    @announcement.error
    async def announcement_error(self, ctx, err):
        if isinstance(err, commands.MissingPermissions):
            await ctx.send(embed=error("Permission Denied", "You need **Manage Server** to post announcements."))

    @suggest.error
    async def suggest_error(self, ctx, err):
        await ctx.send(embed=error("Suggest", "Something went wrong submitting your suggestion."))

    @package.error
    async def package_error(self, ctx, err):
        await ctx.send(embed=error("Backup", "Something went wrong creating the backup."))


async def setup(bot):
    await bot.add_cog(Admin(bot))
