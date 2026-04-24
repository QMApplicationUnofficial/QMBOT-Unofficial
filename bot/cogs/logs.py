"""
logs.py — Per-channel message logger

Stores the last 100 messages per channel, including deleted ones, in memory and JSON.

Commands (Manage Messages required):
  /logs [#channel]  — export channel log as JSON file
"""

import json
import re
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO

import discord
from discord.ext import commands

from config import DATA_DIR
from ui_utils import C, E, embed, error

LOG_CAPACITY = 100
DATA_PATH    = Path(DATA_DIR)
LOG_FILE     = DATA_PATH / "channel_logs.json"

CUSTOM_EMOJI_RE  = re.compile(r"<a?:([a-zA-Z0-9_]+):(\d+)>")
SHORTCODE_RE     = re.compile(r":([a-zA-Z0-9_]+):")
UNICODE_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001F9FF\U00002600-\U000027BF"
    "\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\u2702-\u27B0]+",
    re.UNICODE,
)


def _load_persisted() -> dict:
    if not LOG_FILE.exists():
        return {}
    try:
        with LOG_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_persisted(logs: dict):
    tmp = LOG_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)
    tmp.replace(LOG_FILE)


def _extract_emoji(content: str) -> dict:
    custom  = [{"name": m[0], "id": m[1]} for m in CUSTOM_EMOJI_RE.findall(content)]
    unicode_hits = UNICODE_EMOJI_RE.findall(content)
    codes   = [m for m in SHORTCODE_RE.findall(content) if not any(m == c["name"] for c in custom)]
    return {"unicode": unicode_hits, "custom": custom, "shortcodes": codes}


def _build_entry(message: discord.Message) -> dict:
    content = message.content or ""
    return {
        "message_id":     str(message.id),
        "author_id":      str(message.author.id),
        "author_name":    str(message.author),
        "author_display": message.author.display_name,
        "channel_id":     str(message.channel.id),
        "channel_name":   getattr(message.channel, "name", "DM"),
        "timestamp":      message.created_at.isoformat(),
        "timestamp_unix": message.created_at.timestamp(),
        "content":        content,
        "emoji":          _extract_emoji(content),
        "attachments":    [{"filename": a.filename, "url": a.url} for a in (message.attachments or [])],
        "stickers":       [{"name": s.name, "id": str(s.id)} for s in (message.stickers or [])],
        "reference":      str(message.reference.message_id) if message.reference else None,
        "deleted":        False,
        "edited":         False,
    }


_logs: dict[str, deque] = {}


def _get_log(channel_id: str) -> deque:
    if channel_id not in _logs:
        _logs[channel_id] = deque(maxlen=LOG_CAPACITY)
    return _logs[channel_id]


def _flush():
    try:
        _save_persisted({cid: list(q) for cid, q in _logs.items()})
    except Exception as e:
        print(f"[Logs] flush error: {e}")


def _load():
    for cid, entries in _load_persisted().items():
        _logs[cid] = deque(entries, maxlen=LOG_CAPACITY)


class Logs(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        _load()
        print("[Logs] Channel logs loaded.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        _get_log(str(message.channel.id)).append(_build_entry(message))
        _flush()

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        cid, mid = str(message.channel.id), str(message.id)
        for entry in _get_log(cid):
            if entry["message_id"] == mid:
                entry["deleted"] = True
                break
        _flush()

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild:
            return
        cid, mid = str(before.channel.id), str(before.id)
        for entry in _get_log(cid):
            if entry["message_id"] == mid:
                entry["edited"]         = True
                entry["edited_content"] = after.content or ""
                entry["edited_at"]      = after.edited_at.isoformat() if after.edited_at else None
                break
        _flush()

    @commands.hybrid_command(name="logs", description="Export last 100 messages from a channel as JSON (moderators only).")
    @commands.has_permissions(manage_messages=True)
    async def logs(self, ctx, channel: discord.TextChannel = None):
        target  = channel or ctx.channel
        cid     = str(target.id)
        entries = list(_get_log(cid))

        if not entries:
            return await ctx.send(embed=embed(
                f"{E.LOG}  Logs — #{target.name}",
                "No messages captured for this channel yet.",
                C.LOGS,
            ))

        total    = len(entries)
        deleted  = sum(1 for e in entries if e.get("deleted"))
        edited   = sum(1 for e in entries if e.get("edited"))

        from collections import Counter
        all_uni   = [u for e in entries for u in e.get("emoji", {}).get("unicode", [])]
        all_cust  = [c["name"] for e in entries for c in e.get("emoji", {}).get("custom", [])]

        def top(lst, n=3):
            return Counter(lst).most_common(n)

        output = {
            "exported_at":  datetime.now(timezone.utc).isoformat(),
            "channel_id":   cid,
            "channel_name": target.name,
            "guild_id":     str(target.guild.id),
            "guild_name":   target.guild.name,
            "summary": {
                "total":    total,
                "deleted":  deleted,
                "edited":   edited,
                "emoji_stats": {
                    "top_unicode": top(all_uni),
                    "top_custom":  top(all_cust),
                },
            },
            "messages": entries,
        }

        json_bytes = json.dumps(output, indent=2, ensure_ascii=False).encode("utf-8")
        file       = discord.File(BytesIO(json_bytes), filename=f"logs_{target.name}.json")

        top_emoji = ", ".join(e for e, _ in top(all_uni, 3)) or "none"
        top_cust  = ", ".join(f":{n}:" for n, _ in top(all_cust, 3)) or "none"

        e = embed(
            f"{E.LOG}  #{target.name} — Message Log",
            f"{E.CHECK} **{total}** messages captured\n"
            f"{E.DELETE} **{deleted}** deleted  ·  {E.EDIT} **{edited}** edited\n\n"
            f"**Top Unicode Emoji:** {top_emoji}\n"
            f"**Top Custom Emoji:** {top_cust}",
            C.LOGS,
            footer=f"Requested by {ctx.author.display_name}  ·  Moderators only",
        )
        await ctx.send(embed=e, file=file)

    @logs.error
    async def logs_error(self, ctx, err):
        if isinstance(err, commands.MissingPermissions):
            await ctx.send(embed=error("Logs", "You need **Manage Messages** to view logs."))
        else:
            raise err


async def setup(bot):
    await bot.add_cog(Logs(bot))
