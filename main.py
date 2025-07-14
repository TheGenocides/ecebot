import discord
import os
import datetime
import asyncio
import json
import random
import aiohttp
import sys

from discord.ext import commands
from googletrans import Translator
from dotenv import load_dotenv
from sqlalchemy import select
from db import AsyncSessionLocal, BookDB
from models import (
    EMOJIES,
    MESSAGE_SPLASH,
    API_URL,
    BookshelfDropdownView,
    Book,
    PolicyAgreementView,
    BorrowingDropdownView,
    BorrowingForm,
)
from utils import (
    EC_SERVER_ID,
    PATRON_ROLE,
    RECORD_CHANNEL_ID,
    build_receipt_image,
    build_renewed_receipt_image,
    build_returned_receipt_image,
    embed_title_parse,
    get_records_stats,
    is_book_available,
)

# Load the .env file, you need to make a .env file with the TOKEN variable
load_dotenv()

bot = commands.Bot(command_prefix="ec!", intents=discord.Intents.all())
books: list[Book] = []
records: list[discord.Embed] = []
patron_role: discord.Role = None
translator = Translator()

DEBUGING = False

def get_record_channel():
    return bot.get_channel(RECORD_CHANNEL_ID)

@bot.event
async def on_message(message: discord.Message):
    if message.channel == get_record_channel() and message.embeds:
        records.append(message.embeds[0])
    else:
        await bot.invoke(await bot.get_context(message))

@bot.event
async def on_ready():
    global patron_role, records

    await bot.load_extension("jishaku")
    print("Jishaku loaded!")
    # if not DEBUGING:
    #     async with aiohttp.ClientSession() as session:
    #         async with session.get(
    #             API_URL,
    #             headers={
    #                 "User-Agent": f"BookClubDigitalLibrary/1.0 ({os.environ['MY_EMAIL']})"
    #             },
    #         ) as response:

    #             print("Status:", response.status)
    #             data = await response.json()
    #             with open("a.json", "w", encoding="utf-8") as f:
    #                 json.dump(data, f, ensure_ascii=False, indent=4)
    #             for kv, emoji in zip(data.items(), EMOJIES):
    #                 for _, x in kv[1]["records"].items():
    #                     books.append(Book(x["data"], x["details"]["details"], emoji=emoji))

    # else:
    #     with open("a.json", "r") as f:
    #         payload = (json.load(f))["payload"]

    #     for book in payload:
    #         books.append(Book(book["data"], book["details"]["details"]))
    
    # async with AsyncSessionLocal() as session:
    #     result = await session.execute(
    #         Book.__table__.select()
    #     )
    #     results = result.fetchall()
    #     for book in results:
    #         books.append(Book())


    # patron_role = bot.get_guild(EC_SERVER_ID).get_role(PATRON_ROLE)
    # records = [msg.embeds[0] async for msg in (get_record_channel()).history()]
        
    
    # async with AsyncSessionLocal() as session:
    #     async with session.begin():
    #         for book in books:
    #             session.add(
    #                 BookDB(
    #                     identifiers=json.dumps(book.identifiers),
    #                     url=book.url,
    #                     emoji=book.emoji,
    #                     publish_date=book.published,
    #                     title=book.title,
    #                     details=json.dumps(book.details), #Change to string
    #                     publishers=json.dumps(book.publishers),
    #                     authors=json.dumps(book.authors),
    #                     cover=json.dumps(book.get_cover_url("small"))
    #                 )
    #             )

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(BookDB))
        results = result.scalars().all()
        for result in results:
            books.append(Book(result))

    print(books)
    print("Successfuly fetched books!")
    print(f"Logged in as {bot.user}")


@bot.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.CommandOnCooldown):
        if await bot.is_owner(ctx.author):
            await ctx.reinvoke() # Bypass cooldown by reinvoking the command
        else:
            await ctx.send(
                f"Hold on there! Someone is using this command\nPlease wait in line for <t:{round(datetime.datetime.now().timestamp()) + error.retry_after:.1f}:R>",
                delete_after=5,
            )
    else:
        await ctx.send(f"Error: {error}")
        raise error

@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! ```{bot.latency *  1000:.2f}ms```")

@bot.command(aliases=["trans", "tl"])
async def translate(ctx: commands.Context, *, text=None):
    text = (
        text or (
            (await ctx.channel.fetch_message(ctx.message.reference.message_id)).content
        )
    )
    source = "en" if translator.detect(text).lang == "en" else "id"
    translated_to = "en" if source == "id" else "id"
    translated_text = translator.translate(text, src=source, dest=translated_to).text
    embed = discord.Embed(
        title=f"{source} -> {translated_to}",
        description=translated_text,
        colour=discord.Color.blurple(),
        timestamp=datetime.datetime.now(),
    )
    await ctx.reply(embed=embed)


@bot.command(aliases=["lib", "perpustakaan", "perpus"])
async def library(ctx):
    em = (
        discord.Embed(
            title="English Club Library",
            description="""Howdy Guyziee :wave: This is our shared book collections. 
        You can borrow our books by registering using the command :
        ```
        ec!borrow
        ```
        """,
            url="http://discord.com",
            color=discord.Color.blurple(),
        )
        .add_field(name="Not selected", value="Please select a book from the dropdown")
        .set_author(
            name="English Club Committee Board", icon_url="attachment://EC.jpeg"
        )
        .set_image(url="attachment://output.png")
    )

    await ctx.send(
        file=discord.File("images/EC.jpeg"),
        embed=em,
        view=BookshelfDropdownView(em, books, ctx.author),
    )

@bot.command(aliases=["bor", "minjem", "minjam"])
@commands.cooldown(1, 60, commands.BucketType.default)
async def borrow(ctx: commands.Context):
    has_role = patron_role in ctx.author.roles
    check = lambda inter: inter.user == ctx.author
    modal_check = (
        lambda inter: inter.type == discord.InteractionType.modal_submit
        and check(inter)
    )
    msg: discord.Message = None
    step = 1
    last_step = 3
    
    for embed in records:
        _, _, user_id = embed_title_parse(embed.title)
        if ctx.author.id == int(user_id) and embed.footer.text.lower() in ["borrowed", "renewed"]:
            return await ctx.send("Sorry you can only borrow 1 book at the time...")

    channel = get_record_channel()
    allowed_books = [book for book in books if is_book_available(book, channel.topic)]
    print(allowed_books)
    if not has_role:
        with open("policy.txt", "rb") as f:
            file = discord.File(f)

        msg: discord.Message = await ctx.send(
            f"**`[{step}/{last_step}]`** Let's get started!\nOur policy helped to ensure qualities of our services to patrons. Please confirm our attached policy by pressing the green button bellow!",
            file=file,
            view=PolicyAgreementView(ctx.author),
        )
        step += 1
        await asyncio.sleep(1)

        inter: discord.Interaction = await bot.wait_for("interaction", check=check)
        if not (inter.data["id"] == 2):
            return

        await inter.response.edit_message(
            content=f"**`[{step}/{last_step}]`** Thanks for agreeing to our policy\nYou may choose one book of your liking through the dropdown bellow.",
            attachments=[],
            view=BorrowingDropdownView(msg, allowed_books, ctx.author),
        )
        step += 1

    else:
        last_step = 2
        msg = await ctx.send(
            content=f"**`[{step}/{last_step}]`** Howdy Patron!\nYou may choose one book of your liking through the dropdown bellow.",
            view=BorrowingDropdownView(msg, allowed_books, ctx.author),
        )
        step += 1

    inter: discord.Interaction = await bot.wait_for("interaction", check=check)
    selected_book = inter.data["values"][0]
    book = [book for book in books if book.identifiers.isbn_13[0] == selected_book][0]
    book_isbn = book.identifiers.isbn_13[0]   
    
    await msg.edit(
        content=f"**`[{step}/{last_step}]`** `⸜(｡˃ ᵕ ˂ )⸝♡` Almost there!\nYou just need to enter information through this form.",
        attachments=[],
        view=None,
    )
    await ctx.reply(
        f"`( ╹ -╹)? Hmm?` *{book.full_title}*? " + random.choice(MESSAGE_SPLASH),
        ephemeral=True,
    )
    await inter.response.send_modal(BorrowingForm(timeout=120, selected_book=book))

    inter: discord.Interaction = await bot.wait_for("interaction", check=modal_check)
    name = inter.data["components"][0]["components"][0]["value"]
    phone_number = inter.data["components"][1]["components"][0]["value"]
    renewed_date = datetime.datetime.now() + datetime.timedelta(days=7)
    await inter.response.send_message("Done! Enjoy your book", ephemeral=True)
    await msg.edit(
        content=f"**`[{step}/{last_step}]`** Done! `(,,> ᴗ <,,)`\nI've sent a copy of the receipt to your DM, show us your receipt in our library after school."
    )

    receipt_number, available_book_isbns, borrowed_book_isbns, _ = get_records_stats(
        channel.topic
    )
    
    receipt_number += 1 
    receipt_number = str(receipt_number)
    available_book_isbns.remove(book_isbn)
    borrowed_book_isbns.append(book_isbn)
    await channel.edit(
        topic=f"Total Records: {receipt_number}\n\nAvailable: {(', '.join([isbn for isbn in available_book_isbns])).rstrip(', ')}\n\nBorrowed: {', '.join(borrowed_book_isbns) if borrowed_book_isbns else ''}"
    )

    file = discord.File(
        build_receipt_image(
            book, name, receipt_number, renewed_date.strftime("%d/%m" if sys.platform == "win32" else "%d/%-m")
        ),
        "receipt.png",
    )

    em = (
        discord.Embed(
            title=book_isbn + receipt_number + str(ctx.author.id),
            description=f"**{ctx.author.mention}** has borrowed a book!\n\n{name} • {phone_number}",
            color=discord.Color.yellow(),
            timestamp=datetime.datetime.now(),
        )
        .set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url)
        .set_footer(text="Borrowed")
        .set_image(url="attachment://receipt.png")
        .set_thumbnail(url=book.get_cover_url("large"))
    )
    await channel.send(embed=em, file=file)
    if not has_role:
        await ctx.author.add_roles(
            patron_role, reason="Borrowed their first ever book from the library!"
        )
    await ctx.author.send(
        embed=em,
        file=discord.File(
            build_receipt_image(
                book, name, receipt_number, renewed_date.strftime("%d/%-m")
            ),
            "receipt.png",
        ),
    )

@bot.command()
async def renew(ctx: commands.Context): #What if the user does not go to the library for the weekly book checkup
    receipt = None
    book = None
    patron = None
    embed: discord.Embed = None

    for embed in records:
        isbn, receipt_number, user_id = embed_title_parse(embed.title)
        if ctx.author.id == int(user_id):
            if embed.footer.text.lower() == "returned":
                break
            book = Book.from_books(isbn, books)
            receipt = receipt_number
            patron = (embed.description.split("\n\n")[1]).split(" •")[0]
            day = embed.timestamp.day 
            
            if day < (day + 3):
                return await ctx.send(f"Sorry there! You cannot renew your book until: <t:{round((embed.timestamp + datetime.timedelta(3)).timestamp())}:D>")
            
    if not any([receipt, book, patron]):
        return await ctx.send(
            "Hmm sorry, but you haven't borrowed any book before :/\nBorrow one with the command `ec!borrow`!"
        )
    
    file = discord.File(
        build_renewed_receipt_image(
            book,
            patron,
            receipt,
            (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%d/%-m"),
        ),
        "renewed.png",
    )
    em = (
        discord.Embed(
            title=embed.title,
            description=embed.description.replace("borrowed", "renewed"),
            color=discord.Color.yellow(),
            timestamp=datetime.datetime.now(),
        )
        .set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url)
        .set_footer(text="Renewed")
        .set_image(url="attachment://renewed.png")
        .set_thumbnail(url=book.get_cover_url("large"))
    )
    await (get_record_channel()).send(embed=em, file=file)
    await ctx.send("`٩(>ᴗ<)و` I renewed your book!\nPlease come to the library to confirm your renewal after school and bring **the book**.\nThank you!")


@bot.command(name="return")
async def _return(ctx: commands.Context): #What if the user does not go to the library for returning the book.
    receipt = None
    book = None
    patron = None
    for embed in records:
        isbn, receipt_number, user_id = embed_title_parse(embed.title)
        if ctx.author.id == int(user_id):
            if embed.footer.text.lower() == "returned":
                break

            book = Book.from_books(isbn, books)
            receipt = receipt_number
            patron = (embed.description.split("\n\n")[1]).split(" •")[0]
            day = embed.timestamp.day

            if day < (day + 3):
                return await ctx.send(f"Sorry there! You cannot return your book until: <t:{round((embed.timestamp + datetime.timedelta(3)).timestamp())}:D>")

    if not any([receipt, book, patron]):
        return await ctx.send(
            "Hmm sorry, but you haven't borrowed any book before :/\nBorrow one with the command `ec!borrow`!"
        )
    
    receipt_number, available_book_isbns, borrowed_book_isbns, _ = get_records_stats(
        get_record_channel().topic
    )
    channel = get_record_channel()
    available_book_isbns.append(isbn)
    borrowed_book_isbns.remove(isbn)
    await channel.edit(
        topic=f"Total Records: {receipt_number}\n\nAvailable: {(', '.join([isbn for isbn in available_book_isbns])).rstrip(', ')}\n\nBorrowed: {', '.join(borrowed_book_isbns) if borrowed_book_isbns else ''}"
    )

    file = discord.File(
        build_returned_receipt_image(
            book,
            patron,
            receipt
        ),
        "returned.png",
    )
    em = (
        discord.Embed(
            title=embed.title,
            description=embed.description.replace("borrowed", "returned").replace("renewed", "returned"),
            color=discord.Color.yellow(),
            timestamp=datetime.datetime.now(),
        )
        .set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url)
        .set_footer(text="Returned")
        .set_image(url="attachment://returned.png")
        .set_thumbnail(url=book.get_cover_url("large"))
    )

    await channel.send(embed=em, file=file)
    await ctx.send("`(,,⟡o⟡,,)` _`Woah!`_ Finished? already?! `( ˶° ᗜ°)!!`\nThat was fast! I hope you like the book!\nPlease come and return the book at the library after school!")

os.environ["JISHAKU_NO_UNDERSCORE"] = "true"
os.environ["JISHAKU_RETAIN"] = "true"

bot.run(os.environ["TOKEN"])