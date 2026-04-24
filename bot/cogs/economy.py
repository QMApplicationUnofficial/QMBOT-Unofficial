import discord
from discord.ext import commands
import random
import time
from datetime import datetime, timedelta, timezone

from storage import load_coins, save_coins
from config import (
    ALWAYS_BANKROB_USER_ID,
    BANKROB_STEAL_MIN_PCT,
    BANKROB_STEAL_MAX_PCT,
    BANKROB_MIN_STEAL,
    BANKROB_MAX_STEAL_PCT_CAP,
)
from ui_utils import C, E, embed, success, error, warn, cooldown_str

# ─── Tax Brackets (wider gaps) ────────────────────────────────────────────────
TAX_BRACKETS = [
    (1_000,         0.05),   # 0–1k: 5%
    (5_000,         0.10),   # 1k–5k: 10%
    (15_000,        0.18),   # 5k–15k: 18%
    (40_000,        0.26),   # 15k–40k: 26%
    (100_000,       0.35),   # 40k–100k: 35%
    (float("inf"),  0.45),   # 100k+: 45%
]

# ─── Career System ────────────────────────────────────────────────────────────
# Fields with titles, base pay range, and bonuses per promotion level
CAREER_FIELDS = {
    "tech": {
        "name": "Tech",
        "icon": "💻",
        "tiers": [
            {"title": "Junior Dev",        "min": 80,   "max": 200},
            {"title": "Mid Dev",           "min": 200,  "max": 400},
            {"title": "Senior Dev",        "min": 400,  "max": 700},
            {"title": "Staff Engineer",    "min": 700,  "max": 1100},
            {"title": "Principal Engineer","min": 1100, "max": 1800},
        ],
    },
    "finance": {
        "name": "Finance",
        "icon": "📊",
        "tiers": [
            {"title": "Analyst",           "min": 90,   "max": 220},
            {"title": "Associate",         "min": 220,  "max": 450},
            {"title": "VP",                "min": 450,  "max": 750},
            {"title": "Director",          "min": 750,  "max": 1200},
            {"title": "CFO",               "min": 1200, "max": 2000},
        ],
    },
    "medicine": {
        "name": "Medicine",
        "icon": "🏥",
        "tiers": [
            {"title": "Intern",            "min": 60,   "max": 160},
            {"title": "Resident",          "min": 160,  "max": 350},
            {"title": "Junior Doctor",     "min": 350,  "max": 600},
            {"title": "Consultant",        "min": 600,  "max": 1000},
            {"title": "Lead Consultant",   "min": 1000, "max": 1600},
        ],
    },
    "law": {
        "name": "Law",
        "icon": "⚖️",
        "tiers": [
            {"title": "Paralegal",         "min": 70,   "max": 180},
            {"title": "Solicitor",         "min": 180,  "max": 380},
            {"title": "Senior Solicitor",  "min": 380,  "max": 650},
            {"title": "Partner",           "min": 650,  "max": 1100},
            {"title": "Senior Partner",    "min": 1100, "max": 1900},
        ],
    },
    "entertainment": {
        "name": "Entertainment",
        "icon": "🎬",
        "tiers": [
            {"title": "Intern",            "min": 30,   "max": 120},
            {"title": "Production Assist", "min": 120,  "max": 300},
            {"title": "Content Creator",   "min": 300,  "max": 600},
            {"title": "Producer",          "min": 600,  "max": 1000},
            {"title": "Executive Producer","min": 1000, "max": 1700},
        ],
    },
    "crime": {
        "name": "Crime",
        "icon": "🦹",
        "tiers": [
            {"title": "Street Rat",        "min": 50,   "max": 200},
            {"title": "Grifter",           "min": 200,  "max": 450},
            {"title": "Enforcer",          "min": 450,  "max": 800},
            {"title": "Crime Boss",        "min": 800,  "max": 1400},
            {"title": "Kingpin",           "min": 1400, "max": 2500},
        ],
    },
}

# XP thresholds per tier promotion (cumulative shifts worked)
PROMOTION_THRESHOLDS = [0, 10, 25, 50, 90]  # shifts needed to reach tier 0,1,2,3,4
WORK_COOLDOWN = 3600  # 1 hour
WEEKLY_BONUS_KEY = "weekly_bonus"

DEBT_INTEREST_RATE     = 0.03
DEBT_INTEREST_INTERVAL = 3600


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _week_key() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year}-W{now.isocalendar()[1]}"


def _reset_star_meta_if_needed(user: dict):
    user.setdefault("stars", 0)
    user.setdefault("star_meta", {"day": _today_key(), "given": {}})
    if not isinstance(user["star_meta"], dict):
        user["star_meta"] = {"day": _today_key(), "given": {}}
    user["star_meta"].setdefault("day", _today_key())
    user["star_meta"].setdefault("given", {})
    if user["star_meta"]["day"] != _today_key():
        user["star_meta"] = {"day": _today_key(), "given": {}}


def ensure_user(coins, user_id):
    uid = str(user_id)
    defaults = {
        "wallet": 100, "bank": 0, "debt": 0, "debt_since": 0,
        "stars": 0, "last_daily": 0, "last_beg": 0,
        "last_rob": 0, "last_bankrob": 0, "last_work": 0,
        "active_effects": {},
        "star_meta": {"day": _today_key(), "given": {}},
        # Career fields
        "career_field": None,
        "career_tier": 0,
        "career_shifts": 0,
        "career_week_key": "",
        "career_week_shifts": 0,
    }
    if uid not in coins:
        coins[uid] = dict(defaults)
    else:
        for k, v in defaults.items():
            coins[uid].setdefault(k, v)
        _reset_star_meta_if_needed(coins[uid])
    return coins[uid]


def has_effect(user: dict, effect: str) -> bool:
    effects = user.get("active_effects", {})
    return effect in effects and effects[effect] > time.time()


def calculate_tax(amount: int) -> tuple[int, float]:
    for threshold, rate in TAX_BRACKETS:
        if amount <= threshold:
            return int(amount * rate), rate
    return int(amount * 0.45), 0.45


def accrue_debt_interest(user: dict) -> int:
    debt = int(user.get("debt", 0))
    if debt <= 0:
        return 0
    debt_since = float(user.get("debt_since", 0))
    full_hours = int((time.time() - debt_since) / DEBT_INTEREST_INTERVAL)
    if full_hours < 1:
        return debt
    new_debt = int(debt * ((1 + DEBT_INTEREST_RATE) ** full_hours))
    user["debt"] = new_debt
    user["debt_since"] = debt_since + full_hours * DEBT_INTEREST_INTERVAL
    return new_debt


def _career_tier(user: dict) -> int:
    shifts = int(user.get("career_shifts", 0))
    tier   = 0
    for i, threshold in enumerate(PROMOTION_THRESHOLDS):
        if shifts >= threshold:
            tier = i
    return min(tier, len(PROMOTION_THRESHOLDS) - 1)


def _update_weekly_shifts(user: dict):
    wk = _week_key()
    if user.get("career_week_key") != wk:
        user["career_week_key"]    = wk
        user["career_week_shifts"] = 0


# ─── Career Pick View ─────────────────────────────────────────────────────────

class CareerPickView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        for key, data in CAREER_FIELDS.items():
            btn = discord.ui.Button(
                label=f"{data['icon']}  {data['name']}",
                style=discord.ButtonStyle.secondary,
                custom_id=key,
            )
            btn.callback = self._make_cb(key)
            self.add_item(btn)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                embed=error("Career", "This isn't your career choice."), ephemeral=True)
            return False
        return True

    def _make_cb(self, field_key: str):
        async def callback(interaction: discord.Interaction):
            coins = load_coins()
            user  = ensure_user(coins, interaction.user.id)
            if user.get("career_field"):
                await interaction.response.send_message(
                    embed=warn("Career", f"You already work in **{CAREER_FIELDS[user['career_field']]['name']}**. You can't switch fields."),
                    ephemeral=True)
                return
            user["career_field"]  = field_key
            user["career_tier"]   = 0
            user["career_shifts"] = 0
            save_coins(coins)
            field = CAREER_FIELDS[field_key]
            for c in self.children:
                c.disabled = True
            e = success(
                f"Career Started!",
                f"You're now a **{field['icon']} {field['tiers'][0]['title']}** in **{field['name']}**!\n\n"
                f"Use `/work` every hour to earn coins and rack up shifts.\n"
                f"**10 shifts** earns your first promotion.",
            )
            await interaction.response.edit_message(embed=e, view=self)
            self.stop()
        return callback


# ─── Cog ──────────────────────────────────────────────────────────────────────

class Economy(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    # ── BALANCE ───────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="balance", description="Check your coin balance.")
    async def balance(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        coins  = load_coins()
        user   = ensure_user(coins, member.id)
        debt   = accrue_debt_interest(user)
        save_coins(coins)
        total  = user['wallet'] + user['bank']
        rows = [
            ("Wallet", f"{user['wallet']:,}"),
            ("QMBank", f"{user['bank']:,}"),
            ("Stars",  f"{user['stars']:,}"),
            ("Total",  f"{total:,}"),
        ]
        if debt > 0:
            rows.append(("Debt", f"{debt:,}  (3%/hr)"))
        col_w = max(len(r[0]) for r in rows)
        table = "\n".join(f"{r[0].ljust(col_w)}  {r[1]}" for r in rows)
        e = embed(
            f"{E.CROWN}  {member.display_name}",
            f"```\n{table}\n```",
            C.ECONOMY,
            footer=f"{'Your' if member == ctx.author else member.display_name + chr(39) + 's'} account",
        )
        e.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=e)

    # ── DEPOSIT ───────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="deposit", description="Deposit coins into your bank.")
    async def deposit(self, ctx, amount: str):
        coins = load_coins()
        user  = ensure_user(coins, ctx.author.id)
        amt   = user["wallet"] if amount.lower() == "all" else (int(amount) if amount.isdigit() else None)
        if amt is None:
            return await ctx.send(embed=error("Deposit", "Enter a number or `all`."))
        if amt <= 0 or amt > user["wallet"]:
            return await ctx.send(embed=error("Deposit", f"You only have `{user['wallet']:,}` in your wallet."))
        user["wallet"] -= amt
        user["bank"]   += amt
        save_coins(coins)
        e = success("Deposited!", f"Moved **{amt:,}** coins into {E.BANK} QMBank.")
        e.add_field(name=f"{E.WALLET} Wallet", value=f"`{user['wallet']:,}`", inline=True)
        e.add_field(name=f"{E.BANK} QMBank",   value=f"`{user['bank']:,}`",   inline=True)
        await ctx.send(embed=e)

    # ── WITHDRAW ──────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="withdraw", description="Withdraw coins from your bank.")
    async def withdraw(self, ctx, amount: str):
        coins = load_coins()
        user  = ensure_user(coins, ctx.author.id)
        amt   = user["bank"] if amount.lower() == "all" else (int(amount) if amount.isdigit() else None)
        if amt is None:
            return await ctx.send(embed=error("Withdraw", "Enter a number or `all`."))
        if amt <= 0 or amt > user["bank"]:
            return await ctx.send(embed=error("Withdraw", f"You only have `{user['bank']:,}` in the bank."))
        user["bank"]   -= amt
        user["wallet"] += amt
        save_coins(coins)
        e = success("Withdrawn!", f"Moved **{amt:,}** coins to your {E.WALLET} wallet.")
        e.add_field(name=f"{E.WALLET} Wallet", value=f"`{user['wallet']:,}`", inline=True)
        e.add_field(name=f"{E.BANK} QMBank",   value=f"`{user['bank']:,}`",   inline=True)
        await ctx.send(embed=e)

    # ── DAILY ─────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="daily", description="Claim your daily coins.")
    async def daily(self, ctx):
        coins = load_coins()
        user  = ensure_user(coins, ctx.author.id)
        now   = datetime.now(timezone.utc)
        last  = datetime.fromtimestamp(user["last_daily"], timezone.utc)
        if last.date() == now.date():
            tomorrow  = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            remaining = cooldown_str(int((tomorrow - now).total_seconds()))
            return await ctx.send(embed=warn("Daily Already Claimed", f"{E.CLOCK} Come back in **{remaining}**."))
        reward = random.randint(100, 500)
        user["wallet"] += reward
        user["last_daily"] = now.timestamp()
        save_coins(coins)
        e = success("Daily Reward!", f"{E.COIN} You received **{reward:,}** coins!")
        e.add_field(name=f"{E.WALLET} Wallet", value=f"`{user['wallet']:,}`", inline=False)
        e.set_footer(text="Come back tomorrow!")
        await ctx.send(embed=e)

    # ── BEG ───────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="beg", description="Beg for some coins.")
    async def beg(self, ctx):
        coins = load_coins()
        user  = ensure_user(coins, ctx.author.id)
        now   = time.time()
        if now - user["last_beg"] < 120:
            remaining = cooldown_str(int(120 - (now - user["last_beg"])))
            return await ctx.send(embed=warn("Slow Down", f"Try again in **{remaining}**."))
        responses = [
            "A kind stranger tossed you some change.",
            "Someone felt sorry for you.",
            "A passing NPC dropped their wallet.",
            "The universe took pity on you.",
            "A pigeon dropped coins. Somehow.",
        ]
        amount = random.randint(5, 50)
        user["wallet"] += amount
        user["last_beg"] = now
        save_coins(coins)
        e = embed(f"{E.BEG}  Begging Result",
                  f"{random.choice(responses)}\n\n{E.COIN} You got **{amount}** coins.", C.ECONOMY)
        e.add_field(name=f"{E.WALLET} Wallet", value=f"`{user['wallet']:,}`", inline=False)
        await ctx.send(embed=e)

    # ── CHOOSE CAREER ─────────────────────────────────────────────────────────

    @commands.hybrid_command(name="career", description="Choose your career field.")
    async def career(self, ctx):
        coins = load_coins()
        user  = ensure_user(coins, ctx.author.id)
        field_key = user.get("career_field")
        if field_key:
            field = CAREER_FIELDS[field_key]
            tier  = _career_tier(user)
            tier_data = field["tiers"][tier]
            shifts    = user.get("career_shifts", 0)
            next_thresh = PROMOTION_THRESHOLDS[tier + 1] if tier < len(PROMOTION_THRESHOLDS) - 1 else None
            desc = (
                f"{field['icon']}  **{field['name']}**\n"
                f"Title: **{tier_data['title']}**\n"
                f"Tier: **{tier + 1} / {len(field['tiers'])}**\n"
                f"Total Shifts: **{shifts}**\n"
            )
            if next_thresh:
                desc += f"Next promotion at: **{next_thresh} shifts** ({next_thresh - shifts} to go)"
            else:
                desc += "**MAX RANK ACHIEVED** 🏆"
            return await ctx.send(embed=embed(f"Your Career", desc, C.ECONOMY))
        e = embed(
            "💼  Choose Your Career",
            "Pick a field below. **This is permanent** — you cannot switch.\n\n"
            "Your title and pay scale improve as you work more shifts.",
            C.ECONOMY,
        )
        view = CareerPickView(ctx.author.id)
        await ctx.send(embed=e, view=view)

    # ── WORK ──────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="work", description="Work a shift and earn coins (1hr cooldown).")
    async def work(self, ctx):
        coins = load_coins()
        user  = ensure_user(coins, ctx.author.id)
        now   = time.time()

        if now - user["last_work"] < WORK_COOLDOWN:
            remaining = cooldown_str(int(WORK_COOLDOWN - (now - user["last_work"])))
            return await ctx.send(embed=warn("Too Tired", f"{E.CLOCK} Come back in **{remaining}**."))

        # Require career selection
        field_key = user.get("career_field")
        if not field_key:
            return await ctx.send(embed=warn("No Career",
                "You don't have a job yet! Use `/career` to pick your field."))

        field  = CAREER_FIELDS[field_key]
        old_tier = _career_tier(user)

        # Increment shifts
        user["career_shifts"] = int(user.get("career_shifts", 0)) + 1
        _update_weekly_shifts(user)
        user["career_week_shifts"] = int(user.get("career_week_shifts", 0)) + 1

        new_tier = _career_tier(user)
        promoted = new_tier > old_tier

        tier_data = field["tiers"][new_tier]
        earned    = random.randint(tier_data["min"], tier_data["max"])

        # Time-of-day multiplier
        hour = datetime.now(timezone.utc).hour
        if 9 <= hour < 17:
            time_label = "regular hours"
            multiplier = 1.0
        elif 17 <= hour < 22:
            time_label = "evening shift"
            multiplier = 1.15
        else:
            time_label = "overnight shift"
            multiplier = 1.30
        earned = int(earned * multiplier)

        tax, rate = calculate_tax(earned)
        net       = earned - tax

        user["wallet"]    += net
        user["last_work"]  = now
        save_coins(coins)

        desc = (
            f"_{field['icon']} {tier_data['title']} · {field['name']}_\n\n"
            f"**Gross:** {earned:,} coins\n"
            f"**Tax ({int(rate*100)}%):** -{tax:,} coins\n"
            f"**Net Pay:** +{net:,} coins\n\n"
            f"*{time_label.capitalize()} ({int((multiplier-1)*100)}% bonus)*"
        )

        if promoted:
            new_title = field["tiers"][new_tier]["title"]
            desc += f"\n\n🎉 **PROMOTED to {new_title}!**"

        e = embed(f"{E.WORK}  Payday!", desc, C.WIN if promoted else C.ECONOMY)
        e.add_field(name=f"{E.WALLET} Wallet",  value=f"`{user['wallet']:,}`", inline=True)
        e.add_field(name="Total Shifts",        value=f"`{user['career_shifts']:,}`", inline=True)
        e.set_footer(text="Night shifts pay 30% more · Evening shifts pay 15% more")
        await ctx.send(embed=e)

    # ── WEEKLY BONUS (background task helper, also exposed as command for admins) ──

    @commands.hybrid_command(name="weeklypay", description="Distribute weekly top-worker bonuses (admin only).")
    @commands.has_permissions(administrator=True)
    async def weeklypay(self, ctx):
        """
        Finds the top worker per career field this week and pays them a bonus.
        Also finds the #1 overall worker and gives a larger bonus.
        """
        wk    = _week_key()
        coins = load_coins()
        # Group by field, find top worker per field
        field_top: dict[str, tuple[str, int]] = {}  # field_key -> (uid, shifts)
        overall_top: tuple[str, int] | None = None

        for uid, data in coins.items():
            if data.get("career_week_key") != wk:
                continue
            shifts    = int(data.get("career_week_shifts", 0))
            field_key = data.get("career_field")
            if not field_key or not shifts:
                continue
            if field_key not in field_top or shifts > field_top[field_key][1]:
                field_top[field_key] = (uid, shifts)
            if overall_top is None or shifts > overall_top[1]:
                overall_top = (uid, shifts)

        if not field_top:
            return await ctx.send(embed=warn("Weekly Pay", "No one worked this week."))

        lines = []
        for fk, (uid, shifts) in field_top.items():
            bonus = CAREER_FIELDS[fk]["tiers"][-1]["max"] * 2
            coins.setdefault(uid, {"wallet": 100, "bank": 0})
            coins[uid]["wallet"] = int(coins[uid].get("wallet", 0)) + bonus
            member = ctx.guild.get_member(int(uid)) if ctx.guild else None
            name   = member.display_name if member else f"<@{uid}>"
            lines.append(f"{CAREER_FIELDS[fk]['icon']} **{CAREER_FIELDS[fk]['name']}** top worker: {name} ({shifts} shifts) → +{bonus:,} coins")

        if overall_top:
            uid, shifts = overall_top
            grand_bonus = 5000
            coins[uid]["wallet"] = int(coins[uid].get("wallet", 0)) + grand_bonus
            member = ctx.guild.get_member(int(uid)) if ctx.guild else None
            name   = member.display_name if member else f"<@{uid}>"
            lines.append(f"\n👑 **Overall top worker:** {name} → +{grand_bonus:,} bonus coins!")

        save_coins(coins)
        e = success("Weekly Bonuses Paid! 💰", "\n".join(lines))
        await ctx.send(embed=e)

    # ── PAY ───────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="pay", description="Send coins to another user.")
    async def pay(self, ctx, member: discord.Member, amount: str):
        if member == ctx.author:
            return await ctx.send(embed=error("Pay", "You can't pay yourself."))
        if member.bot:
            return await ctx.send(embed=error("Pay", "Bots don't take tips."))
        coins    = load_coins()
        sender   = ensure_user(coins, ctx.author.id)
        receiver = ensure_user(coins, member.id)
        amt      = sender["wallet"] if amount.lower() == "all" else (int(amount) if amount.isdigit() else None)
        if amt is None:
            return await ctx.send(embed=error("Pay", "Enter a number or `all`."))
        if amt <= 0:
            return await ctx.send(embed=error("Pay", "Amount must be positive."))
        if sender["wallet"] < amt:
            return await ctx.send(embed=error("Pay", f"You only have `{sender['wallet']:,}` coins."))
        sender["wallet"]   -= amt
        receiver["wallet"] += amt
        save_coins(coins)
        e = success("Payment Sent!", f"{ctx.author.mention} sent **{amt:,}** {E.COIN} to {member.mention}.")
        e.add_field(name="Your Wallet",  value=f"`{sender['wallet']:,}`",   inline=True)
        e.add_field(name=f"{member.display_name}'s Wallet", value=f"`{receiver['wallet']:,}`", inline=True)
        await ctx.send(embed=e)

    # ── TAX ───────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="tax", description="Calculate the tax on an amount.")
    async def tax(self, ctx, amount: int):
        if amount <= 0:
            return await ctx.send(embed=error("Tax", "Amount must be positive."))
        tax_amt, rate = calculate_tax(amount)
        net = amount - tax_amt
        brackets = []
        prev  = 0
        found = False
        for threshold, r in TAX_BRACKETS:
            label = f"up to {int(threshold):,}" if threshold != float("inf") else f"{prev:,}+"
            mark  = " ◄ your bracket" if not found and amount <= threshold else ""
            if mark:
                found = True
            brackets.append(f"`{label}` → {int(r*100)}%{mark}")
            prev = int(threshold) if threshold != float("inf") else prev
        e = embed(
            f"{E.TAX}  Tax Calculator",
            f"**Amount:** {amount:,}\n**Rate:** {int(rate*100)}%\n"
            f"**Tax:** -{tax_amt:,}\n**Net:** {net:,}\n\n" + "\n".join(brackets),
            C.ECONOMY,
        )
        await ctx.send(embed=e)

    # ── DEBT ──────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="debt", description="Check your debt balance.")
    async def debt(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        coins  = load_coins()
        user   = ensure_user(coins, member.id)
        debt   = accrue_debt_interest(user)
        save_coins(coins)
        if debt <= 0:
            return await ctx.send(embed=success("Debt Free!", f"{member.display_name} owes nothing. 🎉"))
        e = embed(f"{E.DEBT}  {member.display_name}'s Debt",
                  f"Current debt: **{debt:,}** coins\n\nInterest: **3%/hr** compound.\nUse `/repaydebt` to pay.", C.DEBT)
        await ctx.send(embed=e)

    # ── REPAY DEBT ────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="repaydebt", description="Repay your debt (or part of it).")
    async def repaydebt(self, ctx, amount: str = "all"):
        coins = load_coins()
        user  = ensure_user(coins, ctx.author.id)
        debt  = accrue_debt_interest(user)
        if debt <= 0:
            return await ctx.send(embed=success("No Debt!", "Nothing to repay. 🎉"))
        pay = min(debt, user["wallet"]) if amount.lower() == "all" else (int(amount) if amount.isdigit() else None)
        if pay is None:
            return await ctx.send(embed=error("Repay", "Enter a number or `all`."))
        if pay <= 0:
            return await ctx.send(embed=error("Repay", "Amount must be positive."))
        if user["wallet"] < pay:
            pay = user["wallet"]
        if pay == 0:
            return await ctx.send(embed=error("Repay", "You have no coins to repay with."))
        user["wallet"] -= pay
        user["debt"]    = max(0, debt - pay)
        if user["debt"] == 0:
            user["debt_since"] = 0
        save_coins(coins)
        remaining = user["debt"]
        if remaining == 0:
            e = success("Debt Cleared! 🎉", f"Paid **{pay:,}** coins — debt free!")
        else:
            e = embed(f"{E.DEBT}  Partial Repayment",
                      f"Paid **{pay:,}** coins.\nRemaining: **{remaining:,}**.", C.WARN)
        e.add_field(name=f"{E.WALLET} Wallet", value=f"`{user['wallet']:,}`", inline=False)
        await ctx.send(embed=e)

    # ── STAR ──────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="star", description="Give someone a golden star.")
    async def star(self, ctx, member: discord.Member):
        if member == ctx.author:
            return await ctx.send(embed=error("Star", "Can't star yourself."))
        if member.bot:
            return await ctx.send(embed=error("Star", "Bots don't collect stars."))
        coins    = load_coins()
        giver    = ensure_user(coins, ctx.author.id)
        receiver = ensure_user(coins, member.id)
        _reset_star_meta_if_needed(giver)
        key         = str(member.id)
        given_today = int(giver["star_meta"]["given"].get(key, 0))
        if given_today >= 2:
            return await ctx.send(embed=warn("Limit Reached",
                f"You've already given 2 stars to {member.mention} today."))
        giver["star_meta"]["given"][key] = given_today + 1
        receiver["stars"] += 1
        save_coins(coins)
        e = embed(f"{E.STAR}  Star Given!",
                  f"{ctx.author.mention} gifted {member.mention} a golden star!", C.TRIVIA)
        e.add_field(name=f"{member.display_name}'s Stars", value=f"`{receiver['stars']:,}` {E.STAR}", inline=False)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="stars", description="Check golden stars.")
    async def stars(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        coins  = load_coins()
        user   = ensure_user(coins, member.id)
        e = embed(f"{E.STAR}  {member.display_name}'s Stars", f"**{user['stars']:,}** golden stars", C.TRIVIA)
        e.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="starleaderboard", description="Star leaderboard.")
    async def starleaderboard(self, ctx):
        coins = load_coins()
        board = sorted(coins.items(), key=lambda x: int(x[1].get("stars", 0)), reverse=True)[:10]
        medals = ["🥇", "🥈", "🥉"]
        lines  = []
        for i, (uid, data) in enumerate(board):
            member = ctx.guild.get_member(int(uid)) if ctx.guild else None
            name   = (member.display_name if member else f"User {uid}")[:20]
            you    = "  ← you" if int(uid) == ctx.author.id else ""
            medal  = medals[i] if i < 3 else f"{i+1}."
            lines.append(f"{medal}  **{name}** — `{data.get('stars',0):,}` {E.STAR}{you}")
        e = embed(f"{E.TROPHY}  Star Leaderboard", "\n".join(lines) or "No data.", C.TRIVIA)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="baltop", description="Richest users leaderboard.")
    async def baltop(self, ctx):
        coins = load_coins()
        board = sorted(coins.items(), key=lambda x: x[1].get("wallet", 0) + x[1].get("bank", 0), reverse=True)[:10]
        medals = ["🥇", "🥈", "🥉"]
        rows_data = []
        for i, (uid, data) in enumerate(board):
            total  = data.get("wallet", 0) + data.get("bank", 0)
            member = ctx.guild.get_member(int(uid)) if ctx.guild else None
            name   = (member.display_name if member else f"User {uid}")[:16]
            you    = " *" if int(uid) == ctx.author.id else ""
            medal  = medals[i] if i < 3 else f"{i+1:>2}."
            rows_data.append((medal, name + you, data.get("wallet", 0), data.get("bank", 0), total))
        name_w = max(len(r[1]) for r in rows_data) if rows_data else 4
        header = f"{'':3}  {'Name'.ljust(name_w)}  {'Wallet':>8}  {'Bank':>8}  {'Total':>8}"
        sep    = "─" * len(header)
        lines  = [header, sep]
        for medal, name, wallet, bank, total in rows_data:
            lines.append(f"{medal}  {name.ljust(name_w)}  {wallet:>8,}  {bank:>8,}  {total:>8,}")
        lines += [sep, f"{'':3}  {'* = you'.ljust(name_w)}"]
        e = embed(f"{E.TROPHY}  Balance Leaderboard", f"```\n{chr(10).join(lines)}\n```", C.ECONOMY)
        await ctx.send(embed=e)

    # ── ROB ───────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="rob", description="Attempt to rob someone's wallet.")
    async def rob(self, ctx, member: discord.Member):
        if member == ctx.author:
            return await ctx.send(embed=error("Rob", "You can't rob yourself."))
        if member.bot:
            return await ctx.send(embed=error("Rob", "Bots have no coins."))
        coins  = load_coins()
        robber = ensure_user(coins, ctx.author.id)
        victim = ensure_user(coins, member.id)
        now    = time.time()
        cd     = 60 if has_effect(robber, "kachow_clock_until") else 300
        if now - robber["last_rob"] < cd:
            return await ctx.send(embed=warn("Cooldown",
                f"{E.CLOCK} Try again in **{cooldown_str(int(cd-(now-robber['last_rob'])))}**."))
        if int(victim.get("wallet", 0)) <= 0:
            return await ctx.send(embed=warn("Rob Failed", f"{member.display_name} is broke."))
        robber["last_rob"] = now
        if random.random() < (0.20 if has_effect(victim, "comfort_until") else 0.40):
            steal = random.randint(10, min(200, victim["wallet"]))
            victim["wallet"]  -= steal
            robber["wallet"]  += steal
            save_coins(coins)
            e = embed(f"{E.ROB}  Robbery Success!", f"You swiped **{steal:,}** coins from {member.mention}.", C.WIN)
            e.add_field(name=f"{E.WALLET} Wallet", value=f"`{robber['wallet']:,}`", inline=True)
        else:
            debt_added = random.randint(30, 100)
            old_debt   = int(robber.get("debt", 0))
            robber["debt"] = old_debt + debt_added
            if old_debt == 0:
                robber["debt_since"] = now
            hit = min(robber["wallet"], int(debt_added * 0.03))
            robber["wallet"] = max(0, robber["wallet"] - hit)
            save_coins(coins)
            e = embed(f"{E.LOSE}  Busted!",
                      f"Caught trying to rob {member.mention}.\n\n"
                      f"{E.DEBT} Debt added: `{debt_added:,}`\n"
                      f"{E.COIN} Interest hit: `-{hit:,}`\n\n"
                      f"*Use `/repaydebt` fast — 3%/hr interest!*", C.LOSE)
            e.add_field(name=f"{E.WALLET} Wallet", value=f"`{robber['wallet']:,}`", inline=True)
            e.add_field(name=f"{E.DEBT} Debt",     value=f"`{robber['debt']:,}`",   inline=True)
        await ctx.send(embed=e)

    # ── BANK ROB ──────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="bankrob", description="Attempt to rob someone's bank.")
    async def bankrob(self, ctx, member: discord.Member):
        if member == ctx.author:
            return await ctx.send(embed=error("Bank Rob", "Can't rob your own bank."))
        if member.bot:
            return await ctx.send(embed=error("Bank Rob", "Bots have no banks."))
        coins  = load_coins()
        robber = ensure_user(coins, ctx.author.id)
        victim = ensure_user(coins, member.id)
        now    = time.time()
        cd     = 180 if has_effect(robber, "kachow_clock_until") else 600
        if now - robber["last_bankrob"] < cd:
            return await ctx.send(embed=warn("Cooldown",
                f"{E.CLOCK} Try again in **{cooldown_str(int(cd-(now-robber['last_bankrob'])))}**."))
        if int(victim.get("bank", 0)) <= 0:
            return await ctx.send(embed=warn("Bank Rob Failed", f"{member.display_name} has no bank savings."))
        robber["last_bankrob"] = now
        if random.random() < (0.05 if has_effect(victim, "comfort_until") else 0.20):
            pct    = random.uniform(BANKROB_STEAL_MIN_PCT, BANKROB_STEAL_MAX_PCT)
            amount = max(BANKROB_MIN_STEAL, int(victim["bank"] * pct))
            amount = min(amount, int(victim["bank"] * BANKROB_MAX_STEAL_PCT_CAP), victim["bank"])
            victim["bank"]    -= amount
            robber["wallet"]  += amount
            save_coins(coins)
            e = embed(f"{E.BANK}  Heist Success!",
                      f"Cracked {member.mention}'s vault for **{amount:,}** coins!", C.WIN)
            e.add_field(name=f"{E.WALLET} Wallet", value=f"`{robber['wallet']:,}`", inline=True)
        else:
            debt_added = random.randint(80, 200)
            old_debt   = int(robber.get("debt", 0))
            robber["debt"] = old_debt + debt_added
            if old_debt == 0:
                robber["debt_since"] = now
            hit = min(robber["wallet"], int(debt_added * 0.03))
            robber["wallet"] = max(0, robber["wallet"] - hit)
            save_coins(coins)
            e = embed(f"{E.LOSE}  Heist Failed!",
                      f"Security caught you at {member.mention}'s vault.\n\n"
                      f"{E.DEBT} Debt added: `{debt_added:,}`\n"
                      f"{E.COIN} Interest hit: `-{hit:,}`", C.LOSE)
            e.add_field(name=f"{E.WALLET} Wallet", value=f"`{robber['wallet']:,}`", inline=True)
            e.add_field(name=f"{E.DEBT} Debt",     value=f"`{robber['debt']:,}`",   inline=True)
        await ctx.send(embed=e)

    # ── RESET ECONOMY ─────────────────────────────────────────────────────────

    @commands.hybrid_command(name="reseteconomy", description="Reset all balances (admin only).")
    @commands.has_permissions(administrator=True)
    async def reseteconomy(self, ctx):
        from storage import load_data, save_data
        coins = load_coins()
        for uid in coins:
            coins[uid]["wallet"]     = 100
            coins[uid]["bank"]       = 0
            coins[uid]["debt"]       = 0
            coins[uid]["debt_since"] = 0
        save_coins(coins)
        data = load_data()
        import time as _t
        data["economy_reset_ts"] = _t.time()
        save_data(data)
        e = embed(f"{E.WARN_ACT}  Economy Reset",
                  "All wallets reset to **100** coins. Banks and debts cleared.\n\n"
                  "⚠️ Trivia prizes reduced by 75% for 24 hours.",
                  C.WARN, footer=f"Reset by {ctx.author.display_name}")
        await ctx.send(embed=e)

    @reseteconomy.error
    async def reseteconomy_error(self, ctx, err):
        if isinstance(err, commands.MissingPermissions):
            await ctx.send(embed=error("Permission Denied", "You need **Administrator**."))


async def setup(bot):
    await bot.add_cog(Economy(bot))
