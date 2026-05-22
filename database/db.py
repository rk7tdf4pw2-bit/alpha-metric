import aiosqlite

DB_PATH = "bot.db"


async def init_db(_=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id   INTEGER PRIMARY KEY,
                username  TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS watchlists (
                user_id  INTEGER,
                symbol   TEXT,
                PRIMARY KEY (user_id, symbol),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER,
                symbol    TEXT,
                condition TEXT,
                target    REAL,
                triggered INTEGER DEFAULT 0
            )
        """)
        # Migration: mevcut DB'ye is_premium ekle (zaten varsa hata vermez)
        try:
            await db.execute("ALTER TABLE users ADD COLUMN is_premium INTEGER DEFAULT 0")
        except Exception:
            pass

        await db.commit()


async def set_premium(user_id: int, status: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (user_id, username, is_premium) VALUES (?, '', ?) "
            "ON CONFLICT(user_id) DO UPDATE SET is_premium = excluded.is_premium",
            (user_id, 1 if status else 0),
        )
        await db.commit()


async def is_premium_user(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT is_premium FROM users WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return bool(row and row[0])


async def get_premium_users() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE is_premium = 1")
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def add_coin(user_id: int, username: str, symbol: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (user_id, username),
        )
        cursor = await db.execute(
            "INSERT OR IGNORE INTO watchlists (user_id, symbol) VALUES (?, ?)",
            (user_id, symbol.upper()),
        )
        await db.commit()
        return cursor.rowcount > 0


async def add_coins(user_id: int, username: str, symbols: list[str]) -> int:
    """Add multiple symbols to a user's watchlist and return number of additions."""
    if not symbols:
        return 0

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (user_id, username),
        )
        added_count = 0
        for symbol in symbols:
            cursor = await db.execute(
                "INSERT OR IGNORE INTO watchlists (user_id, symbol) VALUES (?, ?)",
                (user_id, symbol.upper()),
            )
            if cursor.rowcount > 0:
                added_count += 1
        await db.commit()
        return added_count


async def has_watchlist(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM watchlists WHERE user_id = ? LIMIT 1",
            (user_id,),
        )
        return await cursor.fetchone() is not None


async def get_coins(user_id: int) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT symbol FROM watchlists WHERE user_id = ? ORDER BY symbol",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def add_alert(user_id: int, symbol: str, condition: str, target: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO alerts (user_id, symbol, condition, target) VALUES (?, ?, ?, ?)",
            (user_id, symbol.upper(), condition, target),
        )
        await db.commit()


async def get_pending_alerts() -> list[tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, user_id, symbol, condition, target FROM alerts WHERE triggered = 0"
        )
        return await cursor.fetchall()


async def mark_alert_triggered(alert_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE alerts SET triggered = 1 WHERE id = ?", (alert_id,))
        await db.commit()


async def get_all_users() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM users")
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def get_all_watchlists() -> list[tuple[int, str]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id, symbol FROM watchlists")
        return await cursor.fetchall()
