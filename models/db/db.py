import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()

engine = create_async_engine(f"mysql+aiomysql://{os.environ['MYSQL_USER']}:{os.environ['MYSQL_PASSWORD']}@localhost/{os.environ['MYSQL_DB']}", echo=True) 
Base = declarative_base()
AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)