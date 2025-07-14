import json

from dataclasses import dataclass
from typing import Literal
from db import BookDB

@dataclass
class Identifiers:
    isbn_13: list
    openlibrary: list

class Book:
    def __init__(self, payload: BookDB):
        self.__payload = payload
        self.__details = json.loads(payload.details)
        self.__identifiers = json.loads(payload.identifiers)
        self._publishers = json.loads(payload.publishers)
        self._authors =  json.loads(payload.authors)
        self._cover = json.loads(payload.cover)

        try:
            self.__identifiers.pop("isbn_10")
        except KeyError:
            pass

        print(self.__identifiers)
        

    def __repr__(self):
        return self.title

    @classmethod
    def from_books(cls, isbn: str, books: list):  
        return [book for book in books if book.identifiers.isbn_13[0] == isbn][0]

    @property
    def url(self):
        return self.__payload.url
    
    @property
    def emoji(self):
        return self.__payload.emoji

    @property
    def publishers(self):
        return self._publishers

    @property
    def published(self):
        return self.__payload.publish_date

    @property
    def published_year(self):
        date = self.published.split(" ")
        return date[2] if len(date) > 1 else date[0]

    @property
    def title(self):
        return self.__payload.title

    @property
    def description(self):
        description =  (
            self.__details.get(
                "description", {"value": "*Description is not provided*"}
            )
        )
        return description if isinstance(description, str) else description["value"]
    
    @property
    def authors(self):
        return self._authors

    @property
    def main_author(self):
        return self.authors[0]["name"] if self.authors else "*Author not provided*"

    @property
    def full_title(self):
        return self.__details.get("full_title") or self.title

    @property
    def main_author_olid(self):
        return self.authors[0]["url"].split("/")[4] if self.authors else "OLID"
    
    @property
    def identifiers(self):
        return Identifiers(**self.__identifiers)
    
    @property
    def available(self):
        return self.__payload.available

    def get_cover_url(self, size: Literal["small", "medium", "large"]):
        cover = self._cover
        return cover if isinstance(cover, str) else cover[size]

    def get_author_image_url(self, size: Literal["small", "medium", "large"]):
        match size:
            case "small":
                size = "S"
            case "medium":
                size = "M"
            case "large":
                size = "L"
            case _:
                ...

        return f"https://covers.openlibrary.org/a/olid/{self.main_author_olid}-{size}.jpg"


# record = Record(data)
# for k, v in data["records"].items():
#     print(json.dumps(v["data"], indent=4))
#     book = Book(book_data, v["details"]["details"])
#     print(book.description)
#     print(book.get_cover_url("medium"))
#     print(book.identifiers.isbn_13)
#     print(book.main_author_olid)
