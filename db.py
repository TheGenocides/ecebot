import os
from dotenv import load_dotenv
from sqlalchemy import Column, Integer, String, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

load_dotenv()

engine = create_async_engine(f"mysql+aiomysql://{os.environ['MYSQL_USER']}:{os.environ['MYSQL_PASSWORD']}@localhost/{os.environ['MYSQL_DB']}", echo=True) 

Base = declarative_base()

class BookDB(Base):
    __tablename__ = 'books'
    id = Column(Integer, primary_key=True)

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


AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)
