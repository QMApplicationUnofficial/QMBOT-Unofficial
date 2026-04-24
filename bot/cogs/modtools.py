"""
modtools.py — Moderation and admin utility commands

All moderation tools are grouped under one command:

  /modaction slowmode
  /modaction lock
  /modaction unlock
  /modaction clear
  /modaction kick
  /modaction ban
  /modaction unban
  /modaction mute
  /modaction unmute
  /modaction nickname
  /modaction addrole
  /modaction removerole
  /modaction roleinfo
  /modaction rolemembers
  /modaction channelinfo
  /modaction voicemove
  /modaction voicekick
  /modaction massrole
  /modaction nuke
  /modaction warn
  /modaction warnings
  /modaction clearwarnings
  /modaction note
  /modaction notes

Owner-only restore command:
  !modaction restorejson   (attach a .zip in the same message)
"""

import io
import os
import shutil
import time
import zipfile
from datetime import timedelta
from pathlib import Path

import discord
from discord.ext import commands

from config import DATA_DIR
from storage import load_data, save_data
from ui_utils import C, embed, error, warn, success

WARN_KEY = "mod_warnings"
NOTE_KEY = "mod_notes"

DATA_PATH = Path(DATA_DIR).resolve()

OWNER_IDS = {
    734468552903360594,  # replace with your Discord user ID
}


def _get_mod_data(guild_id: str, key: str) -> dict:
    data = load_data()
    return data.get(guild_id, {}).get(key, {})


def _save_mod_data(guild_id: str, key: str, value: dict):
    data = load_data()
    data.setdefault(guild_id, {})[key] = value
    save_data(data)


class ModTools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _is_owner(self, user_id: int) -> bool:
        return user_id in OWNER_IDS

    @commands.hybrid_group(name="modaction", description="Moderation tools.")
    async def modaction(self, ctx):
        if ctx.invoked_subcommand is None:
            e = embed(
                "🛠️  Mod Action",
                (
                    "**Available subcommands:**\n"
                    "`slowmode`, `lock`, `unlock`, `clear`, `kick`, `ban`, `unban`,\n"
                    "`mute`, `unmute`, `nickname`, `addrole`, `removerole`,\n"
                    "`roleinfo`, `rolemembers`, `channelinfo`, `voicemove`, `voicekick`,\n"
                    "`massrole`, `nuke`, `warn`, `warnings`, `clearwarnings`, `note`, `notes`\n\n"
                    "**Backup restore:**\n"
                    "`!modaction restorejson` with a `.zip` attached"
                ),
                C.ADMIN,
            )
            await ctx.send(embed=e)

    # ══ CHANNEL MANAGEMENT ════════════════════════════════════════════════════

    @modaction.command(name="slowmode", description="Set channel slowmode (0 to disable).")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int):
        if not 0 <= seconds <= 21600:
            return await ctx.send(embed=error("Slowmode", "0–21600 seconds only."))
        await ctx.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await ctx.send(embed=success("Slowmode Disabled", f"Slowmode removed from {ctx.channel.mention}."))
        else:
            await ctx.send(embed=success("Slowmode Set", f"Slowmode set to **{seconds}s** in {ctx.channel.mention}."))

    @modaction.command(name="lock", description="Lock a channel so members can't send messages.")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx, channel: discord.TextChannel = None, *, reason: str = "No reason given"):
        ch = channel or ctx.channel
        overwrite = ch.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await ch.edit(overwrites={ctx.guild.default_role: overwrite})

        e = embed(
            "🔒  Channel Locked",
            f"{ch.mention} is now locked.\n\n_{reason}_",
            C.WARN,
            footer=f"Locked by {ctx.author.display_name}",
        )
        await ch.send(embed=e)

        if ch != ctx.channel:
            await ctx.send(embed=success("Locked", f"{ch.mention} has been locked."))

    @modaction.command(name="unlock", description="Unlock a channel.")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        overwrite = ch.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await ch.edit(overwrites={ctx.guild.default_role: overwrite})

        e = success("🔓  Channel Unlocked", f"{ch.mention} is now unlocked.")
        await ch.send(embed=e)

        if ch != ctx.channel:
            await ctx.send(embed=success("Unlocked", f"{ch.mention} has been unlocked."))

    @modaction.command(name="clear", description="Delete N messages from this channel.")
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int, member: discord.Member = None):
        if not 1 <= amount <= 200:
            return await ctx.send(embed=error("Clear", "Amount must be 1–200."))

        await ctx.defer(ephemeral=True)

        def check(m):
            return member is None or m.author == member

        deleted = await ctx.channel.purge(limit=amount, check=check)
        suffix = f" from {member.mention}" if member else ""
        await ctx.send(embed=success("Cleared", f"Deleted **{len(deleted)}** message(s){suffix}."), ephemeral=True)

    @modaction.command(name="nuke", description="Delete and recreate a channel (admin only).")
    @commands.has_permissions(administrator=True)
    async def nuke(self, ctx, *, reason: str = "Nuked"):
        ch = ctx.channel
        pos = ch.position
        new = await ch.clone(reason=f"Nuked by {ctx.author}")
        await new.edit(position=pos)
        await ch.delete()
        await new.send(
            embed=embed(
                "💥  Nuked",
                f"This channel was nuked by {ctx.author.mention}.\n_{reason}_",
                C.LOSE,
                footer=f"Nuked by {ctx.author.display_name}",
            )
        )

    @modaction.command(name="channelinfo", description="Info about a channel.")
    async def channelinfo(self, ctx, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        rows = [
            ("Name", ch.name),
            ("ID", str(ch.id)),
            ("Category", ch.category.name if ch.category else "None"),
            ("Position", str(ch.position)),
            ("Slowmode", f"{ch.slowmode_delay}s"),
            ("NSFW", "Yes" if ch.is_nsfw() else "No"),
            ("Created", ch.created_at.strftime("%d %b %Y")),
        ]
        col_w = max(len(r[0]) for r in rows)
        table = "\n".join(f"{r[0].ljust(col_w)}  {r[1]}" for r in rows)
        e = embed(f"#  {ch.name}", f"```\n{table}\n```", C.ADMIN)
        if ch.topic:
            e.add_field(name="Topic", value=ch.topic[:1024], inline=False)
        await ctx.send(embed=e)

    # ══ MEMBER MANAGEMENT ═════════════════════════════════════════════════════

    @modaction.command(name="kick", description="Kick a member from the server.")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "No reason given"):
        if member == ctx.author:
            return await ctx.send(embed=error("Kick", "You can't kick yourself."))
        if member.top_role >= ctx.author.top_role:
            return await ctx.send(embed=error("Kick", "You can't kick someone with an equal or higher role."))

        try:
            await member.send(embed=warn("Kicked", f"You were kicked from **{ctx.guild.name}**.\nReason: _{reason}_"))
        except Exception:
            pass

        await member.kick(reason=reason)
        e = success("Kicked 👢", f"**{member.display_name}** has been kicked.\nReason: _{reason}_")
        e.set_footer(text=f"By {ctx.author.display_name}")
        await ctx.send(embed=e)

    @modaction.command(name="ban", description="Ban a member from the server.")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "No reason given"):
        if member == ctx.author:
            return await ctx.send(embed=error("Ban", "You can't ban yourself."))
        if member.top_role >= ctx.author.top_role:
            return await ctx.send(embed=error("Ban", "You can't ban someone with an equal or higher role."))

        try:
            await member.send(embed=warn("Banned", f"You were banned from **{ctx.guild.name}**.\nReason: _{reason}_"))
        except Exception:
            pass

        await member.ban(reason=reason, delete_message_days=0)
        e = embed("🔨  Banned", f"**{member.display_name}** has been banned.\nReason: _{reason}_", C.LOSE)
        e.set_footer(text=f"By {ctx.author.display_name}")
        await ctx.send(embed=e)

    @modaction.command(name="unban", description="Unban a user by their ID.")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: str, *, reason: str = "Appeal accepted"):
        try:
            user = await self.bot.fetch_user(int(user_id))
            await ctx.guild.unban(user, reason=reason)
            await ctx.send(embed=success("Unbanned ✅", f"**{user}** has been unbanned.\nReason: _{reason}_"))
        except discord.NotFound:
            await ctx.send(embed=error("Unban", "That user is not banned or ID is invalid."))

    @modaction.command(name="mute", description="Timeout a user for a set number of minutes.")
    @commands.has_permissions(moderate_members=True)
    async def mute(self, ctx, member: discord.Member, minutes: int = 10, *, reason: str = "No reason given"):
        if not 1 <= minutes <= 40320:
            return await ctx.send(embed=error("Mute", "Duration: 1–40320 minutes (28 days max)."))

        until = discord.utils.utcnow() + timedelta(minutes=minutes)
        await member.timeout(until, reason=reason)

        e = embed(
            "🔇  Muted",
            f"**{member.display_name}** timed out for **{minutes}m**.\nReason: _{reason}_",
            C.WARN,
        )
        e.set_footer(text=f"By {ctx.author.display_name}")
        await ctx.send(embed=e)

    @modaction.command(name="unmute", description="Remove a user's timeout.")
    @commands.has_permissions(moderate_members=True)
    async def unmute(self, ctx, member: discord.Member, *, reason: str = "Timeout removed"):
        await member.timeout(None, reason=reason)
        await ctx.send(embed=success("Unmuted 🔊", f"**{member.display_name}**'s timeout has been removed."))

    @modaction.command(name="nickname", description="Change a member's server nickname.")
    @commands.has_permissions(manage_nicknames=True)
    async def nickname(self, ctx, member: discord.Member, *, nickname: str = ""):
        old = member.display_name
        await member.edit(nick=nickname or None)
        new = nickname or member.name
        await ctx.send(embed=success("Nickname Changed", f"**{old}** → **{new}**"))

    # ══ ROLE MANAGEMENT ═══════════════════════════════════════════════════════

    @modaction.command(name="addrole", description="Add a role to a member.")
    @commands.has_permissions(manage_roles=True)
    async def addrole(self, ctx, member: discord.Member, role: discord.Role):
        if role in member.roles:
            return await ctx.send(embed=warn("Add Role", f"{member.mention} already has {role.mention}."))
        await member.add_roles(role)
        await ctx.send(embed=success("Role Added ✅", f"Added {role.mention} to {member.mention}."))

    @modaction.command(name="removerole", description="Remove a role from a member.")
    @commands.has_permissions(manage_roles=True)
    async def removerole(self, ctx, member: discord.Member, role: discord.Role):
        if role not in member.roles:
            return await ctx.send(embed=warn("Remove Role", f"{member.mention} doesn't have {role.mention}."))
        await member.remove_roles(role)
        await ctx.send(embed=success("Role Removed ✅", f"Removed {role.mention} from {member.mention}."))

    @modaction.command(name="roleinfo", description="Info about a role.")
    async def roleinfo(self, ctx, role: discord.Role):
        member_count = len(role.members)
        rows = [
            ("Name", role.name),
            ("ID", str(role.id)),
            ("Colour", str(role.colour)),
            ("Members", str(member_count)),
            ("Mentionable", "Yes" if role.mentionable else "No"),
            ("Hoisted", "Yes" if role.hoist else "No"),
            ("Position", str(role.position)),
            ("Created", role.created_at.strftime("%d %b %Y")),
        ]
        col_w = max(len(r[0]) for r in rows)
        table = "\n".join(f"{r[0].ljust(col_w)}  {r[1]}" for r in rows)
        e = embed(f"🎭  {role.name}", f"```\n{table}\n```", role.colour or C.ADMIN)
        await ctx.send(embed=e)

    @modaction.command(name="rolemembers", description="List members who have a specific role.")
    async def rolemembers(self, ctx, role: discord.Role):
        members = role.members[:30]
        if not members:
            return await ctx.send(embed=embed("🎭  Role Members", f"No one has {role.mention}.", C.NEUTRAL))
        names = ", ".join(m.display_name for m in members)
        extra = f" (+{len(role.members) - 30} more)" if len(role.members) > 30 else ""
        e = embed(f"🎭  {role.name} — {len(role.members)} member(s)", names + extra, C.ADMIN)
        await ctx.send(embed=e)

    @modaction.command(name="massrole", description="Add or remove a role from all members (admin).")
    @commands.has_permissions(administrator=True)
    async def massrole(self, ctx, action: str, role: discord.Role):
        action = action.lower()
        if action not in ("add", "remove"):
            return await ctx.send(embed=error("Mass Role", "Action must be `add` or `remove`."))

        await ctx.send(embed=warn("Mass Role", f"Processing **{len(ctx.guild.members)}** members…"))
        count = 0

        for member in ctx.guild.members:
            if member.bot:
                continue
            try:
                if action == "add" and role not in member.roles:
                    await member.add_roles(role)
                    count += 1
                elif action == "remove" and role in member.roles:
                    await member.remove_roles(role)
                    count += 1
            except Exception:
                pass

        await ctx.send(
            embed=success(
                f"Mass Role — {action.capitalize()}d",
                f"{action.capitalize()}d {role.mention} for **{count}** member(s).",
            )
        )

    # ══ VOICE MANAGEMENT ══════════════════════════════════════════════════════

    @modaction.command(name="voicemove", description="Move all members from one VC to another.")
    @commands.has_permissions(move_members=True)
    async def voicemove(self, ctx, from_channel: discord.VoiceChannel, to_channel: discord.VoiceChannel):
        members = list(from_channel.members)
        if not members:
            return await ctx.send(embed=warn("Voice Move", f"{from_channel.mention} is empty."))

        count = 0
        for m in members:
            try:
                await m.move_to(to_channel)
                count += 1
            except Exception:
                pass

        await ctx.send(embed=success("Voice Move ✅", f"Moved **{count}** member(s) to {to_channel.mention}."))

    @modaction.command(name="voicekick", description="Disconnect a user from voice.")
    @commands.has_permissions(move_members=True)
    async def voicekick(self, ctx, member: discord.Member):
        if not member.voice:
            return await ctx.send(embed=warn("Voice Kick", f"{member.display_name} is not in a voice channel."))
        await member.move_to(None)
        await ctx.send(embed=success("Disconnected 🔇", f"**{member.display_name}** has been removed from voice."))

    # ══ WARNING SYSTEM ════════════════════════════════════════════════════════

    @modaction.command(name="warn", description="Add a warning to a user's record.")
    @commands.has_permissions(manage_messages=True)
    async def warn_member(self, ctx, member: discord.Member, *, reason: str):
        gid = str(ctx.guild.id)
        uid = str(member.id)
        warnings = _get_mod_data(gid, WARN_KEY)
        warnings.setdefault(uid, [])

        entry = {
            "reason": reason,
            "by": ctx.author.display_name,
            "at": int(time.time()),
        }
        warnings[uid].append(entry)
        _save_mod_data(gid, WARN_KEY, warnings)

        count = len(warnings[uid])

        try:
            await member.send(
                embed=warn(
                    "Warning Received",
                    f"You received a warning in **{ctx.guild.name}**.\nReason: _{reason}_\nYou now have **{count}** warning(s).",
                )
            )
        except Exception:
            pass

        e = embed(
            f"⚠️  Warning #{count} — {member.display_name}",
            f"Reason: _{reason}_\nTotal warnings: **{count}**",
            C.WARN,
            footer=f"By {ctx.author.display_name}",
        )
        await ctx.send(embed=e)

    @modaction.command(name="warnings", description="View a user's warning history.")
    @commands.has_permissions(manage_messages=True)
    async def warnings(self, ctx, member: discord.Member):
        gid = str(ctx.guild.id)
        uid = str(member.id)
        warning_list = _get_mod_data(gid, WARN_KEY).get(uid, [])

        if not warning_list:
            return await ctx.send(embed=success("No Warnings", f"{member.display_name} has no warnings."))

        lines = []
        for i, w in enumerate(warning_list, 1):
            ts = f"<t:{w['at']}:d>" if "at" in w else "Unknown"
            lines.append(f"**#{i}** {ts} — _{w['reason']}_ (by {w['by']})")

        e = embed(f"⚠️  {member.display_name}'s Warnings ({len(warning_list)})", "\n".join(lines[-10:]), C.WARN)
        e.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=e)

    @modaction.command(name="clearwarnings", description="Clear all warnings for a user (admin only).")
    @commands.has_permissions(administrator=True)
    async def clearwarnings(self, ctx, member: discord.Member):
        gid = str(ctx.guild.id)
        uid = str(member.id)
        warnings = _get_mod_data(gid, WARN_KEY)
        warnings.pop(uid, None)
        _save_mod_data(gid, WARN_KEY, warnings)
        await ctx.send(embed=success("Warnings Cleared", f"All warnings for **{member.display_name}** have been removed."))

    # ══ MOD NOTES ═════════════════════════════════════════════════════════════

    @modaction.command(name="note", description="Add a mod note to a user (invisible to them).")
    @commands.has_permissions(manage_messages=True)
    async def note(self, ctx, member: discord.Member, *, note_text: str):
        gid = str(ctx.guild.id)
        uid = str(member.id)
        notes = _get_mod_data(gid, NOTE_KEY)
        notes.setdefault(uid, [])
        notes[uid].append(
            {
                "text": note_text,
                "by": ctx.author.display_name,
                "at": int(time.time()),
            }
        )
        _save_mod_data(gid, NOTE_KEY, notes)
        await ctx.send(embed=success("Note Added 📝", f"Note added to **{member.display_name}** (#{len(notes[uid])})."))

    @modaction.command(name="notes", description="View mod notes for a user.")
    @commands.has_permissions(manage_messages=True)
    async def notes(self, ctx, member: discord.Member):
        gid = str(ctx.guild.id)
        uid = str(member.id)
        note_list = _get_mod_data(gid, NOTE_KEY).get(uid, [])

        if not note_list:
            return await ctx.send(embed=embed("📝  No Notes", f"No notes for **{member.display_name}**.", C.NEUTRAL))

        lines = [
            f"**#{i}** <t:{n['at']}:d> — _{n['text']}_ (by {n['by']})"
            for i, n in enumerate(note_list[-10:], 1)
        ]
        e = embed(f"📝  Notes for {member.display_name} ({len(note_list)})", "\n".join(lines), C.ADMIN)
        await ctx.send(embed=e)

    # ══ RESTORE JSON FROM ZIP ═════════════════════════════════════════════════

    @modaction.command(name="restorejson", description="Restore JSON files from a backup zip (owner only; prefix usage recommended).")
    async def restorejson(self, ctx):
        if not self._is_owner(ctx.author.id):
            return await ctx.send(embed=error("Restore JSON", "Owner only command."))

        if not getattr(ctx.message, "attachments", None):
            return await ctx.send(embed=error("Restore JSON", "Attach a `.zip` file to the same message."))

        attachment = ctx.message.attachments[0]

        if not attachment.filename.lower().endswith(".zip"):
            return await ctx.send(embed=error("Restore JSON", "Attachment must be a `.zip` file."))

        DATA_PATH.mkdir(parents=True, exist_ok=True)
        pre_restore_dir = DATA_PATH / "pre_restore_backup"
        pre_restore_dir.mkdir(parents=True, exist_ok=True)

        await ctx.send(embed=warn("Restore JSON", "Reading backup zip and restoring JSON files..."))

        try:
            raw = await attachment.read()

            # Backup existing live jsons first
            for existing in DATA_PATH.glob("*.json"):
                backup_target = pre_restore_dir / existing.name
                try:
                    shutil.copy2(existing, backup_target)
                except Exception:
                    pass

            restored = []
            skipped = []

            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                names = zf.namelist()
                json_members = [name for name in names if name.lower().endswith(".json")]

                if not json_members:
                    return await ctx.send(embed=error("Restore JSON", "No `.json` files found in that zip."))

                for member in json_members:
                    filename = os.path.basename(member)

                    if not filename or filename in {".", ".."}:
                        skipped.append(member)
                        continue

                    target_path = DATA_PATH / filename

                    with zf.open(member) as src:
                        data = src.read()

                    with open(target_path, "wb") as f:
                        f.write(data)

                    restored.append(filename)

            desc_parts = []
            if restored:
                lines = "\n".join(f"- `{name}`" for name in restored[:25])
                if len(restored) > 25:
                    lines += f"\n...and {len(restored) - 25} more"
                desc_parts.append(f"**Restored:**\n{lines}")

            if skipped:
                lines = "\n".join(f"- `{name}`" for name in skipped[:10])
                if len(skipped) > 10:
                    lines += f"\n...and {len(skipped) - 10} more"
                desc_parts.append(f"**Skipped:**\n{lines}")

            desc_parts.append(f"**Path:** `{DATA_PATH}`")
            desc_parts.append("Current live JSON files were backed up to `pre_restore_backup` first.")

            await ctx.send(embed=success("Restore Complete", "\n\n".join(desc_parts)))

        except zipfile.BadZipFile:
            await ctx.send(embed=error("Restore JSON", "That file is not a valid zip archive."))
        except Exception as e:
            await ctx.send(embed=error("Restore JSON", f"Restore failed: {e}"))

    # ══ ERROR HANDLERS ════════════════════════════════════════════════════════

    async def cog_command_error(self, ctx, error_obj):
        if isinstance(error_obj, commands.MissingPermissions):
            await ctx.send(embed=error("Permission Denied", f"You're missing: `{', '.join(error_obj.missing_permissions)}`"))
        elif isinstance(error_obj, commands.BotMissingPermissions):
            await ctx.send(embed=error("Bot Missing Permissions", f"I need: `{', '.join(error_obj.missing_permissions)}`"))
        else:
            raise error_obj


async def setup(bot: commands.Bot):
    await bot.add_cog(ModTools(bot))
