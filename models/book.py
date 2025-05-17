from dataclasses import dataclass
from typing import Literal, Optional

@dataclass
class Identifiers:
    isbn_13: list
    openlibrary: list

class Book:
    def __init__(self, payload, details, **kwargs: any):
        self._emoji = kwargs.pop("emoji")
        self.__payload: dict = payload
        self.__details = details
        try:
            self.__payload.get("identifiers").pop("isbn_10")
        except KeyError:
            pass
        self.__identifiers = self.__payload.get("identifiers")
        print(self.__identifiers)

    def __repr__(self):
        return self.title

    @classmethod
    def from_books(cls, isbn: str, books: list):  
        return [book for book in books if book.identifiers.isbn_13[0] == isbn][0]

    @property
    def url(self):
        return self.__payload.get("url")
    
    @property
    def emoji(self):
        return self._emoji

    @property
    def publishers(self):
        l = []
        for v in (a.items() for a in self.__payload.get("publishers")):
            for _, publisher in v:
                l.append(publisher)
        return l

    @property
    def published(self):
        return self.__payload.get("publish_date")

    @property
    def published_year(self):
        date = self.__payload.get("publish_date").split(" ")
        return date[2] if len(date) > 1 else date[0]

    @property
    def title(self):
        return self.__payload.get("title")

    @property
    def description(self):
        return (
            self.__details.get(
                "description", {"value": "*Description is not provided*"}
            )
        )["value"]

    @property
    def identifiers(self):
        return Identifiers(**self.__identifiers)

    @property
    def main_author(self):
        authors = self.__payload.get("authors")
        return authors[0]["name"] if authors else "*Author not provided*"

    @property
    def full_title(self):
        return self.__details.get("full_title") or self.title

    @property
    def main_author_olid(self):
        authors = self.__payload.get("authors")
        return authors[0]["url"].split("/")[4] if authors else "OLID"

    def get_cover_url(self, size: Literal["small", "medium", "large"]):
        return self.__payload.get(
            "cover",
            {
                "small": f"https://covers.openlibrary.org/b/olid/{self.identifiers.openlibrary[0]}-S.jpg",
                "medium": f"https://covers.openlibrary.org/b/olid/{self.identifiers.openlibrary[0]}-M.jpg",
                "large": f"https://covers.openlibrary.org/b/olid/{self.identifiers.openlibrary[0]}-L.jpg",
            },
        )[size]

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
