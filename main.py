import discord
import os
import datetime
import asyncio
import random
import sys
import wmi

from discord.ext import commands
from googletrans import Translator
from dotenv import load_dotenv
from models.db import BorrowingRecordDB, BookDB, Status, AsyncSessionLocal, engine, Base
from models import (
    Book,
    BookshelfDropdownView,
    AgreementView,
    BorrowingDropdownView,
    BorrowingForm,
    MESSAGE_SPLASH,
)
from utils import (
    TIMEFORMAT,
    EC_SERVER_ID,
    RECORD_CHANNEL_ID,
    LIBRARIAN_ROLE,
    PATRON_ROLE,
    EXTENTIONS,
    build_receipt_image,
    build_renewed_receipt_image,
    build_returned_receipt_image,
    embed_title_parse,
    get_records_stats,
)

# Load the .env file, you need to make a .env file with the TOKEN variable
load_dotenv()

bot = commands.Bot(command_prefix="ec!", intents=discord.Intents.all())
records: list[discord.Embed] = []
books : list[Book] = []
patron_role: discord.Role = None
librarian_role: discord.Role = None
record_channel: discord.TextChannel = None
translator = Translator()

w = wmi.WMI(namespace=r"root\OpenHardwareMonitor")

DEBUGING = False

# @bot.event
# async def on_message(message: discord.Message):
#     if message.channel == record_channel and message.embeds:
#         records.append(message.embeds[0])
#     else:
#         await bot.invoke(await bot.get_context(message))

@bot.event
async def on_ready():
    global patron_role, librarian_role, records, record_channel

    patron_role = bot.get_guild(EC_SERVER_ID).get_role(PATRON_ROLE)
    librarian_role = bot.get_guild(EC_SERVER_ID).get_role(LIBRARIAN_ROLE)
    record_channel = bot.get_channel(RECORD_CHANNEL_ID)
    # records = [msg.embeds[0] async for msg in (record_channel).history()]

    for ext in EXTENTIONS:
        if f"cogs.{ext}" not in bot.extensions:
            await bot.load_extension(ext)
            print(f"The cog '{ext}' is loaded.")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("Successfuly fetched books!")
    print(librarian_role)
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
    
@bot.command(aliases=["temp"])
async def temperature(ctx):
    sensors = w.Sensor()
    sensors = sorted([sensor for sensor in sensors if sensor.SensorType in ["Temperature", "Fan"]], key=lambda sensor: sensor.name)

    final = []
    seen = set()
    txt = ""
    for sensor in sensors:
        key = sensor.name
        if key not in seen:
            seen.add(key)
            final.append(sensor)

    
    for sensor in final:
        txt += f"**{sensor.name}:**\n"
        txt += f"-# {sensor.SensorType}: **{sensor.Value}**{"c°" if sensor.SensorType == "Temperature" else " RPM"}\n\n"
            
    await ctx.send(txt)
    await ctx.send("""CPU Core	Internal CPU diode	CPU (not Nuvoton)
Temperature #1	Motherboard (chipset area)	Nuvoton NCT6776F
Temperature #2	VRM (power delivery)	Nuvoton NCT6776F
Temperature #3	GPU/PCIe/ambient area	Nuvoton NCT6776F\n\nCPU Core 1	Temperature sensor inside core #1	Individual sensor for that core
CPU Core 2	Temperature sensor inside core #2	i3-3220 is dual-core
CPU Core	May be an average or a copy of Core 1 (tool-dependent)	Sometimes redundant
CPU Package	Temperature of the entire CPU die (package)	Most accurate for CPU health/throttle""")

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

    async with AsyncSessionLocal() as session:
        books: Book = await BookDB.get_all(session, True)
        await ctx.send(
            file=discord.File("images/EC.jpeg"),
            embed=em,
            view=BookshelfDropdownView(em, books, ctx.author),
        )

@bot.command(aliases=["bor", "minjem", "minjam"])
@commands.cooldown(1, 60, commands.BucketType.default)
async def borrow(ctx: commands.Context):
    has_role = patron_role in ctx.author.roles
    channel = record_channel
    check_author = lambda inter: inter.user == ctx.author
    modal_check = (
        lambda inter: inter.type == discord.InteractionType.modal_submit
        and check_author(inter)
    )
    msg: discord.Message = None
    step = 1
    last_step = 3

    async with AsyncSessionLocal() as session:
        if (await BorrowingRecordDB.user_is_borrowing(session, ctx.author.id)):
            return await ctx.send("You can only borrow one book at a time!")
    
        allowed_books = await BookDB.get_allowed_books(session, True)

        if not has_role:
            with open("policy.txt", "rb") as f:
                file = discord.File(f)

            msg: discord.Message = await ctx.send(
                f"**`[{step}/{last_step}]`** Let's get started!\nOur policy helps to ensure qualities of our services to patrons. Please confirm our attached policy by pressing the green button bellow!",
                file=file,
                view=AgreementView(ctx.author),
            )
            step += 1
            await asyncio.sleep(1)

            inter: discord.Interaction = await bot.wait_for("interaction", check=check_author)
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

        inter: discord.Interaction = await bot.wait_for("interaction", check=check_author)
        selected_book_isbn = inter.data["values"][0]
        book = await BookDB.get_by_id(session, selected_book_isbn, True)
        
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
        await inter.response.send_message("Please wait for the librarian's approvel", ephemeral=True)

        latest_record = await BorrowingRecordDB.get_latest(session)

        file = discord.File(
            build_receipt_image(
                book, name, latest_record.id + 1, renewed_date.strftime("%d/%m" if sys.platform == "win32" else "%d/%-m")
            ),
            "receipt.png",
        )

        em = (
            discord.Embed(
                title=name,
                description=f"**{ctx.author.mention}** has borrowed a book!\n\n{name} • {phone_number}",
                color=discord.Color.yellow(),
                timestamp=datetime.datetime.now(),
            )
            .set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url)
            .set_footer(text="Borrowed")
            .set_image(url="attachment://receipt.png")
            .set_thumbnail(url=book.get_cover_url("large"))
        )
        channel_msg = await channel.send(librarian_role.mention, embed=em, file=file, view=AgreementView(ctx.author))
  
        inter: discord.Interaction = await bot.wait_for(
            "interaction", 
            check=lambda inter: inter.message == channel_msg and librarian_role in inter.user.roles
        )
       
        await channel_msg.edit(content="", view=None)
        
        if not inter.data.get("custom_id") == "agree":
            return await msg.edit(
            content=f"**`Denied`**\nI am so sorry {ctx.author.mention}\nI cannot approve your request, try asking our committe team for the full response!"
        )
        
        await BookDB.borrow(session, book.isbn)
        new_record: BorrowingRecordDB = await BorrowingRecordDB.create(
            session,
            int(ctx.author.id),
            book.isbn,
            f"{name}:{phone_number}"
        )

        if not has_role:
            await ctx.author.add_roles(
                patron_role, reason="Borrowed their first ever book from the library!"
            )

        await ctx.author.send(
            embed=em,
            file = discord.File(
                build_receipt_image(
                    book, name, new_record.id, renewed_date.strftime(TIMEFORMAT)
                ),
                "receipt.png",
            ),
        )

        await msg.edit(
            content=f"**`[{step}/{last_step}, Approved]`** Done! `(,,> ᴗ <,,)`\nI've sent a copy of the receipt to your DM, show us your receipt in our library after school."
        )


@bot.command()
@commands.has_role(LIBRARIAN_ROLE)
async def renew(ctx: commands.Context, patron: discord.Member):
    async with AsyncSessionLocal() as session:
        record = (await BorrowingRecordDB.get_all_by_patron(session, patron.id))[0]
        if not records or not record.status == Status.BORROWED:
            return await ctx.send("You have not borrowed any book!")
        
        book = await BookDB.get_by_id(session, record.book_isbn, True)
        name, phone_number = record.remarks.split(":")
        file = discord.File(
            build_renewed_receipt_image(
                book,
                patron,
                record.id,
                (datetime.datetime.now() + datetime.timedelta(days=7)).strftime(TIMEFORMAT),
            ),
            "renewed.png",
        )
        em = (
            discord.Embed(
                title=name,
                description=f"**{ctx.author.mention}** has renewed a book!\n\n{name} • {phone_number}",
                color=discord.Color.yellow(),
                timestamp=record.borrow_date,
            )
            .set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url)
            .set_footer(text="Renewed by")
            .set_image(url="attachment://renewed.png")
            .set_thumbnail(url=book.get_cover_url("large"))
        )
        await (record_channel).send(embed=em, file=file)
        await ctx.send("`٩(>ᴗ<)و` I renewed your book!\nPlease come to the library to confirm your renewal after school and bring **the book**.\nThank you!")

        await BorrowingRecordDB.renew(session, record.id)
        await ctx.send("OK")

    

    # receipt = None
    # book = None
    # patron = None
    # embed: discord.Embed = None

    # for embed in records:
    #     isbn, receipt_number, user_id = embed_title_parse(embed.title)
    #     if ctx.author.id == int(user_id):
    #         if embed.footer.text.lower() == "returned":
    #             break
    #         book = Book.from_books(isbn, books)
    #         receipt = receipt_number
    #         patron = (embed.description.split("\n\n")[1]).split(" •")[0]
    #         day = embed.timestamp.day 
            
    #         if day < (day + 3):
    #             return await ctx.send(f"Sorry there! You cannot renew your book until: <t:{round((embed.timestamp + datetime.timedelta(3)).timestamp())}:D>")
            
    # if not any([receipt, book, patron]):
    #     return await ctx.send(
    #         "Hmm sorry, but you haven't borrowed any book before :/\nBorrow one with the command `ec!borrow`!"
    #     )
    
    # file = discord.File(
    #     build_renewed_receipt_image(
    #         book,
    #         patron,
    #         receipt,
    #         (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%d/%-m"),
    #     ),
    #     "renewed.png",
    # )
    # em = (
    #     discord.Embed(
    #         title=embed.title,
    #         description=embed.description.replace("borrowed", "renewed"),
    #         color=discord.Color.yellow(),
    #         timestamp=datetime.datetime.now(),
    #     )
    #     .set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url)
    #     .set_footer(text="Renewed")
    #     .set_image(url="attachment://renewed.png")
    #     .set_thumbnail(url=book.get_cover_url("large"))
    # )
    # await (record_channel).send(embed=em, file=file)
    # await ctx.send("`٩(>ᴗ<)و` I renewed your book!\nPlease come to the library to confirm your renewal after school and bring **the book**.\nThank you!")


@bot.command(name="return")
@commands.has_role(LIBRARIAN_ROLE)
async def _return(ctx: commands.Context, patron: discord.Member): #What if the user does not go to the library for returning the book.
    async with AsyncSessionLocal() as session:
        record = (await BorrowingRecordDB.get_all_by_patron(session, patron.id))[0]
        if not records or not record.status == Status.BORROWED:
            await ctx.send("You have not borrowed any book!")
        await ctx.send("OK")
        
    # receipt = None
    # book = None
    # patron = None
    # for embed in records:
    #     isbn, receipt_number, user_id = embed_title_parse(embed.title)
    #     if ctx.author.id == int(user_id):
    #         if embed.footer.text.lower() == "returned":
    #             break

    #         book = Book.from_books(isbn, books)
    #         receipt = receipt_number
    #         patron = (embed.description.split("\n\n")[1]).split(" •")[0]
    #         day = embed.timestamp.day

    #         if day < (day + 3):
    #             return await ctx.send(f"Sorry there! You cannot return your book until: <t:{round((embed.timestamp + datetime.timedelta(3)).timestamp())}:D>")

    # if not any([receipt, book, patron]):
    #     return await ctx.send(
    #         "Hmm sorry, but you haven't borrowed any book before :/\nBorrow one with the command `ec!borrow`!"
    #     )
    
    # receipt_number, available_book_isbns, borrowed_book_isbns, _ = get_records_stats(
    #     record_channel.topic
    # )
    # channel = record_channel
    # available_book_isbns.append(isbn)
    # borrowed_book_isbns.remove(isbn)
    # await channel.edit(
    #     topic=f"Total Records: {receipt_number}\n\nAvailable: {(', '.join([isbn for isbn in available_book_isbns])).rstrip(', ')}\n\nBorrowed: {', '.join(borrowed_book_isbns) if borrowed_book_isbns else ''}"
    # )

    # file = discord.File(
    #     build_returned_receipt_image(
    #         book,
    #         patron,
    #         receipt
    #     ),
    #     "returned.png",
    # )
    # em = (
    #     discord.Embed(
    #         title=embed.title,
    #         description=embed.description.replace("borrowed", "returned").replace("renewed", "returned"),
    #         color=discord.Color.yellow(),
    #         timestamp=datetime.datetime.now(),
    #     )
    #     .set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url)
    #     .set_footer(text="Returned")
    #     .set_image(url="attachment://returned.png")
    #     .set_thumbnail(url=book.get_cover_url("large"))
    # )

    # await channel.send(embed=em, file=file)
    # await ctx.send("`(,,⟡o⟡,,)` _`Woah!`_ Finished? already?! `( ˶° ᗜ°)!!`\nThat was fast! I hope you like the book!\nPlease come and return the book at the library after school!")

os.environ["JISHAKU_NO_UNDERSCORE"] = "true"
os.environ["JISHAKU_RETAIN"] = "true"

bot.run(os.environ["TOKEN"])