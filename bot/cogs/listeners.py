import time
import re
from datetime import datetime, timezone

import discord
from discord.ext import commands

from config import (
    XP_PER_MESSAGE,
    TOP_ROLE_NAME,
    WELCOME_CHANNEL_ID,
    LEVEL_ANNOUNCE_CHANNEL_ID,
    SWEAR_FINE_ENABLED,
    SWEAR_FINE_AMOUNT,
)
from storage import (
    load_data,
    save_data,
    load_swear_jar,
    save_swear_jar,
    load_coins,
    save_coins,
)

# =========================
# Style
# =========================
from ui_utils import C, E, embed as _ui_embed
EMBED_COLOR = C.NEUTRAL

# =========================
# Stars
# =========================
STAR_REACTION_EMOJIS = {"⭐", "🌟"}

# =========================
# AFK
# =========================
AFK_STATUS = {}  # key = f"{guild_id}-{user_id}" -> reason

# =========================
# Swear jar
# =========================
SWEAR_WORDS = {
    "fuck", "fucking", "shit", "bullshit", "bitch", "asshole", "bastard",
    "dick", "piss", "crap", "damn", "bloody", "wanker", "twat"
}

SWEAR_RE = re.compile(
    r"\b(" + "|".join(map(re.escape, sorted(SWEAR_WORDS, key=len, reverse=True))) + r")\b",
    re.IGNORECASE
)

SWEAR_COUNT_COOLDOWN = 2
_LAST_SWEAR_COUNT_AT = {}  # user_id -> unix timestamp

# =========================
# Banned name filter (faeez / husna + leet-speak variations)
# =========================
# Each character class covers the original letter plus common substitutions.
# The patterns are intentionally loose so things like "f4333z" still match.

_FAEEZ_PATTERN = re.compile(
    r"[fF][^a-zA-Z0-9]*"          # f
    r"[aA4@][^a-zA-Z0-9]*"        # a → a, 4, @
    r"[eE3][^a-zA-Z0-9]*"         # e → e, 3
    r"[eE3][^a-zA-Z0-9]*"         # e → e, 3  (handles fa33z / fa3ez etc.)
    r"[zZ2$]",                     # z → z, 2, $
)

_HUSNA_PATTERN = re.compile(
    r"[hH][^a-zA-Z0-9]*"          # h
    r"[uU][^a-zA-Z0-9]*"          # u
    r"[sS$5][^a-zA-Z0-9]*"        # s → s, $, 5
    r"[nN][^a-zA-Z0-9]*"          # n
    r"[aA4@]",                     # a → a, 4, @
)

BANNED_NAME_PATTERNS = [_FAEEZ_PATTERN, _HUSNA_PATTERN]


def contains_banned_name(text: str) -> bool:
    """Return True if the text contains any banned name / leet-speak variant."""
    for pattern in BANNED_NAME_PATTERNS:
        if pattern.search(text):
            return True
    return False


# =========================
# Helpers
# =========================
def make_embed(title: str | None = None, description: str = "", color=EMBED_COLOR):
    e = discord.Embed(description=description, color=color)
    if title:
        e.title = title
    return e


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def ensure_user_coins(user_id):
    uid = str(user_id)
    coins = load_coins()

    if uid not in coins:
        coins[uid] = {
            "wallet": 100,
            "bank": 0,
            "stars": 0,
            "last_daily": 0,
            "last_rob": 0,
            "last_beg": 0,
            "last_bankrob": 0,
            "portfolio": {},
            "pending_portfolio": [],
            "active_effects": {},
            "trade_meta": {
                "last_trade_ts": {},
                "daily": {"day": "", "count": 0}
            },
            "star_meta": {
                "day": _today_key(),
                "given": {}
            }
        }
        save_coins(coins)
    else:
        data = coins[uid]
        changed = False

        defaults = {
            "wallet": 100,
            "bank": 0,
            "stars": 0,
            "last_daily": 0,
            "last_rob": 0,
            "last_beg": 0,
            "last_bankrob": 0,
            "portfolio": {},
            "pending_portfolio": [],
            "active_effects": {},
            "trade_meta": {
                "last_trade_ts": {},
                "daily": {"day": "", "count": 0}
            },
            "star_meta": {
                "day": _today_key(),
                "given": {}
            }
        }

        for key, value in defaults.items():
            if key not in data:
                data[key] = value
                changed = True

        if not isinstance(data.get("active_effects"), dict):
            data["active_effects"] = {}
            changed = True

        if not isinstance(data.get("star_meta"), dict):
            data["star_meta"] = {
                "day": _today_key(),
                "given": {}
            }
            changed = True

        data["star_meta"].setdefault("day", _today_key())
        data["star_meta"].setdefault("given", {})

        if data["star_meta"]["day"] != _today_key():
            data["star_meta"] = {
                "day": _today_key(),
                "given": {}
            }
            changed = True

        if changed:
            save_coins(coins)

    return coins


def calculate_level(xp: int) -> int:
    return int(int(xp) ** 0.5)


def add_swears(user_id: int, count: int):
    if count <= 0:
        return

    jar = load_swear_jar()
    if not isinstance(jar, dict):
        jar = {"total": 0, "users": {}}

    jar.setdefault("total", 0)
    jar.setdefault("users", {})

    uid = str(user_id)
    jar["total"] = int(jar.get("total", 0)) + count

    jar["users"].setdefault(uid, {})
    jar["users"][uid].setdefault("count", 0)
    jar["users"][uid]["count"] = int(jar["users"][uid]["count"]) + count

    save_swear_jar(jar)


async def update_top_exp_role(guild: discord.Guild):
    data = load_data()
    gid = str(guild.id)

    if gid not in data or not data[gid]:
        return

    top_user_id, _ = max(data[gid].items(), key=lambda x: int(x[1].get("xp", 0)))
    top_member = guild.get_member(int(top_user_id))
    if not top_member:
        return

    role = discord.utils.get(guild.roles, name=TOP_ROLE_NAME)
    if not role:
        try:
            role = await guild.create_role(name=TOP_ROLE_NAME)
        except discord.Forbidden:
            return

    for member in guild.members:
        if role in member.roles and member != top_member:
            try:
                await member.remove_roles(role)
            except Exception:
                pass

    if role not in top_member.roles:
        try:
            await top_member.add_roles(role)
        except Exception:
            pass


async def update_xp(bot: commands.Bot, user_id: int, guild_id: int, xp_amount: int):
    data = load_data()
    gid = str(guild_id)
    uid = str(user_id)

    data.setdefault(gid, {})
    user = data[gid].setdefault(uid, {"xp": 0})

    prev_xp = int(user.get("xp", 0))
    prev_level = int(user.get("level", calculate_level(prev_xp)))

    user["xp"] = prev_xp + int(xp_amount)
    new_level = calculate_level(user["xp"])
    user["level"] = new_level

    save_data(data)

    guild = bot.get_guild(int(gid))
    if not guild:
        return

    if new_level > prev_level and new_level % 5 == 0:
        channel = bot.get_channel(LEVEL_ANNOUNCE_CHANNEL_ID)
        if channel:
            try:
                user_obj = await bot.fetch_user(user_id)
                await channel.send(
                    embed=make_embed(
                        "🎉  Level Up!",
                        f"🎉 {user_obj.mention} just reached level **{new_level}**! 🚀"
                    )
                )
            except Exception:
                pass

    if new_level > prev_level and new_level % 10 == 0:
        role_name = f"Level {new_level}"
        role = discord.utils.get(guild.roles, name=role_name)

        if not role:
            try:
                role = await guild.create_role(name=role_name)
            except discord.Forbidden:
                role = None

        member = guild.get_member(int(uid))
        if role and member:
            try:
                await member.add_roles(role)
            except Exception:
                pass

    await update_top_exp_role(guild)


class Listeners(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------------------
    # Welcome
    # -------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
        if not channel:
            return

        embed = discord.Embed(
            title=f"👋  Welcome to {member.guild.name}!",
            description=(
                f"{member.mention}, we're glad to have you here.\n\n"
                "Read through the channels, introduce yourself, and have fun! 🎉"
            ),
            color=EMBED_COLOR
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)

    # -------------------------
    # Star reactions
    # -------------------------
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if user.bot:
            return

        if str(reaction.emoji) not in STAR_REACTION_EMOJIS:
            return

        message = reaction.message

        if not message.guild:
            return

        if message.author.bot:
            return

        if message.author.id == user.id:
            return

        coins = load_coins()

        giver = ensure_user_coins(user.id)[str(user.id)]
        coins = load_coins()
        receiver = ensure_user_coins(message.author.id)[str(message.author.id)]
        coins = load_coins()

        giver = coins[str(user.id)]
        receiver = coins[str(message.author.id)]

        giver.setdefault("star_meta", {"day": _today_key(), "given": {}})
        giver["star_meta"].setdefault("day", _today_key())
        giver["star_meta"].setdefault("given", {})

        if giver["star_meta"]["day"] != _today_key():
            giver["star_meta"] = {
                "day": _today_key(),
                "given": {}
            }

        target_key = str(message.author.id)
        given_today = int(giver["star_meta"]["given"].get(target_key, 0))

        if given_today >= 2:
            return

        giver["star_meta"]["given"][target_key] = given_today + 1
        receiver["stars"] = int(receiver.get("stars", 0)) + 1

        save_coins(coins)

        try:
            await message.channel.send(
                embed=make_embed(
                    "⭐  Golden Star",
                    f"{message.author.mention} got a **golden star** from {user.mention}.\n"
                    f"✦ Stars: **{receiver['stars']}**"
                ),
                delete_after=3
            )
        except Exception:
            pass

    # -------------------------
    # Main message listener
    # -------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # ── Banned name filter (faeez / husna + all leet variants) ──────────
        if message.guild and contains_banned_name(message.content or ""):
            try:
                await message.delete()
            except discord.Forbidden:
                pass

            await message.channel.send(
                embed=make_embed(
                    "🚫  Filtered",
                    f"{message.author.mention} that name is not allowed here."
                ),
                delete_after=5
            )
            return
        # ─────────────────────────────────────────────────────────────────────

        if message.guild:
            try:
                now_ts = time.time()
                last_ts = _LAST_SWEAR_COUNT_AT.get(message.author.id, 0)

                if now_ts - last_ts >= SWEAR_COUNT_COOLDOWN:
                    matches = SWEAR_RE.findall(message.content or "")
                    swear_count = len(matches)

                    if swear_count > 0:
                        _LAST_SWEAR_COUNT_AT[message.author.id] = now_ts
                        add_swears(message.author.id, swear_count)

                        if SWEAR_FINE_ENABLED and SWEAR_FINE_AMOUNT > 0:
                            coins = ensure_user_coins(message.author.id)
                            uid = str(message.author.id)

                            fine = SWEAR_FINE_AMOUNT * swear_count
                            wallet = int(coins[uid].get("wallet", 0))
                            taken = min(wallet, fine)
                            coins[uid]["wallet"] = wallet - taken
                            save_coins(coins)

                        jar = load_swear_jar()
                        total = int(jar.get("total", 0))

                        await message.channel.send(
                            embed=make_embed(
                                "🫙  Swear Jar",
                                f"{message.author.mention} added **{swear_count}** coin(s) to the swear jar.\n"
                                f"Server total: **{total}**"
                            ),
                            delete_after=5
                        )

            except Exception as e:
                print(f"[SwearJar] failed: {type(e).__name__}: {e}")

        if message.guild and "rigged" in (message.content or "").lower():
            try:
                await message.delete()
            except discord.Forbidden:
                pass

            await message.channel.send(
                embed=make_embed(
                    "🔪  Filtered",
                    f"{message.author.mention} its fair 🔪"
                ),
                delete_after=5
            )
            return

        if message.guild:
            key = f"{message.guild.id}-{message.author.id}"

            if key in AFK_STATUS:
                del AFK_STATUS[key]
                await message.channel.send(
                    embed=make_embed(
                        "✅  Back Online",
                        f"{message.author.mention} is no longer AFK."
                    )
                )

            for user in message.mentions:
                mention_key = f"{message.guild.id}-{user.id}"
                if mention_key in AFK_STATUS:
                    reason = AFK_STATUS[mention_key]
                    await message.channel.send(
                        embed=make_embed(
                            "💤  User is AFK",
                            f"{user.display_name} is currently AFK: {reason}"
                        )
                    )

            try:
                await update_xp(
                    self.bot,
                    message.author.id,
                    message.guild.id,
                    XP_PER_MESSAGE
                )
            except Exception as e:
                print(f"[XP] update_xp failed: {type(e).__name__}: {e}")

    # -------------------------
    # AFK command
    # -------------------------
    @commands.hybrid_command(
        name="afk",
        description="Set your AFK status with a reason."
    )
    async def afk(self, ctx: commands.Context, *, reason: str = "💤  AFK"):
        if not ctx.guild:
            return await ctx.send(
                embed=make_embed("AFK", "AFK only works in servers.")
            )

        key = f"{ctx.guild.id}-{ctx.author.id}"
        AFK_STATUS[key] = reason

        await ctx.send(
            embed=make_embed(
                "💤  AFK Set",
                f"{ctx.author.mention} is now AFK: {reason}"
            )
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Listeners(bot))
