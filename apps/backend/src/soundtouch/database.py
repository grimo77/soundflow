import aiosqlite
from soundtouch.config import settings

DB = settings.db_path


async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                name TEXT,
                ip TEXT,
                mac TEXT,
                model TEXT,
                firmware TEXT,
                last_seen REAL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS presets (
                device_id TEXT,
                slot INTEGER,
                name TEXT,
                source TEXT,
                source_account TEXT,
                location TEXT,
                icon_url TEXT,
                PRIMARY KEY (device_id, slot)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS zones (
                id TEXT PRIMARY KEY,
                name TEXT,
                master_device_id TEXT,
                member_ids TEXT
            )
        """)
        await db.commit()


async def get_db():
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        yield db
