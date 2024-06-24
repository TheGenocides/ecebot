import discord
import os
from googletrans import Translator
from dotenv import load_dotenv
from discord.ext import commands

load_dotenv()

bot = commands.Bot(command_prefix="ec!", intents=discord.Intents.all())
translator = Translator()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! ```{bot.latency *  1000:.2f}ms```")

@bot.command(aliases=["trans", "tl"])
async def translate(ctx, *, text = None):
    if not text:
        text = (await ctx.channel.fetch_message(ctx.message.reference.message_id)).content
    source = translator.detect(text).lang
    translated_to = "en" if source == "id" else "id"
    translated_text = translator.translate(text, src=source, dest = translated_to).text
    await ctx.reply(translated_text)

bot.run(os.getenv("TOKEN"))
