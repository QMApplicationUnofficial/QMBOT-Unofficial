# utils.py
import io
import re
import zipfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import discord
from discord.ext import commands


# =========================
# Mentions / members
# =========================
def only_mention_target(ctx: commands.Context) -> Optional[int]:
    """
    Returns the mentioned user ID if exactly one user is mentioned.
    Otherwise returns None.
    """
    mentions = getattr(ctx.message, "mentions", None) or []
    if len(mentions) != 1:
        return None
    return mentions[0].id


async def get_member_safe(guild: discord.Guild, user_id: int) -> Optional[discord.Member]:
    """
    Try cache first, then fetch from API.
    Returns None if the member cannot be found or fetched.
    """
    member = guild.get_member(user_id)
    if member:
        return member

    try:
        return await guild.fetch_member(user_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None


# =========================
# Time helpers
# =========================
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_day_key(dt: Optional[datetime] = None) -> str:
    dt = dt or utc_now()
    return dt.strftime("%Y-%m-%d")


def fmt_hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def human_delta(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60

    if h > 0:
        return f"{h}h {m}m"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


# =========================
# Zip backup helpers (Railway-safe)
# =========================
def existing_files(paths: list[str]) -> list[str]:
    out = []
    for p in paths:
        try:
            path = Path(p)
            if path.exists() and path.is_file():
                out.append(str(path))
        except Exception:
            pass
    return out


def build_zip_bytes(
    file_paths: list[str],
    folder_name: str = "bot_backup"
) -> tuple[io.BytesIO, list[str]]:
    """
    Build an in-memory zip containing the provided files.
    Returns (buffer, included_files).
    """
    included = existing_files(file_paths)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path_str in included:
            path = Path(path_str)
            arcname = f"{folder_name}/{path.name}"
            zf.write(path, arcname=arcname)

    buf.seek(0)
    return buf, included


# =========================
# Regex helpers
# =========================
def compile_whole_word_regex(words: set[str]) -> re.Pattern:
    """
    Compile a case-insensitive whole-word regex from a set of words.
    Longer words are matched first.
    """
    safe_words = {str(w).strip() for w in words if str(w).strip()}
    if not safe_words:
        # matches nothing
        return re.compile(r"(?!x)x")

    return re.compile(
        r"\b(" + "|".join(map(re.escape, sorted(safe_words, key=len, reverse=True))) + r")\b",
        re.IGNORECASE,
    )
