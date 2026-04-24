"""
fun.py — Fun commands
Removed: ascii, reverse, roll, poll, highlow, googleit, wordcount
Renamed: uwuify -> fandomify
Added: cooldowns on iq/rate, Next buttons on nhie/wyr, quote from replied message,
       howgay uses pfp + percentage bar only, RPS vs another person
"""

import asyncio
import hashlib
import io
import random
import time
import re
from datetime import date

import aiohttp
import discord
from discord.ext import commands

from ui_utils import C, E, embed, error, warn, success

TENOR_API_KEY = "AIzaSyAyimkuEcdEnPs55ueys84EMt_lFe0BXKQ"
TENOR_BASE    = "https://tenor.googleapis.com/v2/search"

# Cooldowns  uid -> last_used timestamp
_iq_cd:   dict[int, float] = {}
_rate_cd: dict[int, float] = {}
IQ_COOLDOWN   = 3600   # 1 hour
RATE_COOLDOWN = 300    # 5 minutes

EIGHT_BALL_RESPONSES = [
    ("It is certain.",              True),
    ("Without a doubt.",            True),
    ("You may rely on it.",         True),
    ("Yes, definitely.",            True),
    ("As I see it, yes.",           True),
    ("Most likely.",                True),
    ("Outlook good.",               True),
    ("Signs point to yes.",         True),
    ("Reply hazy, try again.",      None),
    ("Ask again later.",            None),
    ("Cannot predict now.",         None),
    ("Concentrate and ask again.", None),
    ("Don't count on it.",          False),
    ("My reply is no.",             False),
    ("Very doubtful.",              False),
    ("Outlook not so good.",        False),
    ("My sources say no.",          False),
]

FACTS = [
    "Honey never spoils. Archaeologists found 3000-year-old honey in Egyptian tombs that was still edible.",
    "A day on Venus is longer than a year on Venus.",
    "Octopuses have three hearts, and two of them stop beating when they swim.",
    "The shortest war in history lasted 38–45 minutes — Britain vs Zanzibar, 1896.",
    "Cleopatra lived closer in time to the Moon landing than to the construction of the Great Pyramid.",
    "Bananas are slightly radioactive due to their potassium content.",
    "A group of flamingos is called a flamboyance.",
    "The inventor of the frisbee was turned into a frisbee after he died. His ashes were pressed into one.",
    "Wombat poo is cube-shaped. No other animal produces cube-shaped faeces.",
    "There are more possible iterations of a chess game than atoms in the observable universe.",
    "The average person walks past 36 murderers in their lifetime. Sleep well.",
    "Crows can recognise human faces and hold grudges for years.",
    "A bolt of lightning contains enough energy to toast about 100,000 slices of bread.",
    "The unicorn is Scotland's national animal.",
    "Pineapples take about 2 years to grow.",
    "Sharks are older than trees. They've been around for over 450 million years.",
    "There are more stars in the universe than grains of sand on all of Earth's beaches.",
    "The inventor of the world wide web, Tim Berners-Lee, never patented it — he gave it away for free.",
    "A day on Mercury lasts longer than a year on Mercury.",
    "Humans share 50% of their DNA with bananas.",
]

ROASTS = [
    "You're the human equivalent of a participation trophy.",
    "I'd roast you, but my mum said I'm not allowed to burn trash.",
    "You're proof that even evolution makes mistakes.",
    "You have something on your chin... no, the third one down.",
    "If brains were petrol, you wouldn't have enough to power an ant's go-kart around a Cheerio.",
    "I've seen better-looking faces on a clock.",
    "You're not stupid — you just have bad luck thinking.",
    "You're like a software update. Every time I see you, I think 'not now'.",
    "I would explain it to you, but I left my crayons at home.",
    "You're the reason they put instructions on shampoo bottles.",
]

WYR_QUESTIONS = [
    "Would you rather fight 100 duck-sized horses or 1 horse-sized duck?",
    "Would you rather know when you're going to die or how you're going to die?",
    "Would you rather have unlimited money but no friends, or be broke but have amazing friends?",
    "Would you rather be able to fly but only at walking pace, or run at 100mph but only backwards?",
    "Would you rather always have to say everything you think, or never speak again?",
    "Would you rather lose all your memories or never make new ones?",
    "Would you rather eat a meal of your least favourite food every day or never eat again?",
    "Would you rather have hiccups for the rest of your life or always feel like you need to sneeze?",
    "Would you rather be famous but hated or unknown but beloved?",
    "Would you rather have a rewind button for your life or a pause button?",
    "Would you rather be able to read minds but never be able to turn it off, or be completely invisible but only when no one is looking?",
    "Would you rather give up the internet for a year or give up all streaming services forever?",
    "Would you rather have the ability to speak every language fluently or play every instrument perfectly?",
    "Would you rather always be 10 minutes late or always be 2 hours early?",
    "Would you rather have no phone for a month or no food for a week?",
    "Would you rather live in a world without music or a world without colour?",
    "Would you rather be able to pause time or rewind it, but only once per day?",
    "Would you rather be the funniest person in the room or the smartest?",
    "Would you rather know every language but only speak in riddles, or speak normally but only in your native tongue forever?",
    "Would you rather have to whisper everything you say or shout everything you say?",
]

NHIE = [
    "Never have I ever gone to bed without brushing my teeth.",
    "Never have I ever replied 'on my way' while still in bed.",
    "Never have I ever laughed so hard I cried in public.",
    "Never have I ever sent a text to the wrong person.",
    "Never have I ever pretended to be busy to avoid someone.",
    "Never have I ever accidentally liked an old photo while stalking someone.",
    "Never have I ever fallen asleep in class or a meeting.",
    "Never have I ever eaten food that fell on the floor.",
    "Never have I ever Googled myself.",
    "Never have I ever stayed up past 4 AM for no real reason.",
    "Never have I ever cried at a movie and denied it afterwards.",
    "Never have I ever bought something expensive and hidden it from someone.",
    "Never have I ever pretended to laugh at a joke I didn't get.",
    "Never have I ever faked being sick to get out of plans.",
    "Never have I ever eavesdropped on a conversation I wasn't part of.",
    "Never have I ever read someone's messages without them knowing.",
    "Never have I ever convinced someone of something completely false just to see if they'd believe it.",
    "Never have I ever ended a friendship over something absolutely petty.",
    "Never have I ever cheated at a board game and got away with it.",
    "Never have I ever regretted sending a message before it even arrived.",
]

TOPICS = [
    "If you found out your whole life was a simulation, what's the first thing you'd test?",
    "What's the most genuinely useful skill most people don't have?",
    "If aliens landed and you were the first human they met, what's the first thing you'd say?",
    "What's something that was embarrassing 5 years ago that's now completely normal?",
    "If you could delete one song from existence — not ban it, delete it from ever existing — what is it?",
    "What's a law that doesn't exist but absolutely should?",
    "If you had to pick one person in this server to survive a zombie apocalypse with, who and why?",
    "What's the most expensive lesson you've ever learned?",
    "At what point does a collection become a problem?",
    "What's an opinion you hold that you know the majority disagrees with?",
    "If your personality was a type of weather, what would it be?",
    "What's a universally loved thing that you genuinely don't understand the appeal of?",
    "If you could know the absolute truth to one question, what would you ask?",
    "What's the most chaotic thing someone could do that isn't technically illegal?",
    "What's the worst way a story could end?",
    "If you had to eat one meal for the rest of your life, what do you choose and what goes wrong?",
    "What skill do you have that would be genuinely useless if society collapsed?",
    "What's the fastest way to lose a friend without being directly rude?",
    "What mundane superpower would actually change your life the most?",
    "If this server were a country, what would the national dish be and why is it something cursed?",
]

DARES = [
    "Message someone random in this server and say 'I know what you did'.",
    "Change your nickname to something embarrassing for the next hour.",
    "Send a voice message of you singing any song.",
    "Post your screen time stats.",
    "Tell us your most embarrassing autocorrect fail.",
    "Send the last thing you copied to your clipboard.",
    "Type with your elbows for your next three messages.",
    "Say something genuinely nice about every person in this channel.",
    "Send your most recent photo from your camera roll.",
    "DM someone 'I think we need to talk' and wait 2 minutes before saying it's a dare.",
    "Post your Spotify top artist or most played song.",
    "Write a 3-line poem about the person above you right now.",
]


def _seed(text: str) -> int:
    key = f"{text.lower().strip()}{date.today().isoformat()}"
    return int(hashlib.md5(key.encode()).hexdigest(), 16) % 101


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


def _cd_remaining(store: dict, uid: int, seconds: int) -> int:
    last = store.get(uid, 0)
    remaining = int(seconds - (time.time() - last))
    return max(0, remaining)


class WYRView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.button(label="Next Question", style=discord.ButtonStyle.primary)
    async def next_q(self, interaction: discord.Interaction, button: discord.ui.Button):
        q = random.choice(WYR_QUESTIONS)
        e = embed("🤔  Would You Rather…", q, C.GAMES,
                  footer=f"Asked by {interaction.user.display_name}")
        view = WYRView()
        await interaction.response.edit_message(embed=e, view=view)


class NHIEView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.current = random.choice(NHIE)

    def build_embed(self) -> discord.Embed:
        return embed("🙋  Never Have I Ever…", self.current, C.GAMES,
                     footer="Press I Have or I Haven't — or get a new one!")

    @discord.ui.button(label="✋  I Have", style=discord.ButtonStyle.danger)
    async def have(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=embed("📢", f"{interaction.user.mention} **HAS** done this 👀", C.LOSE),
            ephemeral=False
        )

    @discord.ui.button(label="🙅  I Haven't", style=discord.ButtonStyle.success)
    async def havent(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=embed("📢", f"{interaction.user.mention} has **NOT** done this ✅", C.WIN),
            ephemeral=False
        )

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_q(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current = random.choice(NHIE)
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class RPSChallengeView(discord.ui.View):
    BEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
    EMOJI = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}

    def __init__(self, challenger: discord.Member, opponent: discord.Member):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent   = opponent
        self.choices: dict[int, str] = {}
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in (self.challenger.id, self.opponent.id):
            await interaction.response.send_message(
                embed=error("RPS", "You're not in this game."), ephemeral=True)
            return False
        return True

    def _make_cb(self, choice: str):
        async def callback(interaction: discord.Interaction):
            uid = interaction.user.id
            if uid in self.choices:
                await interaction.response.send_message(
                    embed=warn("RPS", "You already picked!"), ephemeral=True)
                return
            self.choices[uid] = choice
            await interaction.response.send_message(
                embed=embed("🤫  Locked In", f"You chose **{self.EMOJI[choice]} {choice}**. Waiting for opponent…", C.NEUTRAL),
                ephemeral=True,
            )
            if len(self.choices) == 2:
                await self._resolve()
        return callback

    async def _resolve(self):
        for c in self.children:
            c.disabled = True
        c1 = self.choices[self.challenger.id]
        c2 = self.choices[self.opponent.id]
        e1, e2 = self.EMOJI[c1], self.EMOJI[c2]
        if c1 == c2:
            result = "**Tie!** 🤝"
            color  = C.NEUTRAL
        elif self.BEATS[c1] == c2:
            result = f"**{self.challenger.display_name} wins!** 🎉"
            color  = C.WIN
        else:
            result = f"**{self.opponent.display_name} wins!** 🎉"
            color  = C.WIN
        desc = (
            f"{self.challenger.mention}  {e1} **{c1}**\n"
            f"{self.opponent.mention}  {e2} **{c2}**\n\n"
            f"{result}"
        )
        e = embed("🪨📄✂️  Result", desc, color)
        if self.message:
            await self.message.edit(embed=e, view=self)
        self.stop()

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True
        missing = []
        if self.challenger.id not in self.choices:
            missing.append(self.challenger.display_name)
        if self.opponent.id not in self.choices:
            missing.append(self.opponent.display_name)
        if self.message:
            await self.message.edit(
                embed=warn("RPS Timed Out", f"{', '.join(missing)} didn't pick in time."),
                view=self,
            )

    @discord.ui.button(label="🪨  Rock", style=discord.ButtonStyle.secondary)
    async def rock(self, i, b):
        await self._make_cb("rock")(i)

    @discord.ui.button(label="📄  Paper", style=discord.ButtonStyle.secondary)
    async def paper(self, i, b):
        await self._make_cb("paper")(i)

    @discord.ui.button(label="✂️  Scissors", style=discord.ButtonStyle.secondary)
    async def scissors(self, i, b):
        await self._make_cb("scissors")(i)


class Fun(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="8ball", description="Ask the magic 8-ball a question.")
    async def eightball(self, ctx, *, question: str):
        response, positive = random.choice(EIGHT_BALL_RESPONSES)
        color  = C.WIN if positive is True else (C.LOSE if positive is False else C.NEUTRAL)
        symbol = "✅" if positive is True else ("❌" if positive is False else "🔮")
        e = embed("🎱  Magic 8-Ball",
                  f"**{ctx.author.display_name} asks:**\n> {question}\n\n{symbol}  *{response}*",
                  color, footer="The 8-ball has spoken.")
        await ctx.send(embed=e)

    @commands.hybrid_command(name="rps", description="Challenge someone to Rock Paper Scissors.")
    async def rps(self, ctx, opponent: discord.Member):
        if opponent == ctx.author:
            return await ctx.send(embed=error("RPS", "You can't play yourself."))
        if opponent.bot:
            return await ctx.send(embed=error("RPS", "Bots don't have thumbs."))
        view = RPSChallengeView(ctx.author, opponent)
        e = embed(
            "🪨📄✂️  Rock Paper Scissors",
            f"{ctx.author.mention} has challenged {opponent.mention}!\n\n"
            f"**Both players** — pick your weapon below.\nYour choice is hidden until both have picked.",
            C.GAMES,
            footer="60 seconds to choose",
        )
        msg = await ctx.send(embed=e, view=view)
        view.message = msg

    @commands.hybrid_command(name="choose", description="Pick one option from a comma-separated list.")
    async def choose(self, ctx, *, options: str):
        choices = [o.strip() for o in options.split(",") if o.strip()]
        if len(choices) < 2:
            return await ctx.send(embed=error("Choose", "Give me at least 2 options, separated by commas."))
        picked = random.choice(choices)
        e = embed("🤔  The bot chooses…", f"**{picked}**\n\n*From: {', '.join(choices)}*", C.GAMES)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="ship", description="Ship two users and get a compatibility score.")
    async def ship(self, ctx, user1: discord.Member, user2: discord.Member):
        score     = _seed(f"{min(user1.id, user2.id)}{max(user1.id, user2.id)}")
        filled    = score // 10
        bar       = "█" * filled + "░" * (10 - filled)
        if score >= 90:
            verdict = "Absolutely soulmates. 💍"
        elif score >= 70:
            verdict = "Strong vibes. 💕"
        elif score >= 50:
            verdict = "Could work with effort. 🤔"
        elif score >= 30:
            verdict = "Complicated... 😬"
        else:
            verdict = "Run. Now. 💀"
        ship_name = user1.display_name[:len(user1.display_name)//2] + user2.display_name[len(user2.display_name)//2:]
        e = embed(
            f"💘  {user1.display_name} × {user2.display_name}",
            f"**Ship name:** _{ship_name}_\n\n`{bar}` **{score}%**\n{verdict}",
            C.MARRIAGE,
        )
        await ctx.send(embed=e)

    @commands.hybrid_command(name="howgay", description="How gay are you today?")
    async def howgay(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        score  = _seed(f"gay{member.id}")
        filled = score // 10
        bar    = "█" * filled + "░" * (10 - filled)
        e = embed(
            "Gay-O-Meter",
            f"`{bar}` **{score}%**",
            C.SOCIAL,
            footer=f"Results for {member.display_name}",
        )
        e.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="iq", description="Check someone's IQ score.")
    async def iq(self, ctx, member: discord.Member = None):
        uid = ctx.author.id
        remaining = _cd_remaining(_iq_cd, uid, IQ_COOLDOWN)
        if remaining:
            m, s = divmod(remaining, 60)
            h, m = divmod(m, 60)
            return await ctx.send(embed=warn("IQ Cooldown", f"Your brain needs rest. Try again in **{h}h {m}m {s}s**."))
        _iq_cd[uid] = time.time()
        member = member or ctx.author
        score  = _seed(f"iq{member.id}")
        iq_val = max(1, int(score * 2.5))
        if iq_val >= 200:
            verdict = "Literally Einstein reborn."
        elif iq_val >= 140:
            verdict = "Certified genius territory."
        elif iq_val >= 100:
            verdict = "Average. Disappointingly average."
        elif iq_val >= 70:
            verdict = "Concerning."
        else:
            verdict = "How are you even typing?"
        e = embed("🧠  IQ Test Results", f"{member.mention}\n\n**IQ: {iq_val}**\n_{verdict}_", C.TRIVIA,
                  footer="Cooldown: 1 hour")
        e.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="simp", description="How much of a simp are you?")
    async def simp(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        score  = _seed(f"simp{member.id}")
        filled = score // 10
        bar    = "█" * filled + "░" * (10 - filled)
        e = embed("💝  Simp Detector", f"{member.mention}\n\n`{bar}` **{score}% simp**", C.MARRIAGE)
        e.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="pp", description="The important measurement.")
    async def pp(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        size   = _seed(f"pp{member.id}") // 10
        e = embed("📏  PP Size", f"{member.mention}\n\n`8{'=' * size}D`\n\n**{size} inches**", C.NEUTRAL)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="rate", description="Bot rates anything out of 10.")
    async def rate(self, ctx, *, thing: str):
        uid = ctx.author.id
        remaining = _cd_remaining(_rate_cd, uid, RATE_COOLDOWN)
        if remaining:
            return await ctx.send(embed=warn("Rate Cooldown", f"Try again in **{remaining}s**."))
        _rate_cd[uid] = time.time()
        score = _seed(thing) // 10
        bar   = "█" * score + "░" * (10 - score)
        e = embed("⭐  Rating", f"**{thing}**\n\n`{bar}` **{score}/10**", C.TRIVIA,
                  footer="Cooldown: 5 minutes")
        await ctx.send(embed=e)

    @commands.hybrid_command(name="mock", description="SpOnGeBoB mOcK someone's text.")
    async def mock(self, ctx, *, text: str):
        mocked = "".join(c.upper() if i % 2 else c.lower() for i, c in enumerate(text))
        e = embed("🧽  mOcKeD", f"> {mocked}", C.SOCIAL)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="clap", description="👏 ADD 👏 CLAPS 👏 BETWEEN 👏 EVERY 👏 WORD")
    async def clap(self, ctx, *, text: str):
        e = embed("👏  Clapped", " 👏 ".join(text.split()), C.SOCIAL)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="fandomify", description="Transform text into fandom/tumblr speech.")
    async def fandomify(self, ctx, *, text: str):
        t = text.replace("r", "w").replace("l", "w").replace("R", "W").replace("L", "W")
        t = t.replace("na", "nya").replace("Na", "Nya").replace("no", "nyo").replace("No", "Nyo")
        t = t.replace("ne", "nye").replace("Ne", "Nye")
        t = t.replace("th", "d").replace("Th", "D")
        additions = [" uwu", " owo", " >w<", " :3", " nya~", " ✨", " /lh", " /pos", ""]
        t += random.choice(additions)
        e = embed("✨  Fandomified", f"> {t}", C.MARRIAGE)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="emojify", description="Turn text into big letter emoji.")
    async def emojify(self, ctx, *, text: str):
        result = ""
        for ch in text.lower():
            if ch.isalpha():
                result += f":regional_indicator_{ch}: "
            elif ch == " ":
                result += "   "
            elif ch.isdigit():
                names = ["zero","one","two","three","four","five","six","seven","eight","nine"]
                result += f":{names[int(ch)]}: "
        if len(result) > 500:
            return await ctx.send(embed=error("Emojify", "Text is too long."))
        e = embed("🔡  Emojified", result or "…", C.SOCIAL)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="fact", description="Get a random interesting fact.")
    async def fact(self, ctx):
        e = embed("🧠  Random Fact", random.choice(FACTS), C.TRIVIA, footer="The more you know ✨")
        await ctx.send(embed=e)

    @commands.hybrid_command(name="quote", description="Reply to a message to quote it, or just run to get a random famous quote.")
    async def quote(self, ctx):
        ref = ctx.message.reference
        if ref and ref.resolved and isinstance(ref.resolved, discord.Message):
            quoted_msg = ref.resolved
            author     = quoted_msg.author
            content    = quoted_msg.content or "[no text content]"

            e = discord.Embed(
                description=f"*\"{content}\"*",
                color=C.TRIVIA,
                timestamp=quoted_msg.created_at,
            )
            e.set_author(
                name=author.display_name,
                icon_url=author.display_avatar.url,
            )
            e.set_footer(text=f"Quoted by {ctx.author.display_name} · #{getattr(ctx.channel, 'name', 'unknown')}")
            e.set_thumbnail(url=author.display_avatar.url)
            await ctx.send(embed=e)
        else:
            famous = [
                ("The only way to do great work is to love what you do.", "Steve Jobs"),
                ("It does not matter how slowly you go, as long as you do not stop.", "Confucius"),
                ("Life is what happens when you're busy making other plans.", "John Lennon"),
                ("In the middle of every difficulty lies opportunity.", "Albert Einstein"),
                ("You miss 100% of the shots you don't take.", "Wayne Gretzky"),
                ("Whether you think you can or you think you can't, you're right.", "Henry Ford"),
                ("Be yourself; everyone else is already taken.", "Oscar Wilde"),
                ("It always seems impossible until it is done.", "Nelson Mandela"),
                ("Two things are infinite: the universe and human stupidity.", "Albert Einstein"),
                ("The future belongs to those who believe in the beauty of their dreams.", "Eleanor Roosevelt"),
            ]
            text, attr = random.choice(famous)
            e = embed("💬  Quote", f"*\"{text}\"*\n\n— **{attr}**", C.TRIVIA,
                      footer="Tip: reply to a message and use /quote to quote that person")
            await ctx.send(embed=e)

    @commands.hybrid_command(name="roast", description="Auto-roast a user.")
    async def roast(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        e = embed(f"🔥  Roasting {member.display_name}",
                  f"{member.mention}\n\n> {random.choice(ROASTS)}", C.SOCIAL,
                  footer=f"Delivered by {ctx.author.display_name}")
        await ctx.send(embed=e)

    @commands.hybrid_command(name="wyr", description="Random would you rather question.")
    async def wyr(self, ctx):
        q    = random.choice(WYR_QUESTIONS)
        view = WYRView()
        e    = embed("🤔  Would You Rather…", q, C.GAMES, footer=f"Asked by {ctx.author.display_name}")
        await ctx.send(embed=e, view=view)

    @commands.hybrid_command(name="dare", description="Get a random dare.")
    async def dare(self, ctx):
        e = embed("😈  Dare", random.choice(DARES), C.SOCIAL, footer="Do it. No cap.")
        await ctx.send(embed=e)

    @commands.hybrid_command(name="nhie", description="Never Have I Ever.")
    async def nhie(self, ctx):
        view = NHIEView()
        await ctx.send(embed=view.build_embed(), view=view)

    @commands.hybrid_command(name="topic", description="Random conversation starter.")
    async def topic(self, ctx):
        e = embed("💬  Conversation Starter", random.choice(TOPICS), C.TRIVIA)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="hug", description="Hug someone.")
    async def hug(self, ctx, member: discord.Member):
        e = embed("🤗  Hug", f"{ctx.author.mention} gave {member.mention} a big hug!", C.MARRIAGE,
                  footer=f"{ctx.author.display_name} → {member.display_name}")
        gif = await fetch_gif("anime hug")
        if gif:
            e.set_image(url=gif)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="pat", description="Pat someone on the head.")
    async def pat(self, ctx, member: discord.Member):
        e = embed("😊  Head Pat", f"{ctx.author.mention} patted {member.mention} on the head.", C.MARRIAGE,
                  footer=f"{ctx.author.display_name} → {member.display_name}")
        gif = await fetch_gif("anime head pat")
        if gif:
            e.set_image(url=gif)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="bonk", description="Bonk someone. Go to jail.")
    async def bonk(self, ctx, member: discord.Member):
        e = embed("🔨  BONK", f"{ctx.author.mention} bonked {member.mention}. Straight to jail.", C.LOSE,
                  footer=f"{ctx.author.display_name} → {member.display_name}")
        gif = await fetch_gif("anime bonk")
        if gif:
            e.set_image(url=gif)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="kill", description="Dramatically kill someone.")
    async def kill(self, ctx, member: discord.Member):
        methods = [
            f"dropped a piano on {member.mention}.",
            f"challenged {member.mention} to a dance-off and they died of embarrassment.",
            f"replaced {member.mention}'s keyboard with a waffle iron.",
            f"sent {member.mention} to Italy.",
            f"made {member.mention} read their own old Tweets.",
            f"exposed {member.mention}'s search history to the entire server.",
            f"forced {member.mention} to watch 12 hours of unskippable YouTube ads.",
        ]
        e = embed("💀  Murder", f"{ctx.author.mention} {random.choice(methods)}", C.LOSE,
                  footer=f"{ctx.author.display_name} → {member.display_name}")
        await ctx.send(embed=e)

    @commands.hybrid_command(name="confess", description="Send an anonymous confession.")
    async def confess(self, ctx, *, confession: str):
        CONFESSIONS_CHANNEL_ID = 1492170739955138630
        LOG_USER_ID = 734468552903360594

        try:
            await ctx.message.delete()
        except Exception:
            pass

        if not ctx.guild:
            return await ctx.send(embed=error("Confession", "This command can only be used in a server."))

        confessions_channel = ctx.guild.get_channel(CONFESSIONS_CHANNEL_ID)
        if confessions_channel is None:
            try:
                confessions_channel = await self.bot.fetch_channel(CONFESSIONS_CHANNEL_ID)
            except Exception:
                return await ctx.send(embed=error("Confession", "Confessions channel not found."))

        public_e = embed(
            "🤫  Anonymous Confession",
            confession,
            C.NEUTRAL,
            footer="Submitted anonymously"
        )

        try:
            await confessions_channel.send(embed=public_e)
        except Exception:
            return await ctx.send(embed=error("Confession", "I couldn't post to the confessions channel."))

        try:
            await ctx.author.send(
                embed=embed(
                    "✅  Confession Sent",
                    "Your confession was posted anonymously in the confessions channel.",
                    C.WIN
                )
            )
        except Exception:
            pass

        log_user = self.bot.get_user(LOG_USER_ID)
        if log_user is None:
            try:
                log_user = await self.bot.fetch_user(LOG_USER_ID)
            except Exception:
                log_user = None

        if log_user is not None:
            log_embed = embed(
                "🔍  Confession Log",
                f"**Confession:**\n{confession}\n\n"
                f"**Sender:** {ctx.author.mention} (`{ctx.author}` · ID `{ctx.author.id}`)\n"
                f"**Guild:** {ctx.guild.name} (`{ctx.guild.id}`)\n"
                f"**Used In:** {ctx.channel.mention} (`{ctx.channel.id}`)\n"
                f"**Posted To:** {confessions_channel.mention}",
                C.WARN,
                footer="Private confession log"
            )
            try:
                await log_user.send(embed=log_embed)
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
