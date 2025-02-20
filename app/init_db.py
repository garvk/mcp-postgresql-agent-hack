import asyncio
import asyncpg
from dotenv import load_dotenv
import os

async def init_chainlit_db():
    """Initialize Chainlit database tables"""
    load_dotenv()
    
    db_url = os.getenv("CHAINLIT_DATABASE_URL")
    if not db_url:
        raise ValueError("CHAINLIT_DATABASE_URL not set")
        
    conn = await asyncpg.connect(db_url)
    
    # Create tables for Chainlit persistence
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS thread (
            id TEXT PRIMARY KEY,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS message (
            id TEXT PRIMARY KEY,
            thread_id TEXT REFERENCES thread(id),
            content TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS user_session (
            id TEXT PRIMARY KEY,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(init_chainlit_db())