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
from models.db import BorrowingRecordDB, BookDB, BorrowingStatus, AsyncSessionLocal, engine, Base
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
    BOT_CHANNEL_ID,
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
bot_channel: discord.TextChannel = None
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
    global patron_role, librarian_role, records, record_channel, bot_channel

    patron_role = bot.get_guild(EC_SERVER_ID).get_role(PATRON_ROLE)
    librarian_role = bot.get_guild(EC_SERVER_ID).get_role(LIBRARIAN_ROLE)
    record_channel = bot.get_channel(RECORD_CHANNEL_ID)
    bot_channel = bot.get_channel(BOT_CHANNEL_ID)
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
        
        await inter.response.send_modal(BorrowingForm(timeout=120, selected_book=book))

        inter: discord.Interaction = await bot.wait_for("interaction", check=modal_check)
        name = inter.data["components"][0]["components"][0]["value"]
        phone_number = inter.data["components"][1]["components"][0]["value"]
        renewed_date = datetime.datetime.now() + datetime.timedelta(days=7)
        await inter.response.send_message(f"`( ╹ -╹)? Hmm?` *{book.full_title}*? " + random.choice(MESSAGE_SPLASH), ephemeral=True)

        latest_record = await BorrowingRecordDB.get_latest(session)

        file = discord.File(
            build_receipt_image(
                book, name, (latest_record.id if latest_record else 0) + 1, renewed_date.strftime(TIMEFORMAT)
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

        await BookDB.borrow(session, book.isbn)
        await BorrowingRecordDB.create(
            session,
            int(ctx.author.id),
            book.isbn,
            f"{name}:{phone_number}"
        )

        await channel.send(librarian_role.mention, embed=em, file=file)
        await msg.edit(
            content=f"**`[{step}/{last_step}, Pending]`** Done! `(,,> ᴗ <,,)`\nYour request is being validated by us.\n**We will notify you shortly via DM**"
        )
       

@bot.command(aliases=["acc", "ac"])
@commands.has_role(LIBRARIAN_ROLE)
@commands.cooldown(1, 60, commands.BucketType.default)
async def accept(ctx: commands.Context, receipt_id: int):
    await ctx.send(f"Approving **{receipt_id}**? \n**(yes, no)**")
    msg = await bot.wait_for("message", check=lambda msg: msg.content.lower() in ["yes", "no"] and msg.channel == ctx.channel and msg.author == ctx.author)
    async with AsyncSessionLocal() as session:
        record = await BorrowingRecordDB.get_by_id(session, receipt_id)
        book = await BookDB.get_by_id(session, record.book_isbn, True)
        name, phone_number = record.remarks.split(":")
        
        if not record or not record.status == BorrowingStatus.PENDING:
            return await ctx.send("Record does not exist or cannot be approved!")
        
        file = discord.File(
            build_receipt_image(
                book, name, record.id, record.due_date.strftime(TIMEFORMAT)
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
        
        match msg.content:
            case "yes":
                await (bot.get_guild(EC_SERVER_ID).get_member(record.user_id)).send(f"Hi! We have approved your request\n**Please come to Language Room (Ruang Bahasa) afterschool!**", embed=em, file=file)
                await BorrowingRecordDB.approve_record_by_id(session, receipt_id)
                return await ctx.send(f"Approved **{receipt_id}**!")
            case "no":
                return await ctx.send("Aborting...")
            
@bot.command(aliases=["den"])
@commands.has_role(LIBRARIAN_ROLE)
@commands.cooldown(1, 60, commands.BucketType.default)
async def denied(ctx: commands.Context, receipt_id: int):
    await ctx.send(f"Denying **{receipt_id}**? \n**(yes, no)**")
    msg = await bot.wait_for("message", check=lambda msg: msg.content.lower() in ["yes", "no"] and msg.channel == ctx.channel and msg.author == ctx.author)

    async with AsyncSessionLocal() as session:
        record = await BorrowingRecordDB.get_by_id(session, receipt_id)

        if not record or not record.status == BorrowingStatus.PENDING:
            return await ctx.send("Record does not exist or cannot be denied!")
        
        match msg.content:
            case "yes":
                try:
                    dm = await (bot.get_guild(EC_SERVER_ID).get_member(record.user_id)).create_dm()
                except discord.Forbidden:
                    await bot_channel.send(f"{ctx.author.mention} Your request has been approved! (I cannot send your a dm)\n**Please come to **Ruang Bahasa** afterschool!")
                else:
                    await dm.send("Your request has been denied: Please contact the @librarian or open a ticker for more information!")
                await (bot.get_guild(EC_SERVER_ID).get_member(record.user_id)).send("")
                await BookDB.borrow(session, record.book_isbn, True)
                await BorrowingRecordDB.disapprove_record_by_id(session, int(receipt_id))
                return await ctx.send(f"Denied **{receipt_id}**!")
    
            case "no":
                return await ctx.send("Aborting...")


@bot.command()
@commands.has_role(LIBRARIAN_ROLE)
async def renew(ctx: commands.Context, patron: discord.Member):
    await ctx.send(f"Renewing for **{patron.mention}**? \n**(yes, no)**")
    msg = await bot.wait_for("message", check=lambda msg: msg.content.lower() in ["yes", "no"] and msg.channel == ctx.channel and msg.author == ctx.author)

    match msg.content:
        case "yes":
            pass
        case "no":
            return await ctx.send("Aborting...")
        
    async with AsyncSessionLocal() as session:
        record = (await BorrowingRecordDB.get_all_by_patron(session, patron.id))[0]
    
        if not record.status == BorrowingStatus.BORROWING:
            return await ctx.send("They have not borrowed any book!")
        
        await BorrowingRecordDB.renew(session, record.id)

        book = await BookDB.get_by_id(session, record.book_isbn, True)
        name, phone_number = record.remarks.split(":")
        file = discord.File(
            build_renewed_receipt_image(
                book,
                name,
                record.id,
                (record.due_date).strftime(TIMEFORMAT),
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
            .set_author(name=patron.name, icon_url=patron.avatar.url)
            .set_footer(text=f"Returned by {ctx.author.name}", icon_url=ctx.author.avatar.url)
            .set_image(url="attachment://renewed.png")
            .set_thumbnail(url=book.get_cover_url("large"))
        )
        await (record_channel).send(embed=em, file=file)
        await ctx.send(f"`٩(>ᴗ<)و` I renewed your book!\n{patron.mention} Please come to **Language Room** to confirm your renewal after school and bring **the book**.\nThank you!")

        file = discord.File(
            build_renewed_receipt_image(
                book,
                name,
                record.id,
                (record.due_date).strftime(TIMEFORMAT),
            ),
            "renewed.png",
        )

        await patron.send(embed=em, file=file)


@bot.command(name="return")
@commands.has_role(LIBRARIAN_ROLE)
async def _return(ctx: commands.Context, patron: discord.Member): #What if the user does not go to the library for returning the book.
    await ctx.send(f"Are they **{patron.mention}** done with the book? \n**(yes, no)**")
    msg = await bot.wait_for("message", check=lambda msg: msg.content.lower() in ["yes", "no"] and msg.channel == ctx.channel and msg.author == ctx.author)

    match msg.content:
        case "yes":
            pass
        case "no":
            return await ctx.send("Aborting.================================..")
        
    async with AsyncSessionLocal() as session:
        record = (await BorrowingRecordDB.get_all_by_patron(session, patron.id))[0]
    
        if not record.status == BorrowingStatus.BORROWING:
            return await ctx.send("They have not borrowed any book!")
        
        book = await BookDB.get_by_id(session, record.book_isbn, True)
        await BorrowingRecordDB.finish(session, record.id)
        await BookDB.borrow(session, book.isbn, True)
        name, phone_number = record.remarks.split(":")
        file = discord.File(
            build_returned_receipt_image(
                book,
                name,
                record.id
            ),
            "returned.png",
        )
        em = (
            discord.Embed(
                title=name,
                description=f"**{ctx.author.mention}** has returned a book!\n\n{name} • {phone_number}",
                color=discord.Color.yellow(),
                timestamp=record.borrow_date,
            )
            .set_author(name=patron.name, icon_url=patron.avatar.url)
            .set_footer(text=f"Returned by {ctx.author.name}", icon_url=ctx.author.avatar.url)
            .set_image(url="attachment://returned.png")
            .set_thumbnail(url=book.get_cover_url("large"))
        )
        await (record_channel).send(embed=em, file=file)
        await ctx.send(f"`(,,⟡o⟡,,)` _`Woah!`_ Finished? already?! `( ˶° ᗜ°)!!`\nThat was fast! I hope you like the book!\n{patron.mention} Please come and return the book at the library after school!")

        file = discord.File(
            build_returned_receipt_image(
                book,
                name,
                record.id
            ),
            "returned.png",
        )

        await patron.send(embed=em, file=file)

os.environ["JISHAKU_NO_UNDERSCORE"] = "true"
os.environ["JISHAKU_RETAIN"] = "true"

bot.run(os.environ["TOKEN"])