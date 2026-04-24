"""
ui_utils.py — Shared design system for QMBOT
Defines colours, emoji constants, and polished embed builders used across all cogs.
"""
import discord

# ============================================================
# Colour Palette
# ============================================================

class C:
    """Brand colours used across the bot."""
    # Primary per-cog accents
    ECONOMY   = discord.Color.from_rgb(159, 89, 255)   # vivid purple
    GAMES     = discord.Color.from_rgb(56, 182, 255)    # electric blue
    MARKET    = discord.Color.from_rgb(0, 214, 143)     # emerald green
    SHOP      = discord.Color.from_rgb(255, 165, 0)     # rich amber
    SOCIAL    = discord.Color.from_rgb(255, 87, 139)    # hot pink
    TRIVIA    = discord.Color.from_rgb(255, 200, 40)    # golden yellow
    MARRIAGE  = discord.Color.from_rgb(255, 105, 180)   # pastel pink
    SWEAR     = discord.Color.from_rgb(200, 80, 80)     # deep red
    ADMIN     = discord.Color.from_rgb(100, 120, 160)   # slate blue
    LOGS      = discord.Color.from_rgb(90, 200, 200)    # teal
    MC        = discord.Color.from_rgb(80, 200, 90)     # grass green

    # State colours (shared)
    WIN       = discord.Color.from_rgb(57, 220, 130)    # success green
    LOSE      = discord.Color.from_rgb(240, 80, 80)     # failure red
    WARN      = discord.Color.from_rgb(255, 193, 7)     # amber warning
    NEUTRAL   = discord.Color.from_rgb(72, 80, 100)     # dark neutral
    DEBT      = discord.Color.from_rgb(220, 50, 50)     # debt red

# ============================================================
# Emoji Constants
# ============================================================

class E:
    # Currency / economy
    COIN      = "🪙"
    BANK      = "🏦"
    STAR      = "⭐"
    WALLET    = "👛"
    CHART     = "📈"
    CHART_DN  = "📉"
    DEBT      = "💸"
    TAX       = "🧾"
    WORK      = "💼"
    PAY       = "💳"
    DAILY     = "📅"
    BEG       = "🙏"
    ROB       = "🦹"
    SAFE      = "🔐"
    TROPHY    = "🏆"

    # Games
    DICE      = "🎲"
    CARDS     = "🃏"
    COIN_FLIP = "🪙"
    WIN       = "🎉"
    LOSE      = "💥"
    JACKPOT   = "💎"

    # Shop
    BAG       = "🛍️"
    ITEM      = "📦"
    PRICE_TAG = "🏷️"
    STOCK_OUT = "⛔"
    RESTOCK   = "🔄"

    # Social / actions
    HEART     = "❤️"
    FIRE      = "🔥"
    CLAP      = "👏"
    WARN_ACT  = "⚠️"
    SKULL     = "💀"

    # Trivia
    CORRECT   = "✅"
    WRONG     = "❌"
    STREAK    = "🔥"
    QUESTION  = "❓"

    # Logs
    LOG       = "📋"
    DELETE    = "🗑️"
    EDIT      = "✏️"
    EMOJI     = "😊"

    # Misc
    CLOCK     = "⏰"
    LOCK      = "🔒"
    CHECK     = "✅"
    CROSS     = "❌"
    ARROW     = "➤"
    SPARKLE   = "✨"
    CROWN     = "👑"
    SHIELD    = "🛡️"

# ============================================================
# Embed Builders
# ============================================================

def embed(
    title: str,
    description: str = "",
    color: discord.Color = C.NEUTRAL,
    footer: str | None = None,
    thumbnail: str | None = None,
) -> discord.Embed:
    """Standard embed factory."""
    e = discord.Embed(title=title, description=description, color=color)
    if footer:
        e.set_footer(text=footer)
    if thumbnail:
        e.set_thumbnail(url=thumbnail)
    return e


def success(title: str, description: str = "", footer: str | None = None) -> discord.Embed:
    return embed(f"{E.WIN}  {title}", description, C.WIN, footer)


def error(title: str, description: str = "", footer: str | None = None) -> discord.Embed:
    return embed(f"{E.CROSS}  {title}", description, C.LOSE, footer)


def warn(title: str, description: str = "", footer: str | None = None) -> discord.Embed:
    return embed(f"{E.WARN_ACT}  {title}", description, C.WARN, footer)


def info(title: str, description: str = "", color: discord.Color = C.NEUTRAL, footer: str | None = None) -> discord.Embed:
    return embed(title, description, color, footer)


def balance_bar(wallet: int, bank: int, debt: int = 0) -> str:
    """Render a compact inline balance summary string."""
    parts = [
        f"{E.WALLET} **{wallet:,}**",
        f"{E.BANK} **{bank:,}**",
    ]
    if debt > 0:
        parts.append(f"{E.DEBT} **{debt:,}** owed")
    return "  ·  ".join(parts)


def leaderboard_block(rows: list[tuple[str, str]]) -> str:
    """
    rows = list of (name, value_str) tuples.
    Returns a pretty formatted leaderboard in a code block.
    Medals for top 3.
    """
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (name, val) in enumerate(rows):
        medal = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"{medal}  {name:<20} {val}")
    return "```\n" + "\n".join(lines) + "\n```"


def cooldown_str(seconds: int) -> str:
    """Human-readable cooldown string."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"
