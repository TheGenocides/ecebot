import discord
import os
import datetime
from googletrans import Translator
from dotenv import load_dotenv
from discord.ext import commands

# Load the .env file, you need to make a .env file with the TOKEN variable 
load_dotenv()

os.environ["JISHAKU_NO_UNDERSCORE"] = "true"
os.environ["JISHAKU_RETAIN"] = "true"

bot = commands.Bot(command_prefix="ec!", intents=discord.Intents.all())
translator = Translator()

@bot.event
async def on_ready():
    await bot.load_extension("jishaku")
    print("Jishaku loaded!")
    print(f"Logged in as {bot.user}")

@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! ```{bot.latency *  1000:.2f}ms```")

@bot.command(aliases=["trans", "tl"])
async def translate(ctx, *, text = None):
    msg = await ctx.reply("Translating....")
    text = text if text else ((await ctx.channel.fetch_message(ctx.message.reference.message_id)).content)
    source = "en" if translator.detect(text).lang == "en" else "id"
    translated_to = "en" if source == "id" else "id"
    translated_text = translator.translate(text, src=source, dest = translated_to).text
    embed = discord.Embed(
        title=f"{source} -> {translated_to}",
        description=translated_text,
        colour=discord.Color.blurple(),
        timestamp=datetime.datetime.now()
    )
    await msg.edit(content="", embed=embed)

bot.run(os.getenv("TOKEN"))
