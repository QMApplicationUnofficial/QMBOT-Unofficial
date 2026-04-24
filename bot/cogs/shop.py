import asyncio
import random
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands, tasks

import storage
from storage import (
    load_coins,
    save_coins,
    load_inventory,
    save_inventory,
    load_shop_stock,
    save_shop_stock,
    load_stocks,
    save_stocks,
)

from ui_utils import C, E, embed as _embed, error, success, warn
EMBED_COLOR = C.SHOP
SHOP_RESTOCK_MINUTES = 30

# =========================
# Shop definitions
# =========================

COIN_SHOP_ITEMS = {
    "Bank note": {
        "price": 1000,
        "max_stock": 9,
        "description": (
            "Spins a wheel of cash rewards.\n"
            "Possible results: 1, 5, 10, 20, 50, 100, 200, 250, 1000, 1500, 2000, Jackpot (10000)."
        ),
    },
    "Kachow clock": {
        "price": 10000,
        "max_stock": 3,
        "description": (
            "Reduces your rob cooldown to 1 minute and bankrob cooldown to 3 minutes for 1 hour."
        ),
    },
    "Pocket PC": {
        "price": 10000,
        "max_stock": 3,
        "description": (
            "Creates the Comfort buff for 1 hour.\n"
            "While active, the chance of being robbed becomes 20/80 and bankrobbed becomes 5/95."
        ),
    },
}

STAR_SHOP_ITEMS = {
    "Crash token": {
        "price": 2,
        "max_stock": 2,
        "description": "Halves the current price of a stock that you choose.",
    },
    "Fwiz's USB": {
        "price": 10,
        "max_stock": 1,
        "description": (
            "Targets a user and a stock. Has a chance to steal up to 40% of that user's shares in that stock."
        ),
    },
    "Imran's Nose": {
        "price": 100,
        "max_stock": 1,
        "description": "Resets all JSON files except the action command data.",
    },
}

BANK_NOTE_WHEEL = [1, 5, 10, 20, 50, 100, 200, 250, 1000, 1500, 2000, "JACKPOT"]


# =========================
# Helpers
# =========================

def make_embed(title: str, description: str) -> discord.Embed:
    return _embed(title, description, EMBED_COLOR)


def ensure_user(coins: dict, user_id: int | str) -> dict:
    uid = str(user_id)

    if uid not in coins:
        coins[uid] = {
            "wallet": 100,
            "bank": 0,
            "stars": 0,
            "portfolio": {},
            "active_effects": {},
        }
    else:
        coins[uid].setdefault("wallet", 100)
        coins[uid].setdefault("bank", 0)
        coins[uid].setdefault("stars", 0)
        coins[uid].setdefault("portfolio", {})
        coins[uid].setdefault("active_effects", {})

    return coins[uid]


def ensure_inventory(inv: dict, user_id: int | str) -> dict:
    uid = str(user_id)

    if uid not in inv:
        inv[uid] = {}

    return inv[uid]


def _ordered_coin_items():
    return sorted(COIN_SHOP_ITEMS.keys(), key=lambda x: COIN_SHOP_ITEMS[x]["price"])


def _ordered_star_items():
    return sorted(STAR_SHOP_ITEMS.keys(), key=lambda x: STAR_SHOP_ITEMS[x]["price"])


def _all_item_data() -> dict:
    data = {}
    data.update(COIN_SHOP_ITEMS)
    data.update(STAR_SHOP_ITEMS)
    return data


def _item_lookup(name: str) -> str | None:
    target = name.lower().strip()
    for item in _all_item_data():
        if item.lower() == target:
            return item
    return None


def _default_stock_data() -> dict:
    return {
        "coin_shop": generate_stock(COIN_SHOP_ITEMS),
        "star_shop": generate_stock(STAR_SHOP_ITEMS),
    }


def generate_stock(items: dict) -> dict:
    prices = [items[item]["price"] for item in items]
    min_price = min(prices)
    max_price = max(prices)

    stock = {}

    for item, meta in items.items():
        price = meta["price"]
        max_item_stock = meta["max_stock"]

        if max_price == min_price:
            score = 1.0
        else:
            score = 1 - ((price - min_price) / (max_price - min_price))

        score = max(0, min(1, score))
        appear_chance = 0.15 + (score * 0.85)

        if random.random() > appear_chance:
            stock[item] = 0
            continue

        upper = max(1, int(round(1 + score * (max_item_stock - 1))))
        stock[item] = random.randint(1, upper)

    return stock


def ensure_shop_stock(stock: dict) -> dict:
    if not isinstance(stock, dict):
        stock = _default_stock_data()

    if "coin_shop" not in stock or not isinstance(stock.get("coin_shop"), dict):
        stock["coin_shop"] = generate_stock(COIN_SHOP_ITEMS)

    if "star_shop" not in stock or not isinstance(stock.get("star_shop"), dict):
        stock["star_shop"] = generate_stock(STAR_SHOP_ITEMS)

    for item in COIN_SHOP_ITEMS:
        stock["coin_shop"].setdefault(item, 0)

    for item in STAR_SHOP_ITEMS:
        stock["star_shop"].setdefault(item, 0)

    for item in list(stock["coin_shop"].keys()):
        if item not in COIN_SHOP_ITEMS:
            stock["coin_shop"].pop(item)

    for item in list(stock["star_shop"].keys()):
        if item not in STAR_SHOP_ITEMS:
            stock["star_shop"].pop(item)

    save_shop_stock(stock)
    return stock


def _format_shop_table(items: list[str], stock_map: dict, price_map: dict) -> str:
    rows = []

    for item in items:
        price = price_map[item]
        qty = stock_map.get(item, 0)

        rows.append(
            f"{item[:16].ljust(16)} | "
            f"{str(qty).rjust(3)} | "
            f"{str(price).rjust(6)}"
        )

    return (
        "```text\n"
        "Item            |Qty |Price\n"
        "---------------------------\n"
        f"{chr(10).join(rows)}\n"
        "```"
    )


def _format_inventory_table(user_inv: dict) -> str:
    rows = []

    for item, qty in sorted(user_inv.items()):
        rows.append(
            f"{item[:16].ljust(16)} | "
            f"{str(qty).rjust(3)}"
        )

    return (
        "```text\n"
        "Item            |Qty\n"
        "--------------------\n"
        f"{chr(10).join(rows)}\n"
        "```"
    )


def _bank_note_reward() -> int:
    weighted = [
        1, 1, 1,
        5, 5,
        10, 10,
        20, 20,
        50, 50,
        100, 100,
        200,
        250,
        1000,
        1500,
        2000,
        "JACKPOT",
    ]
    choice = random.choice(weighted)
    return 10000 if choice == "JACKPOT" else int(choice)


def _spinner_text(values: list) -> str:
    line = " | ".join(str(v) for v in values)

    middle = str(values[2])
    left = " | ".join(str(v) for v in values[:2])
    prefix_len = len(left) + 3 if left else 0
    center_pos = prefix_len + (len(middle) // 2)

    arrow_line = " " * center_pos + "▲"

    return f"```text\n{line}\n{arrow_line}\n```"


def _future_ts(minutes: int = 0, hours: int = 0) -> float:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes, hours=hours)).timestamp()


def _reset_all_json_except_actions():
    reset_map = {
        storage.DATA_FILE: {},
        storage.COOLDOWN_FILE: {},
        storage.COIN_DATA_FILE: {},
        storage.SHOP_FILE: _default_stock_data(),
        storage.INVENTORY_FILE: {},
        storage.MARRIAGE_FILE: {},
        storage.PLAYLIST_FILE: {},
        storage.QUEST_FILE: {},
        storage.EVENT_FILE: {},
        storage.STOCK_FILE: {},
        storage.SUGGESTION_FILE: [],
        storage.TRIVIA_STATS_FILE: {},
        storage.TRIVIA_STREAKS_FILE: {},
        storage.BEG_STATS_FILE: {},
        storage.SWEAR_JAR_FILE: {"total": 0, "users": {}},
        storage.STICKER_FILE: {"total": 0, "users": {}, "daily": {}},
    }

    for path, default in reset_map.items():
        storage._save_json(path, default)


# =========================
# Confirm view
# =========================

class ConfirmClaimView(discord.ui.View):
    def __init__(self, *, author_id: int, on_confirm):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.on_confirm = on_confirm

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                embed=make_embed("Claim", "This confirmation isn't for you."),
                ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="✅  Confirm", style=discord.ButtonStyle.success)
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(view=self)
        await self.on_confirm(interaction)
        self.stop()

    @discord.ui.button(label="❌  Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            embed=_embed("❌  Cancelled", "Nothing was claimed.", C.LOSE),
            view=self
        )
        self.stop()


# =========================
# Shop cog
# =========================

class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.restock.start()

    def cog_unload(self):
        self.restock.cancel()

    @tasks.loop(minutes=SHOP_RESTOCK_MINUTES)
    async def restock(self):
        save_shop_stock(_default_stock_data())

    @restock.before_loop
    async def before_restock(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command(
        name="shop",
        description="View the coin shop."
    )
    async def shop(self, ctx: commands.Context):
        stock = ensure_shop_stock(load_shop_stock())
        table = _format_shop_table(
            _ordered_coin_items(),
            stock["coin_shop"],
            {k: v["price"] for k, v in COIN_SHOP_ITEMS.items()}
        )

        embed = discord.Embed(
            title="🛍️  Coin Shop",
            description=table,
            color=EMBED_COLOR
        )
        embed.set_footer(text="🛍️  Coin Shop  ·  Restocks every 30 minutes")
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="starshop",
        description="View the star shop."
    )
    async def starshop(self, ctx: commands.Context):
        stock = ensure_shop_stock(load_shop_stock())
        table = _format_shop_table(
            _ordered_star_items(),
            stock["star_shop"],
            {k: v["price"] for k, v in STAR_SHOP_ITEMS.items()}
        )

        embed = discord.Embed(
            title="⭐  Star Shop",
            description=table,
            color=EMBED_COLOR
        )
        embed.set_footer(text="⭐  Star Shop  ·  Prices in ✦ stars  ·  Restocks every 30 minutes")
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="buyitem",
        description="Buy an item from the coin shop."
    )
    async def buyitem(self, ctx: commands.Context, *, item: str):
        item = _item_lookup(item)

        if item not in COIN_SHOP_ITEMS:
            return await ctx.send(embed=make_embed("Shop", "Coin shop item not found."))

        stock = ensure_shop_stock(load_shop_stock())
        current_stock = stock["coin_shop"].get(item, 0)

        if current_stock <= 0:
            return await ctx.send(embed=make_embed("Shop", "That item is out of stock."))

        price = COIN_SHOP_ITEMS[item]["price"]

        coins = load_coins()
        user = ensure_user(coins, ctx.author.id)

        if user["wallet"] < price:
            return await ctx.send(embed=make_embed("Shop", "Not enough coins."))

        inv = load_inventory()
        user_inv = ensure_inventory(inv, ctx.author.id)

        user["wallet"] -= price
        user_inv[item] = user_inv.get(item, 0) + 1
        stock["coin_shop"][item] = current_stock - 1

        save_coins(coins)
        save_inventory(inv)
        save_shop_stock(stock)

        embed = discord.Embed(
            title="✅  Purchase Complete",
            description=f"Bought **{item}**",
            color=EMBED_COLOR
        )
        embed.add_field(name="Cost", value=f"`{price}`", inline=True)
        embed.add_field(name="Stock Left", value=f"`{stock['coin_shop'][item]}`", inline=True)
        embed.add_field(name="¢ Wallet", value=f"`{user['wallet']}`", inline=True)

        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="buystaritem",
        description="Buy an item from the star shop."
    )
    async def buystaritem(self, ctx: commands.Context, *, item: str):
        item = _item_lookup(item)

        if item not in STAR_SHOP_ITEMS:
            return await ctx.send(embed=make_embed("Star Shop", "Star shop item not found."))

        stock = ensure_shop_stock(load_shop_stock())
        current_stock = stock["star_shop"].get(item, 0)

        if current_stock <= 0:
            return await ctx.send(embed=make_embed("Star Shop", "That item is out of stock."))

        price = STAR_SHOP_ITEMS[item]["price"]

        coins = load_coins()
        user = ensure_user(coins, ctx.author.id)

        if user["stars"] < price:
            return await ctx.send(embed=make_embed("Star Shop", "Not enough golden stars."))

        inv = load_inventory()
        user_inv = ensure_inventory(inv, ctx.author.id)

        user["stars"] -= price
        user_inv[item] = user_inv.get(item, 0) + 1
        stock["star_shop"][item] = current_stock - 1

        save_coins(coins)
        save_inventory(inv)
        save_shop_stock(stock)

        embed = discord.Embed(
            title="✅  Purchase Complete",
            description=f"Bought **{item}**",
            color=EMBED_COLOR
        )
        embed.add_field(name="Cost", value=f"`{price}` ✦", inline=True)
        embed.add_field(name="Stock Left", value=f"`{stock['star_shop'][item]}`", inline=True)
        embed.add_field(name="✦ Stars", value=f"`{user['stars']}`", inline=True)

        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="inventory",
        description="View your inventory."
    )
    async def inventory(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author

        inv = load_inventory()
        user_inv = ensure_inventory(inv, member.id)

        if not user_inv:
            return await ctx.send(embed=make_embed("Inventory", "Inventory empty."))

        table = _format_inventory_table(user_inv)

        embed = discord.Embed(
            title=f"📦  {member.display_name}'s Inventory",
            description=table,
            color=EMBED_COLOR
        )
        embed.set_footer(text="Use /claim <item> to use an item")
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="info",
        description="Show info for an item or all items."
    )
    async def info(self, ctx: commands.Context, *, item: str = "all"):
        item = item.strip()

        if item.lower() == "all":
            lines = []

            for name in _ordered_coin_items():
                meta = COIN_SHOP_ITEMS[name]
                lines.append(
                    f"**{name}**\n"
                    f"Cost: `{meta['price']}` coins\n"
                    f"Max stock: `{meta['max_stock']}`\n"
                    f"{meta['description']}\n"
                )

            for name in _ordered_star_items():
                meta = STAR_SHOP_ITEMS[name]
                lines.append(
                    f"**{name}**\n"
                    f"Cost: `{meta['price']}` ✦ stars\n"
                    f"Max stock: `{meta['max_stock']}`\n"
                    f"{meta['description']}\n"
                )

            embed = make_embed("Item Info", "\n".join(lines)[:4000])
            return await ctx.send(embed=embed)

        real_item = _item_lookup(item)

        if not real_item:
            return await ctx.send(embed=make_embed("Item Info", "Item not found."))

        meta = _all_item_data()[real_item]
        currency = "coins" if real_item in COIN_SHOP_ITEMS else "✦ stars"

        embed = make_embed(
            real_item,
            (
                f"Cost: `{meta['price']}` {currency}\n"
                f"Max stock: `{meta['max_stock']}`\n\n"
                f"{meta['description']}"
            )
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="claim",
        description="Claim a usable inventory item."
    )
    async def claim(self, ctx: commands.Context, *, item: str):
        real_item = _item_lookup(item)

        if not real_item:
            return await ctx.send(embed=make_embed("Claim", "Item not found."))

        inv = load_inventory()
        user_inv = ensure_inventory(inv, ctx.author.id)

        if user_inv.get(real_item, 0) <= 0:
            return await ctx.send(embed=make_embed("Claim", "You do not own that item."))

        if real_item == "Crash token":
            return await ctx.send(embed=make_embed("Claim", "Use `/claimcrash <stock>` for Crash token."))

        if real_item == "Fwiz's USB":
            return await ctx.send(embed=make_embed("Claim", "Use `/claimusb <member> <stock>` for Fwiz's USB."))

        async def do_claim(interaction: discord.Interaction):
            inv_data = load_inventory()
            user_inv_live = ensure_inventory(inv_data, ctx.author.id)

            if user_inv_live.get(real_item, 0) <= 0:
                return await interaction.message.edit(
                    embed=make_embed("Claim", "You no longer own that item."),
                    view=None
                )

            user_inv_live[real_item] -= 1
            if user_inv_live[real_item] <= 0:
                user_inv_live.pop(real_item, None)
            save_inventory(inv_data)

            coins = load_coins()
            user = ensure_user(coins, ctx.author.id)

            if real_item == "Kachow clock":
                user["active_effects"]["kachow_clock_until"] = _future_ts(hours=1)
                save_coins(coins)

                embed = make_embed(
                    "Claimed: Kachow clock",
                    "Your rob cooldown is now **1 minute** and bankrob cooldown is **3 minutes** for **1 hour**."
                )
                await interaction.message.edit(embed=embed, view=None)

            elif real_item == "Pocket PC":
                user["active_effects"]["comfort_until"] = _future_ts(hours=1)
                save_coins(coins)

                embed = make_embed(
                    "Claimed: Pocket PC",
                    "Comfort buff activated for **1 hour**.\nYour robbery defense is now stronger."
                )
                await interaction.message.edit(embed=embed, view=None)

            elif real_item == "Bank note":
                await interaction.message.edit(embed=make_embed("Bank Note", "Spinning..."), view=None)

                final_reward = _bank_note_reward()
                delays = [0.08, 0.10, 0.12, 0.16, 0.20, 0.28]

                for delay in delays:
                    values = [random.choice(BANK_NOTE_WHEEL) for _ in range(5)]
                    await interaction.message.edit(
                        embed=make_embed("Bank Note", _spinner_text(values)),
                        view=None
                    )
                    await asyncio.sleep(delay)

                final_values = [random.choice(BANK_NOTE_WHEEL) for _ in range(5)]
                final_values[2] = final_reward

                coins = load_coins()
                user = ensure_user(coins, ctx.author.id)
                user["wallet"] += final_reward
                save_coins(coins)

                result_embed = make_embed(
                    "Bank Note Result",
                    _spinner_text(final_values) + f"\nYou won **{final_reward}** coins."
                )
                result_embed.add_field(name="¢ Wallet", value=f"`{user['wallet']}`", inline=False)

                await interaction.message.edit(embed=result_embed, view=None)

            elif real_item == "Imran's Nose":
                _reset_all_json_except_actions()
                embed = make_embed(
                    "Claimed: Imran's Nose",
                    "All JSON data has been reset.\nAction commands were kept."
                )
                await interaction.message.edit(embed=embed, view=None)

        view = ConfirmClaimView(author_id=ctx.author.id, on_confirm=do_claim)

        await ctx.send(
            embed=make_embed(
                "Claim Confirmation",
                f"Are you sure you want to claim **{real_item}**?"
            ),
            view=view
        )

    @commands.hybrid_command(
        name="claimcrash",
        description="Claim a Crash token on a stock."
    )
    async def claimcrash(self, ctx: commands.Context, stock: str):
        inv = load_inventory()
        user_inv = ensure_inventory(inv, ctx.author.id)

        if user_inv.get("Crash token", 0) <= 0:
            return await ctx.send(embed=make_embed("Crash Token", "You do not own a Crash token."))

        stocks = load_stocks()
        stock_names = {s.lower(): s for s in stocks.keys()}
        key = stock.lower().strip()

        if key not in stock_names:
            return await ctx.send(embed=make_embed("Crash Token", "Unknown stock."))

        stock_name = stock_names[key]

        async def do_claim(interaction: discord.Interaction):
            inv_data = load_inventory()
            user_inv_live = ensure_inventory(inv_data, ctx.author.id)

            if user_inv_live.get("Crash token", 0) <= 0:
                return await interaction.message.edit(
                    embed=make_embed("Crash Token", "You no longer own a Crash token."),
                    view=None
                )

            user_inv_live["Crash token"] -= 1
            if user_inv_live["Crash token"] <= 0:
                user_inv_live.pop("Crash token", None)
            save_inventory(inv_data)

            stocks_data = load_stocks()
            if stock_name not in stocks_data:
                return await interaction.message.edit(
                    embed=make_embed("Crash Token", "That stock no longer exists."),
                    view=None
                )

            old_price = int(stocks_data[stock_name].get("price", 0))
            new_price = max(1, old_price // 2)

            stocks_data[stock_name]["price"] = new_price
            history = stocks_data[stock_name].get("history", [])
            history.append(new_price)
            stocks_data[stock_name]["history"] = history[-240:]
            save_stocks(stocks_data)

            embed = make_embed(
                "Crash Token Used",
                f"**{stock_name}** was halved from **{old_price}** to **{new_price}**."
            )
            await interaction.message.edit(embed=embed, view=None)

        view = ConfirmClaimView(author_id=ctx.author.id, on_confirm=do_claim)

        await ctx.send(
            embed=make_embed(
                "Claim Confirmation",
                f"Are you sure you want to crash **{stock_name}**?"
            ),
            view=view
        )

    @commands.hybrid_command(
        name="claimusb",
        description="Claim Fwiz's USB against a user's stock."
    )
    async def claimusb(self, ctx: commands.Context, member: discord.Member, stock: str):
        if member == ctx.author:
            return await ctx.send(embed=make_embed("Fwiz's USB", "You can't use this on yourself."))

        inv = load_inventory()
        user_inv = ensure_inventory(inv, ctx.author.id)

        if user_inv.get("Fwiz's USB", 0) <= 0:
            return await ctx.send(embed=make_embed("Fwiz's USB", "You do not own Fwiz's USB."))

        coins = load_coins()
        victim = ensure_user(coins, member.id)

        stock_names = {s.lower(): s for s in victim.get("portfolio", {}).keys()}
        key = stock.lower().strip()

        if key not in stock_names:
            return await ctx.send(embed=make_embed("Fwiz's USB", "That user does not have that stock."))

        stock_name = stock_names[key]
        victim_owned = int(victim["portfolio"].get(stock_name, 0))

        if victim_owned <= 0:
            return await ctx.send(embed=make_embed("Fwiz's USB", "That user has no shares to steal."))

        async def do_claim(interaction: discord.Interaction):
            inv_data = load_inventory()
            user_inv_live = ensure_inventory(inv_data, ctx.author.id)

            if user_inv_live.get("Fwiz's USB", 0) <= 0:
                return await interaction.message.edit(
                    embed=make_embed("Fwiz's USB", "You no longer own Fwiz's USB."),
                    view=None
                )

            user_inv_live["Fwiz's USB"] -= 1
            if user_inv_live["Fwiz's USB"] <= 0:
                user_inv_live.pop("Fwiz's USB", None)
            save_inventory(inv_data)

            coins_data = load_coins()
            attacker_live = ensure_user(coins_data, ctx.author.id)
            victim_live = ensure_user(coins_data, member.id)

            owned_now = int(victim_live["portfolio"].get(stock_name, 0))

            if owned_now <= 0:
                return await interaction.message.edit(
                    embed=make_embed("Fwiz's USB", "They no longer have any shares to steal."),
                    view=None
                )

            success = random.random() < 0.40

            if success:
                max_steal = max(1, int(owned_now * 0.40))
                stolen = random.randint(1, max_steal)

                victim_live["portfolio"][stock_name] = owned_now - stolen
                attacker_live["portfolio"][stock_name] = int(
                    attacker_live["portfolio"].get(stock_name, 0)
                ) + stolen

                save_coins(coins_data)

                embed = make_embed(
                    "Fwiz's USB Success",
                    f"You stole **{stolen}** shares of **{stock_name}** from {member.mention}."
                )
            else:
                save_coins(coins_data)
                embed = make_embed(
                    "Fwiz's USB Failed",
                    f"The USB failed to steal any **{stock_name}** shares from {member.mention}."
                )

            await interaction.message.edit(embed=embed, view=None)

        view = ConfirmClaimView(author_id=ctx.author.id, on_confirm=do_claim)

        await ctx.send(
            embed=make_embed(
                "Claim Confirmation",
                f"Are you sure you want to use **Fwiz's USB** on {member.mention} for **{stock_name}**?"
            ),
            view=view
        )


async def setup(bot):
    await bot.add_cog(Shop(bot))
