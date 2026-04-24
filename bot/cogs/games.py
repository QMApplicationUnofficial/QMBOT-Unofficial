import asyncio
import random
import discord
from discord.ext import commands

from storage import load_coins, save_coins
from ui_utils import C, E, embed, error, warn, success

BLACKJACK_GAMES: dict[str, dict] = {}


def ensure_user(coins: dict, user_id) -> dict:
    uid = str(user_id)
    if uid not in coins:
        coins[uid] = {"wallet": 100, "bank": 0}
    return coins[uid]


# ─── Card Logic ───────────────────────────────────────────────────────────────

def draw_card() -> str:
    ranks = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
    suits = ["♠","♥","♦","♣"]
    return f"{random.choice(ranks)}{random.choice(suits)}"

def card_value(card: str) -> int:
    r = card[:-1]
    if r in {"J","Q","K"}: return 10
    if r == "A":           return 11
    return int(r)

def hand_value(hand: list[str]) -> int:
    total = sum(card_value(c) for c in hand)
    aces  = sum(1 for c in hand if c[:-1] == "A")
    while total > 21 and aces:
        total -= 10
        aces  -= 1
    return total

def render_card(card: str) -> list[str]:
    rank, suit = card[:-1], card[-1]
    mid = rank.center(3)
    return ["┌─────┐", f"│{suit:<5}│", f"│ {mid} │", f"│{suit:>5}│", "└─────┘"]

def render_hidden() -> list[str]:
    return ["┌─────┐", "│     │", "│  ♔  │", "│     │", "└─────┘"]

def combine_cards(cards: list[str], hide_second: bool = False, per_row: int = 3) -> str:
    rows = []
    for i in range(0, len(cards), per_row):
        chunk = cards[i:i + per_row]
        rendered = []
        for j, card in enumerate(chunk):
            if hide_second and i == 0 and j == 1:
                rendered.append(render_hidden())
            else:
                rendered.append(render_card(card))
        lines = ["  ".join(r[row] for r in rendered) for row in range(5)]
        rows.append("\n".join(lines))
    return "\n\n".join(rows)


# ─── Slots ────────────────────────────────────────────────────────────────────

SLOT_SYMBOLS = ["🍒", "🍋", "🍊", "🍇", "🍓", "💎", "7️⃣", "🎰"]
SLOT_WEIGHTS = [30,   25,   20,   15,   10,    5,    3,    2  ]

# Payout multipliers per result type
SLOT_PAYOUTS = {
    "7️⃣": 20,   # triple 7s
    "💎": 15,   # triple diamonds
    "🎰": 12,   # triple slots
    "🍓": 8,
    "🍇": 6,
    "🍊": 5,
    "🍋": 4,
    "🍒": 3,
    "two": 1.5,  # any pair
}

def _spin_row() -> list[str]:
    return random.choices(SLOT_SYMBOLS, weights=SLOT_WEIGHTS, k=3)

def _evaluate(row: list[str]) -> tuple[str, float]:
    """Returns (outcome_text, multiplier). multiplier 0 = loss."""
    if row[0] == row[1] == row[2]:
        sym = row[0]
        mult = SLOT_PAYOUTS.get(sym, 3)
        return f"**JACKPOT** — Three {sym}!", mult
    if row[0] == row[1] or row[1] == row[2] or row[0] == row[2]:
        return "**Pair!** Close, but not quite.", SLOT_PAYOUTS["two"]
    return "No match. Unlucky.", 0.0

def _render_slots(rows: list[list[str]], spin_row_idx: int = -1) -> str:
    """Render a 3x3 slot grid. spin_row_idx = which row is the 'active' win line (-1 = all locked)."""
    lines = ["```"]
    for i, row in enumerate(rows):
        prefix = "▶ " if i == 1 else "  "   # middle row is the win line
        lines.append(f"{prefix}│ {' │ '.join(row)} │")
    lines.append("   ▲ win line ▲")
    lines.append("```")
    return "\n".join(lines)


class SlotsView(discord.ui.View):
    def __init__(self, author_id: int, bet: int):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.bet       = bet
        self.message   = None

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                embed=error("Slots", "Not your machine."), ephemeral=True)
            return False
        return True

    async def spin_and_animate(self, interaction: discord.Interaction):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        # Build 3 rows, middle row is the win line
        top    = _spin_row()
        middle = _spin_row()
        bottom = _spin_row()
        grid   = [top, middle, bottom]

        # Animate 5 frames
        for _ in range(5):
            anim_top    = _spin_row()
            anim_mid    = _spin_row()
            anim_bot    = _spin_row()
            anim_grid   = [anim_top, anim_mid, anim_bot]
            e = embed("🎰  Spinning…", _render_slots(anim_grid), C.TRIVIA)
            await asyncio.sleep(0.5)
            try:
                await interaction.message.edit(embed=e)
            except Exception:
                pass

        # Final result
        outcome_text, multiplier = _evaluate(middle)
        coins = load_coins()
        user  = ensure_user(coins, self.author_id)

        if multiplier > 0:
            winnings = int(self.bet * multiplier)
            user["wallet"] = int(user.get("wallet", 0)) + winnings
            color  = C.WIN
            result = f"{outcome_text}\n\n{E.COIN} **+{winnings:,}** coins  (x{multiplier})"
        else:
            color  = C.LOSE
            result = f"{outcome_text}\n\n{E.COIN} Lost **{self.bet:,}** coins."

        save_coins(coins)

        # Re-enable spin again button
        for child in self.children:
            child.disabled = False

        e = embed("🎰  Slot Machine",
                  f"{_render_slots(grid)}\n{result}",
                  color,
                  footer=f"Bet: {self.bet:,} coins · Win line = middle row")
        e.add_field(name=f"{E.WALLET} Wallet", value=f"`{user['wallet']:,}`", inline=False)
        try:
            await interaction.message.edit(embed=e, view=self)
        except Exception:
            pass

    @discord.ui.button(label="Spin Again  🎰", style=discord.ButtonStyle.primary)
    async def spin_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        coins = load_coins()
        user  = ensure_user(coins, self.author_id)
        if user.get("wallet", 0) < self.bet:
            return await interaction.response.send_message(
                embed=error("Slots", f"Not enough coins for another **{self.bet:,}** spin."),
                ephemeral=True)
        user["wallet"] = int(user.get("wallet", 0)) - self.bet
        save_coins(coins)
        await self.spin_and_animate(interaction)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.secondary)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


# ─── Gamble View ──────────────────────────────────────────────────────────────

class GambleView(discord.ui.View):
    def __init__(self, *, author_id, bet):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.bet       = bet
        self.message   = None

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                embed=error("Gamble", "Not your bet."), ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        coins = load_coins()
        user  = ensure_user(coins, self.author_id)
        user["wallet"] = int(user.get("wallet", 0)) + self.bet
        save_coins(coins)
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(
                embed=warn("Timed Out", f"Your **{self.bet:,}** coins were refunded."),
                view=self)

    async def _finish(self, interaction, choice):
        result = random.choice(["red", "black"])
        for child in self.children:
            child.disabled = True
        coins = load_coins()
        user  = ensure_user(coins, self.author_id)
        if choice == result:
            user["wallet"] = int(user.get("wallet", 0)) + self.bet * 2
            e = embed(f"{E.WIN}  Winner!", f"🎰 **{result.capitalize()}** — correct!\n\n{E.COIN} Won **{self.bet*2:,}** coins!", C.WIN)
        else:
            e = embed(f"{E.LOSE}  Wrong!", f"🎰 It was **{result.capitalize()}**.\n\n{E.COIN} Lost **{self.bet:,}** coins.", C.LOSE)
        e.add_field(name=f"{E.WALLET} Wallet", value=f"`{user['wallet']:,}`", inline=False)
        save_coins(coins)

        # Add "bet again" button
        view = GambleAgainView(author_id=self.author_id, bet=self.bet)
        await interaction.response.edit_message(embed=e, view=view)
        self.stop()

    @discord.ui.button(label="Red",   style=discord.ButtonStyle.danger)
    async def red(self, interaction, button):
        await self._finish(interaction, "red")

    @discord.ui.button(label="Black", style=discord.ButtonStyle.secondary)
    async def black(self, interaction, button):
        await self._finish(interaction, "black")


class GambleAgainView(discord.ui.View):
    def __init__(self, *, author_id: int, bet: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.bet       = bet

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                embed=error("Gamble", "Not your game."), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Bet Again", style=discord.ButtonStyle.primary)
    async def bet_again(self, interaction, button):
        coins = load_coins()
        user  = ensure_user(coins, self.author_id)
        if user.get("wallet", 0) < self.bet:
            return await interaction.response.send_message(
                embed=error("Gamble", f"Not enough coins to bet **{self.bet:,}** again."),
                ephemeral=True)
        user["wallet"] = int(user.get("wallet", 0)) - self.bet
        save_coins(coins)
        for child in self.children:
            child.disabled = True
        view = GambleView(author_id=self.author_id, bet=self.bet)
        e = embed("🎰  Place Your Bet",
                  f"Bet: **{self.bet:,}** {E.COIN}\n\nPick **Red** or **Black**.", C.GAMES)
        e.add_field(name=f"{E.WALLET} Wallet (held)", value=f"`{user['wallet']:,}`", inline=False)
        await interaction.response.edit_message(embed=e, view=view)
        view.message = interaction.message
        self.stop()

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.secondary)
    async def stop_btn(self, interaction, button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


# ─── Blackjack View ───────────────────────────────────────────────────────────

class BlackjackView(discord.ui.View):
    def __init__(self, *, author_id):
        super().__init__(timeout=60)
        self.author_id = str(author_id)

    async def interaction_check(self, interaction):
        if str(interaction.user.id) != self.author_id:
            await interaction.response.send_message(
                embed=error("Blackjack", "Not your game."), ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        BLACKJACK_GAMES.pop(self.author_id, None)

    def build_embed(self, game, reveal_dealer=False, result_text=None):
        p_val    = hand_value(game["player"])
        d_val    = hand_value(game["dealer"])
        p_cards  = combine_cards(game["player"])
        d_cards  = combine_cards(game["dealer"], hide_second=not reveal_dealer)
        d_label  = f"Dealer  ({d_val})" if reveal_dealer else f"Dealer  ({card_value(game['dealer'][0])} + ?)"
        desc = (
            f"**Your Hand  ({p_val})**\n```\n{p_cards}\n```\n"
            f"**{d_label}**\n```\n{d_cards}\n```"
        )
        if result_text:
            desc += f"\n{result_text}"
        e = embed(f"{E.CARDS}  Blackjack", desc, C.GAMES)
        e.add_field(name="Bet", value=f"`{game['bet']:,}` {E.COIN}", inline=True)
        return e

    async def _end(self, interaction, e, show_again_btn=False):
        for child in self.children:
            child.disabled = True
        bet = BLACKJACK_GAMES.get(self.author_id, {}).get("bet", 0)
        BLACKJACK_GAMES.pop(self.author_id, None)
        if show_again_btn and bet:
            view = BlackjackAgainView(author_id=int(self.author_id), bet=bet)
            await interaction.response.edit_message(embed=e, view=view)
        else:
            await interaction.response.edit_message(embed=e, view=self)
        self.stop()

    @discord.ui.button(label="Hit",   style=discord.ButtonStyle.primary)
    async def hit(self, interaction, button):
        game = BLACKJACK_GAMES.get(self.author_id)
        if not game:
            return
        game["player"].append(draw_card())
        total = hand_value(game["player"])
        if total > 21:
            coins = load_coins()
            user  = ensure_user(coins, self.author_id)
            e     = self.build_embed(game, result_text=f"\n{E.LOSE} **Bust!**  Lost **{game['bet']:,}** coins.")
            e.color = C.LOSE
            e.add_field(name=f"{E.WALLET} Wallet", value=f"`{user['wallet']:,}`", inline=False)
            return await self._end(interaction, e, show_again_btn=True)
        await interaction.response.edit_message(embed=self.build_embed(game), view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction, button):
        game  = BLACKJACK_GAMES.get(self.author_id)
        if not game:
            return
        p_val = hand_value(game["player"])
        while hand_value(game["dealer"]) < 17:
            game["dealer"].append(draw_card())
        d_val = hand_value(game["dealer"])
        coins = load_coins()
        user  = ensure_user(coins, self.author_id)
        bet   = int(game["bet"])
        if d_val > 21 or p_val > d_val:
            user["wallet"] = int(user.get("wallet", 0)) + bet * 2
            result = f"\n{E.WIN} **You win!**  +{bet*2:,} coins."
            color  = C.WIN
        elif d_val == p_val:
            user["wallet"] = int(user.get("wallet", 0)) + bet
            result = f"\n🤝 **Push!**  {bet:,} coins returned."
            color  = C.NEUTRAL
        else:
            result = f"\n{E.LOSE} **Dealer wins.**  -{bet:,} coins."
            color  = C.LOSE
        save_coins(coins)
        e = self.build_embed(game, reveal_dealer=True, result_text=result)
        e.color = color
        e.add_field(name=f"{E.WALLET} Wallet", value=f"`{user['wallet']:,}`", inline=False)
        await self._end(interaction, e, show_again_btn=True)


class BlackjackAgainView(discord.ui.View):
    def __init__(self, *, author_id: int, bet: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.bet       = bet

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                embed=error("Blackjack", "Not your game."), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Deal Again  🃏", style=discord.ButtonStyle.primary)
    async def deal_again(self, interaction, button):
        uid   = str(self.author_id)
        coins = load_coins()
        user  = ensure_user(coins, uid)
        if user.get("wallet", 0) < self.bet:
            return await interaction.response.send_message(
                embed=error("Blackjack", f"Not enough coins to bet **{self.bet:,}** again."),
                ephemeral=True)
        if uid in BLACKJACK_GAMES:
            return await interaction.response.send_message(
                embed=warn("Blackjack", "You already have a game running."), ephemeral=True)
        user["wallet"] = int(user.get("wallet", 0)) - self.bet
        player = [draw_card(), draw_card()]
        dealer = [draw_card(), draw_card()]
        save_coins(coins)
        BLACKJACK_GAMES[uid] = {"player": player, "dealer": dealer, "bet": self.bet}
        for child in self.children:
            child.disabled = True
        view = BlackjackView(author_id=self.author_id)
        if hand_value(player) == 21:
            while hand_value(dealer) < 17:
                dealer.append(draw_card())
            game = BLACKJACK_GAMES.pop(uid)
            coins = load_coins()
            user  = ensure_user(coins, uid)
            if hand_value(dealer) == 21:
                user["wallet"] = int(user.get("wallet", 0)) + self.bet
                result = f"\n🤝 Push. Both blackjack."
                color  = C.NEUTRAL
            else:
                user["wallet"] = int(user.get("wallet", 0)) + self.bet * 2
                result = f"\n{E.WIN} **Natural Blackjack!**  +{self.bet*2:,} coins!"
                color  = C.WIN
            save_coins(coins)
            e = view.build_embed(game, reveal_dealer=True, result_text=result)
            e.color = color
            e.add_field(name=f"{E.WALLET} Wallet", value=f"`{user['wallet']:,}`", inline=False)
            await interaction.response.edit_message(embed=e, view=BlackjackAgainView(author_id=self.author_id, bet=self.bet))
            return
        await interaction.response.edit_message(
            embed=view.build_embed(BLACKJACK_GAMES[uid]), view=view)
        self.stop()

    @discord.ui.button(label="Cash Out", style=discord.ButtonStyle.secondary)
    async def cash_out(self, interaction, button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


# ─── Cog ──────────────────────────────────────────────────────────────────────

class Games(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="coinflip", description="Flip a coin. Bet optionally: /coinflip heads 200")
    async def coinflip(self, ctx, side: str = None, amount: str = None):
        result = random.choice(["Heads", "Tails"])
        if side is None:
            return await ctx.send(embed=embed(f"🪙  Coin Flip", f"It landed on **{result}**!", C.GAMES))
        side = side.strip().lower()
        if side not in ("heads", "tails"):
            return await ctx.send(embed=error("Coin Flip", "Choose **heads** or **tails**."))
        if amount is None:
            return await ctx.send(embed=error("Coin Flip", "Provide a bet: `/coinflip heads 100`"))
        coins  = load_coins()
        user   = ensure_user(coins, ctx.author.id)
        wallet = user["wallet"]
        bet    = wallet if amount.lower() == "all" else (int(amount) if amount.isdigit() else None)
        if bet is None:
            return await ctx.send(embed=error("Coin Flip", "Enter a number or `all`."))
        if bet <= 0:
            return await ctx.send(embed=error("Coin Flip", "Bet must be positive."))
        if wallet < bet:
            return await ctx.send(embed=error("Coin Flip", f"You only have `{wallet:,}` coins."))
        won = side.capitalize() == result
        if won:
            user["wallet"] += bet
            e = embed(f"🪙  {result} — Correct!", f"You won **{bet:,}** coins! {E.WIN}", C.WIN)
        else:
            user["wallet"] -= bet
            e = embed(f"🪙  {result} — Wrong!", f"You guessed **{side}**. Lost **{bet:,}** coins.", C.LOSE)
        save_coins(coins)
        e.add_field(name=f"{E.WALLET} Wallet", value=f"`{user['wallet']:,}`", inline=False)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="gamble", description="Bet on red or black.")
    async def gamble(self, ctx, amount: str):
        coins  = load_coins()
        user   = ensure_user(coins, ctx.author.id)
        wallet = user["wallet"]
        bet    = wallet if amount.lower() == "all" else (int(amount) if amount.isdigit() else None)
        if bet is None:
            return await ctx.send(embed=error("Gamble", "Enter a number or `all`."))
        if bet <= 0:
            return await ctx.send(embed=error("Gamble", "Bet must be positive."))
        if wallet < bet:
            return await ctx.send(embed=error("Gamble", f"You only have `{wallet:,}` coins."))
        user["wallet"] -= bet
        save_coins(coins)
        e = embed("🎰  Place Your Bet",
                  f"Bet: **{bet:,}** {E.COIN}\n\nPick **Red** or **Black** — winner doubles!", C.GAMES)
        e.add_field(name=f"{E.WALLET} Wallet (held)", value=f"`{user['wallet']:,}`", inline=False)
        view = GambleView(author_id=ctx.author.id, bet=bet)
        msg  = await ctx.send(embed=e, view=view)
        view.message = msg

    @commands.hybrid_command(name="slots", description="Spin the slot machine — bet an amount to play.")
    async def slots(self, ctx, amount: str):
        coins  = load_coins()
        user   = ensure_user(coins, ctx.author.id)
        wallet = int(user.get("wallet", 0))
        bet    = wallet if amount.lower() == "all" else (int(amount) if amount.isdigit() else None)
        if bet is None:
            return await ctx.send(embed=error("Slots", "Enter a number or `all`."))
        if bet <= 0:
            return await ctx.send(embed=error("Slots", "Bet must be positive."))
        if wallet < bet:
            return await ctx.send(embed=error("Slots", f"You only have `{wallet:,}` coins."))
        user["wallet"] = wallet - bet
        save_coins(coins)

        view = SlotsView(author_id=ctx.author.id, bet=bet)

        # Initial "loading" embed
        placeholder_grid = [_spin_row() for _ in range(3)]
        e = embed("🎰  Spinning…", _render_slots(placeholder_grid), C.TRIVIA,
                  footer=f"Bet: {bet:,} coins · Middle row is the win line")
        msg = await ctx.send(embed=e, view=view)
        view.message = msg

        # Animate and resolve
        top    = _spin_row()
        middle = _spin_row()
        bottom = _spin_row()
        grid   = [top, middle, bottom]

        for _ in range(5):
            anim = [_spin_row() for _ in range(3)]
            ae   = embed("🎰  Spinning…", _render_slots(anim), C.TRIVIA)
            await asyncio.sleep(0.45)
            try:
                await msg.edit(embed=ae)
            except Exception:
                pass

        outcome_text, multiplier = _evaluate(middle)
        coins = load_coins()
        user  = ensure_user(coins, ctx.author.id)

        if multiplier > 0:
            winnings = int(bet * multiplier)
            user["wallet"] = int(user.get("wallet", 0)) + winnings
            color  = C.WIN
            result = f"{outcome_text}\n\n{E.COIN} **+{winnings:,}** coins  (×{multiplier})"
        else:
            color  = C.LOSE
            result = f"{outcome_text}\n\n{E.COIN} Lost **{bet:,}** coins."

        save_coins(coins)

        final_e = embed("🎰  Slot Machine",
                        f"{_render_slots(grid)}\n{result}",
                        color,
                        footer=f"Bet: {bet:,} coins · Win line = middle row")
        final_e.add_field(name=f"{E.WALLET} Wallet", value=f"`{user['wallet']:,}`", inline=False)
        try:
            await msg.edit(embed=final_e, view=view)
        except Exception:
            pass

    @commands.hybrid_command(name="blackjack", description="Play a hand of blackjack.")
    async def blackjack(self, ctx, bet: str):
        uid    = str(ctx.author.id)
        coins  = load_coins()
        user   = ensure_user(coins, uid)
        wallet = user["wallet"]
        amount = wallet if bet.lower() == "all" else (int(bet) if bet.isdigit() else None)
        if amount is None:
            return await ctx.send(embed=error("Blackjack", "Enter a number or `all`."))
        if amount <= 0:
            return await ctx.send(embed=error("Blackjack", "Bet must be positive."))
        if wallet < amount:
            return await ctx.send(embed=error("Blackjack", f"You only have `{wallet:,}` coins."))
        if uid in BLACKJACK_GAMES:
            return await ctx.send(embed=warn("Blackjack", "Finish your current game first."))
        player = [draw_card(), draw_card()]
        dealer = [draw_card(), draw_card()]
        user["wallet"] -= amount
        save_coins(coins)
        BLACKJACK_GAMES[uid] = {"player": player, "dealer": dealer, "bet": amount}
        if hand_value(player) == 21:
            while hand_value(dealer) < 17:
                dealer.append(draw_card())
            game = BLACKJACK_GAMES.pop(uid)
            view = BlackjackView(author_id=ctx.author.id)
            coins = load_coins()
            user  = ensure_user(coins, uid)
            if hand_value(dealer) == 21:
                user["wallet"] += amount
                result = f"\n🤝 Push. Both hit blackjack."
                color  = C.NEUTRAL
            else:
                user["wallet"] += amount * 2
                result = f"\n{E.WIN} **Natural Blackjack!**  +{amount*2:,} coins!"
                color  = C.WIN
            save_coins(coins)
            e = view.build_embed(game, reveal_dealer=True, result_text=result)
            e.color = color
            e.add_field(name=f"{E.WALLET} Wallet", value=f"`{user['wallet']:,}`", inline=False)
            return await ctx.send(embed=e,
                                  view=BlackjackAgainView(author_id=ctx.author.id, bet=amount))
        view = BlackjackView(author_id=ctx.author.id)
        await ctx.send(embed=view.build_embed(BLACKJACK_GAMES[uid]), view=view)


async def setup(bot):
    await bot.add_cog(Games(bot))
