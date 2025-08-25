import datetime
import os
import sys

from discord.ext import commands
from io import BytesIO
from PIL import Image, ImageFont, ImageDraw
from dotenv import load_dotenv
from models.book import Book

YELLOW = (255, 189, 89)
COBALT = (0, 63, 148)
LETTER_SPACING = 7

load_dotenv()

EC_SERVER_ID = int(os.environ["EC_SERVER_ID"])
PATRON_ROLE = int(os.environ["PATRON_ROLE"])
LIBRARIAN_ROLE = int(os.environ["LIBRARIAN_ROLE"])
RECORD_CHANNEL_ID = int(os.environ["RECORD_CHANNEL_ID"])
EXTENTIONS = ["jishaku"]
TIMEFORMAT = "%d/%m" if sys.platform == "win32" else "%d/%-m"

def is_book_available(book: Book, topic: str) -> bool:
    _, available_book_isbns, _, _ = get_records_stats(topic);
    if book.identifiers.isbn_13[0] in available_book_isbns:
        return True
    return False

def font(size: int, bold: bool = True):
    return ImageFont.truetype(
        "fonts/Poppins-Bold.ttf" if bold else "fonts/Poppins-Regular.ttf", size
    )

def embed_title_parse(embed_title: str):
    return embed_title[:13], embed_title[13], embed_title[14:]

def build_renewed_receipt_image(
    book: Book, patron: str, receipt: int, receipt_expired: str
) -> BytesIO:
    img, draw = _build_image("renewed", book, patron, receipt)
    draw.text((1190, 889), receipt_expired, fill=YELLOW, font=font(64))
    return _save_image(img)


def build_receipt_image(
    book: Book, patron: str, receipt: int, receipt_expired: str
) -> BytesIO:
    img, draw = _build_image("borrowed", book, patron, receipt)
    draw.text((1190, 889), receipt_expired, fill=YELLOW, font=font(64))
    return _save_image(img)


def build_returned_receipt_image(book: Book, patron: str, receipt: int) -> BytesIO:
    img, _ = _build_image("returned", book, patron, receipt)
    return _save_image(img)


def _build_image(mode: str, book: Book, patron: str, receipt: int):
    time = datetime.datetime.now()
    SUB_RECEIPT = f"{receipt}\n{time.strftime('%d %B, %Y')}"

    img = Image.open(f"images/{mode}_receipt_template.png")
    draw = ImageDraw.Draw(img)
    img_width, _ = img.size

    draw.text((620, 23), f"#{receipt}", fill=YELLOW, font=font(125))

    x, y = (350, 265)
    for line in SUB_RECEIPT.split("\n"):
        for letter in line:
            draw.text((x, y), letter, fill="white", font=font(35, False))
            char_width = (
                font(35, False).getbbox(letter)[2] - font(35, False).getbbox(letter)[0]
            )
            x += char_width + LETTER_SPACING
        x, y = (74, 310)

    patron_letter_x = img_width - 100
    draw.text((patron_letter_x, 380), patron, fill="black", font=font(75), anchor="rt")

    LEFT_SIDE_INFO_X = 119
    RIGHT_SIDE_INFO_X = img_width - 580
    draw.text((LEFT_SIDE_INFO_X, 596), book.full_title, fill="black", font=font(35))
    draw.text((LEFT_SIDE_INFO_X, 724), book.main_author, fill="black", font=font(35))

    draw.text(
        (RIGHT_SIDE_INFO_X, 596),
        book.identifiers.isbn_13[0],
        fill="black",
        font=font(35),
    )
    draw.text((RIGHT_SIDE_INFO_X, 715), book.publishers[0], fill="black", font=font(35))

    return img, draw


def _save_image(img) -> BytesIO:
    byte_io = BytesIO()
    img.save(byte_io, "PNG")
    byte_io.seek(0)
    return byte_io


def get_records_stats(topic):
    topic = topic.split("\n")
    total_records = int(topic[0].split(": ")[1])
    available_book_isbns = [
        isbn.lstrip() for isbn in topic[2].split(":")[1].split(", ") if isbn.lstrip()
    ]
    borrowed_book_isbns = [
        isbn.lstrip() for isbn in topic[4].split(":")[1].split(", ") if isbn.lstrip()
    ]

    return total_records, available_book_isbns, borrowed_book_isbns, topic
