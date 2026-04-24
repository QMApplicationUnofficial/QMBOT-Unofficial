import discord
from discord.ext import commands
import random
import aiohttp

from storage import load_actions, save_actions
from ui_utils import C, E, embed, error, warn

TENOR_API_KEY = "AIzaSyAyimkuEcdEnPs55ueys84EMt_lFe0BXKQ"   # replace with your key
TENOR_BASE    = "https://tenor.googleapis.com/v2/search"


async def fetch_gif(query: str) -> str | None:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                TENOR_BASE,
                params={"q": query, "key": TENOR_API_KEY, "limit": 20,
                        "media_filter": "gif", "contentfilter": "medium"},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as r:
                if r.status != 200:
                    return None
                data    = await r.json()
                results = data.get("results", [])
                if not results:
                    return None
                chosen = random.choice(results[:10])
                media  = chosen.get("media_formats", {})
                gif    = media.get("gif") or media.get("mediumgif") or media.get("tinygif") or {}
                return gif.get("url")
    except Exception:
        return None


def action_embed(title: str, desc: str, author: discord.Member, target: discord.Member) -> discord.Embed:
    e = embed(title, desc, C.SOCIAL, footer=f"{author.display_name} → {target.display_name}")
    return e


class Social(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    # ── INSULT ────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="insult", description="Insult another user.")
    async def insult(self, ctx, member: discord.Member):
        if member.bot:
            return await ctx.send(embed=error("Insult", "I won't insult bots."))
        lines = [
            "I hope you know ur a fat fuck, biggie",
            "Any racial slur would be a complement to you",
            "I would rather drag my testicles over shattered glass than to talk to you any longer",
            "Even moses cant part that fucking unibrow, ugly fuck",
            "your Ital*an (from iggy)",
            "kys", "retard.", "retarded is a compliment to you",
            "I hope love never finds ur fugly ahh", "Fuckkk 🐺...",
            "flippin Malteser",
            "Fuck you, you ho. Come and say to my face, I'll fuck you in the ass in front of everybody. You bitch.",
            "Whoever's willing to fuck you is just too lazy to jerk off.",
            "God just be making anyone",
            "You should have been a blowjob",
        ]
        e = action_embed(f"{E.SKULL}  Insult", f"{ctx.author.mention} → {member.mention}\n\n> {random.choice(lines)}", ctx.author, member)
        await ctx.send(embed=e)

    # ── THREATEN ──────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="threaten", description="Threaten another user.")
    async def threaten(self, ctx, member: discord.Member):
        lines = [
            "I will pee your pants", "I will touch you",
            "*twirls your balls (testicular torsion way)* 🔌😈",
            "I will jiggle your tits", "I will send you to I*aly",
            "I will wet your socks (sexually)", "🇫🇷",
        ]
        e = action_embed(f"⚔️  Threat", f"{ctx.author.mention} → {member.mention}\n\n> {random.choice(lines)}", ctx.author, member)
        await ctx.send(embed=e)

    # ── WARN ──────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="warn", description="Warn another user.")
    async def warn(self, ctx, member: discord.Member):
        lines = [
            "That message has been escorted out by security.",
            "Please keep your hands, feet, and words to yourself.",
            "This is a no-weird-zone. Thank you for your cooperation.",
            "Bonk. Go to respectful conversation jail.",
            "That was a bit much. Let's dial it back.",
            "Socks will remain dry. Boundaries enforced.",
            "International incidents are not permitted here.",
        ]
        e = action_embed(f"{E.WARN_ACT}  Warning Issued", f"{ctx.author.mention} → {member.mention}\n\n> {random.choice(lines)}", ctx.author, member)
        await ctx.send(embed=e)

    # ── COMPLIMENT ────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="compliment", description="Compliment another user.")
    async def compliment(self, ctx, member: discord.Member):
        lines = [
            "You're the MVP of this server.",
            "You make this place genuinely better.",
            "You're smarter than the average Discord user, which says a lot.",
            "Your memes are elite tier — don't let anyone tell you otherwise.",
            "You are carrying this server on your back. Respect.",
        ]
        e = action_embed(f"{E.HEART}  Compliment", f"{ctx.author.mention} → {member.mention}\n\n> {random.choice(lines)}", ctx.author, member)
        e.color = C.MARRIAGE
        await ctx.send(embed=e)

    # ── STAB ──────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="stab", description="Stab another user.")
    async def stab(self, ctx, member: discord.Member):
        e = action_embed(f"{E.SKULL}  Stabbed!", f"{ctx.author.mention} **stabbed** {member.mention}. Ouch.", ctx.author, member)
        gif = await fetch_gif("anime stab")
        if gif:
            e.set_image(url=gif)
        await ctx.send(embed=e)

    # ── LICK ──────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="lick", description="Lick another user.")
    async def lick(self, ctx, member: discord.Member):
        e = action_embed("👅  Lick", f"{ctx.author.mention} **licked** {member.mention}.", ctx.author, member)
        gif = await fetch_gif("anime lick")
        if gif:
            e.set_image(url=gif)
        await ctx.send(embed=e)

    # ── ACTION CREATE ─────────────────────────────────────────────────────────

    @commands.hybrid_command(name="actioncreate", description="Create a custom action (moderators only).")
    @commands.has_permissions(manage_guild=True)
    async def actioncreate(self, ctx, verb: str, plural: str):
        actions = load_actions()
        verb    = verb.lower().strip()
        if not verb.isalpha():
            return await ctx.send(embed=error("Action Create", "Verb must only contain letters."))
        if verb in actions:
            return await ctx.send(embed=error("Action Create", f"`{verb}` already exists."))
        actions[verb] = plural.strip()
        save_actions(actions)
        e = embed(
            f"{E.SPARKLE}  Action Created",
            f"**Verb:** `{verb}`\n**Output:** _{plural}_\n\nAnyone can now use `/action {verb} @user`",
            C.SOCIAL,
        )
        await ctx.send(embed=e)

    # ── ACTION (everyone) ─────────────────────────────────────────────────────

    @commands.hybrid_command(name="action", description="Perform a custom action on someone.")
    async def action(self, ctx, verb: str, member: discord.Member):
        actions = load_actions()
        key     = verb.lower().strip()
        if key not in actions:
            return await ctx.send(embed=error("Action", f"`{key}` doesn't exist. Use `/actionlist` to see what's available."))
        plural = actions[key]
        e = action_embed(
            f"{E.SPARKLE}  Action",
            f"{ctx.author.mention} **{plural}** {member.mention}.",
            ctx.author, member,
        )
        e.color = C.SOCIAL
        gif = await fetch_gif(key)
        if gif:
            e.set_image(url=gif)
        await ctx.send(embed=e)

    # ── ACTION LIST ───────────────────────────────────────────────────────────

    @commands.hybrid_command(name="actionlist", description="List all custom actions.")
    async def actionlist(self, ctx):
        actions = load_actions()
        if not actions:
            return await ctx.send(embed=embed(f"{E.SPARKLE}  Action List", "No custom actions created yet.", C.SOCIAL))
        lines = [f"`{v}` — _{actions[v]}_" for v in sorted(actions)]
        e = embed(f"{E.SPARKLE}  Custom Actions ({len(actions)})", "\n".join(lines), C.SOCIAL)
        await ctx.send(embed=e)

    # ── ACTION DELETE ─────────────────────────────────────────────────────────

    @commands.hybrid_command(name="actiondelete", description="Delete a custom action (moderators only).")
    @commands.has_permissions(manage_guild=True)
    async def actiondelete(self, ctx, verb: str):
        actions = load_actions()
        key     = verb.lower().strip()
        if key not in actions:
            return await ctx.send(embed=error("Action Delete", f"`{key}` doesn't exist."))
        removed = actions.pop(key)
        save_actions(actions)
        e = embed(f"🗑️  Action Deleted", f"Removed `{key}` — _{removed}_", C.ADMIN)
        await ctx.send(embed=e)

    @actioncreate.error
    async def actioncreate_error(self, ctx, err):
        if isinstance(err, commands.MissingPermissions):
            await ctx.send(embed=error("Permission Denied", "You need **Manage Server** to create actions."))

    @actiondelete.error
    async def actiondelete_error(self, ctx, err):
        if isinstance(err, commands.MissingPermissions):
            await ctx.send(embed=error("Permission Denied", "You need **Manage Server** to delete actions."))


async def setup(bot):
    await bot.add_cog(Social(bot))
