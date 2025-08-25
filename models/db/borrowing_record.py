import os
import datetime

from .book import BookDB
from .db import Base
from dotenv import load_dotenv
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text, Enum, desc, insert, select
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum

load_dotenv()

BORROWED_DAYS = int(os.environ["Borrowed_DAYS"])

class Status(str, PyEnum):
    BORROWED    = "borrowed"
    RETURNED    = "returned"
    LATE        = "late"
    PENDING     = "pending"
    
class BorrowingRecordDB(Base):
    __tablename__ = 'records'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False) #ToDo: Create user tables
    book_isbn = Column(String(15), ForeignKey('books.isbn'), nullable=False)
    
    borrow_date = Column(DateTime, default=datetime.datetime.now(datetime.timezone.utc))
    due_date = Column(DateTime, nullable=False)
    last_renewed_date = Column(DateTime, nullable=True)
    return_date = Column(DateTime, nullable=True)
    
    status = Column(Enum(Status), default=Status.BORROWED)
    remarks = Column(Text, nullable=True)

    # user = relationship("User", back_populates="borrow_records")
    book = relationship("BookDB", back_populates="borrow_records")

    @staticmethod
    async def get_by_id(session, id):
        return await session.execute(select(BorrowingRecordDB).where(BorrowingRecordDB.id == id))
    
    @staticmethod
    async def get_latest(session):
        result = await session.execute(
            select(BorrowingRecordDB)
            .order_by(desc(BorrowingRecordDB.borrow_date)).limit(1)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_all_by_patron(session, user_id):
        result = await session.execute(
            select(BorrowingRecordDB)
            .where(BorrowingRecordDB.user_id == user_id)
            .order_by(desc(BorrowingRecordDB.borrow_date))
        )
        return result.scalars().all()
    
    @staticmethod
    async def user_is_borrowing(session, user_id):
        records = (await BorrowingRecordDB.get_all_by_patron(session, user_id))
        if records and records[0].status == Status.BORROWED:
            return True
        return False
    
    @staticmethod
    async def create(session, user_id, book_isbn, remarks):
        new_record = BorrowingRecordDB(
            user_id=user_id,
            book_isbn=book_isbn,
            borrow_date=datetime.datetime.now(),
            due_date=datetime.datetime.now() + datetime.timedelta(days=BORROWED_DAYS),
            status=Status.PENDING,
            remarks=remarks
        )
        
        session.add(new_record)   
        await session.commit()

        return await BorrowingRecordDB.get_latest(session)
    
    @staticmethod
    async def renew(session, id):
        record = await BorrowingRecordDB.get_by_id(session, id)
        record.last_renewed_date = datetime.datetime.now()
        record.due_date = record.due_date + datetime.timedelta(days=BORROWED_DAYS)
        await session.commit()