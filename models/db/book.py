from .db import Base
from models.book import Book
from sqlalchemy import Column, Integer, String, JSON, select
from sqlalchemy.orm import relationship

class BookDB(Base):
    __tablename__ = 'books'
    isbn = Column(String(15), primary_key=True)

    identifiers = Column(JSON)        # {"Openlib": "...", "ISBN_13": "..."}
    details = Column(JSON)            # {"description": "...", "full_title": "..."}
    available = Column(Integer)      

    url = Column(String(255))
    emoji = Column(String(10))        # stores an emoji character
    publish_date = Column(String(50))
    title = Column(String(255))
    cover = Column(String(255))

    # JSON arrays
    publishers = Column(JSON)         # ["Publisher A", "Publisher B"]
    authors = Column(JSON)            # ["Author A", "Author B"]

    borrow_records = relationship("BorrowingRecordDB", back_populates="book")

    @staticmethod
    async def get_by_id(session, isbn, parse_to_book):
        book = (await session.execute(select(BookDB).where(BookDB.isbn == isbn))).scalar()
        if parse_to_book:
            return Book(book)
        return book
    
    @staticmethod
    async def get_allowed_books(session, parse_to_book):
        books = (await session.execute(select(BookDB).where(BookDB.available == 1))).scalars().all()
        if parse_to_book:
            return [Book(book) for book in books]
        return books
    
    @staticmethod
    async def get_all(session, parse_to_book):
        books = (await session.execute(select(BookDB))).scalars().all()
        if parse_to_book:
            return [Book(book) for book in books]
        return books

    @staticmethod
    async def borrow(session, isbn):
        book: BookDB = await BookDB.get_by_id(session, isbn, False)

        if book:
            book.available = 0
            await session.commit()
            return True
        return False