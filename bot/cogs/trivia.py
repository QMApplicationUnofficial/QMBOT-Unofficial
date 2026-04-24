import random
import time
import aiohttp
import discord
from discord.ext import commands

from storage import (
    load_trivia_stats, save_trivia_stats,
    load_trivia_streaks, save_trivia_streaks,
    load_coins, save_coins,
    load_data,
)
from cogs.listeners import update_xp
from ui_utils import C, E, embed, success, error, warn

TRIVIA_RESET_PENALTY_SECONDS = 86400
TRIVIA_RESET_MULTIPLIER      = 0.25


def ensure_user_coins(user_id):
    uid   = str(user_id)
    coins = load_coins()
    if uid not in coins:
        coins[uid] = {
            "wallet": 100, "bank": 0, "last_daily": 0,
            "last_rob": 0, "last_beg": 0, "last_bankrob": 0,
            "portfolio": {}, "pending_portfolio": [],
            "trade_meta": {"last_trade_ts": {}, "daily": {"day": "", "count": 0}},
        }
        save_coins(coins)
    return coins


def add_trivia_result(uid: str, category: str, correct: bool):
    stats = load_trivia_stats()
    cat   = stats.setdefault(uid, {}).setdefault(category, {"correct": 0, "attempts": 0})
    cat["attempts"] += 1
    if correct:
        cat["correct"] += 1
    save_trivia_stats(stats)


class TriviaView(discord.ui.View):
    def __init__(self, *, author_id, options, correct_answer):
        super().__init__(timeout=20)
        self.author_id      = author_id
        self.options        = options
        self.correct_answer = correct_answer
        self.chosen_answer  = None
        self.timed_out      = False
        labels = ["🇦", "🇧", "🇨", "🇩"]
        for i, option in enumerate(options):
            btn          = discord.ui.Button(label=f"{labels[i]}  {option[:60]}", style=discord.ButtonStyle.secondary)
            btn.callback = self._make_cb(option)
            self.add_item(btn)

    def _make_cb(self, option):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                return await interaction.response.send_message(
                    embed=error("Trivia", "This question isn't yours."), ephemeral=True)
            self.chosen_answer = option
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)
            self.stop()
        return callback

    async def on_timeout(self):
        self.timed_out = True
        for child in self.children:
            child.disabled = True


class Trivia(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="trivia", description="Answer a trivia question and win coins.")
    async def trivia(self, ctx):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://the-trivia-api.com/v2/questions") as resp:
                    if resp.status != 200:
                        return await ctx.send(embed=error("Trivia", "Trivia API is currently unavailable."))
                    data = await resp.json()
        except Exception:
            return await ctx.send(embed=error("Trivia", "Couldn't reach the trivia API."))
        if not data:
            return await ctx.send(embed=error("Trivia", "No question returned."))

        q        = data[0]
        question = q["question"]["text"]
        correct  = q["correctAnswer"]
        options  = q["incorrectAnswers"] + [correct]
        random.shuffle(options)
        raw_cat  = q.get("category", "General")
        category = str(raw_cat[0] if isinstance(raw_cat, list) and raw_cat else raw_cat).title()
        labels   = ["🇦", "🇧", "🇨", "🇩"]
        option_text = "\n".join(f"{labels[i]}  {opt}" for i, opt in enumerate(options))

        e = embed(
            f"{E.QUESTION}  Trivia",
            f"**{question}**\n\n{option_text}",
            C.TRIVIA,
            footer=f"Category: {category}  ·  You have 20 seconds",
        )
        view = TriviaView(author_id=ctx.author.id, options=options, correct_answer=correct)
        msg  = await ctx.send(embed=e, view=view)
        await view.wait()

        if view.timed_out:
            await msg.edit(view=view)
            return await ctx.send(embed=warn("Time's Up!", f"The correct answer was **{correct}**."))

        uid     = str(ctx.author.id)
        streaks = load_trivia_streaks()
        streak  = int(streaks.get(uid, 0))
        chosen  = view.chosen_answer

        if chosen == correct:
            streak    += 1
            base       = 50
            bonus      = 5 * min(streak - 1, 10)
            reward     = base + bonus
            data_store = load_data()
            reset_ts   = data_store.get("economy_reset_ts", 0)
            if (time.time() - reset_ts) < TRIVIA_RESET_PENALTY_SECONDS:
                reward = max(5, int(reward * TRIVIA_RESET_MULTIPLIER))
            coins = ensure_user_coins(ctx.author.id)
            coins[uid]["wallet"] += reward
            save_coins(coins)
            try:
                if ctx.guild:
                    await update_xp(self.bot, ctx.author.id, ctx.guild.id, 20)
            except Exception:
                pass
            add_trivia_result(uid, category, True)
            streaks[uid] = streak
            save_trivia_streaks(streaks)
            streak_txt = f"{E.STREAK} **Streak: {streak}**" if streak > 1 else ""
            e = embed(
                f"{E.CORRECT}  Correct!",
                f"The answer was **{correct}**.\n\n{E.COIN} +**{reward:,}** coins  {streak_txt}",
                C.WIN,
                footer=f"Category: {category}",
            )
            e.add_field(name=f"{E.WALLET} Wallet", value=f"`{coins[uid]['wallet']:,}`", inline=False)
        else:
            add_trivia_result(uid, category, False)
            streaks[uid] = 0
            save_trivia_streaks(streaks)
            e = embed(
                f"{E.WRONG}  Incorrect",
                f"You chose **{chosen}**.\nThe correct answer was **{correct}**.",
                C.LOSE,
                footer=f"Category: {category}  ·  Streak reset",
            )
        await ctx.send(embed=e)

    @commands.hybrid_command(name="triviastats", description="View trivia stats.")
    async def triviastats(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        stats  = load_trivia_stats()
        uid    = str(member.id)
        if uid not in stats:
            return await ctx.send(embed=embed(f"{E.QUESTION}  Trivia Stats", f"{member.display_name} hasn't played yet.", C.TRIVIA))
        user_stats    = stats[uid]
        total_att = total_cor = 0
        lines = []
        for cat, rec in user_stats.items():
            att = rec["attempts"]; cor = rec["correct"]
            total_att += att; total_cor += cor
            acc = (cor / att * 100) if att else 0
            bar = "█" * int(acc / 10) + "░" * (10 - int(acc / 10))
            lines.append(f"**{cat}**  `{bar}` {cor}/{att} ({acc:.0f}%)")
        total_acc = (total_cor / total_att * 100) if total_att else 0
        e = embed(
            f"{E.QUESTION}  {member.display_name}'s Trivia Stats",
            "\n".join(lines),
            C.TRIVIA,
            footer=f"Overall: {total_cor}/{total_att} ({total_acc:.0f}% accuracy)",
        )
        e.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="trivialeaderboard", description="Trivia leaderboard.")
    async def trivialeaderboard(self, ctx):
        if not ctx.guild:
            return await ctx.send(embed=error("Trivia", "Server only command."))
        stats = load_trivia_stats()
        board = []
        for member in ctx.guild.members:
            if member.bot or str(member.id) not in stats:
                continue
            us  = stats[str(member.id)]
            cor = sum(x["correct"] for x in us.values())
            att = sum(x["attempts"] for x in us.values())
            board.append((member, cor, att))
        board.sort(key=lambda x: x[1], reverse=True)
        medals = ["🥇", "🥈", "🥉"]
        lines  = []
        for i, (m, cor, att) in enumerate(board[:10]):
            acc   = (cor / att * 100) if att else 0
            medal = medals[i] if i < 3 else f"{i+1}."
            lines.append(f"{medal}  **{m.display_name}** — `{cor}` correct ({acc:.0f}%)")
        e = embed(f"{E.TROPHY}  Trivia Leaderboard", "\n".join(lines) or "No players yet.", C.TRIVIA)
        await ctx.send(embed=e)


async def setup(bot):
    await bot.add_cog(Trivia(bot))
