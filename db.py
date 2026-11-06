"""SQLite storage for bookings. Times are stored as local ISO strings (business time zone)."""
from datetime import date, datetime, timedelta

import aiosqlite

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    service TEXT NOT NULL,
    master TEXT NOT NULL,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',      -- active | cancelled
    reminded TEXT NOT NULL DEFAULT '',          -- comma-separated hours already reminded
    created TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS bookings_master_start ON bookings(master, start);
"""


async def init() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


def _row(r) -> dict:
    keys = ["id", "user_id", "name", "phone", "service", "master", "start", "end", "status", "reminded", "created"]
    d = dict(zip(keys, r))
    d["start"], d["end"] = datetime.fromisoformat(d["start"]), datetime.fromisoformat(d["end"])
    return d


async def busy(master: str, day: date) -> list[tuple[datetime, datetime]]:
    lo, hi = datetime.combine(day, datetime.min.time()), datetime.combine(day + timedelta(days=1), datetime.min.time())
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT start, end FROM bookings WHERE master=? AND status='active' "
                               "AND start < ? AND end > ?", (master, hi.isoformat(), lo.isoformat()))
        return [(datetime.fromisoformat(a), datetime.fromisoformat(b)) for a, b in await cur.fetchall()]


async def create(user_id: int, name: str, phone: str, service: str, master: str, start: datetime,
                 end: datetime) -> int | None:
    """Insert a booking unless the slot was taken in the meantime. Returns the id, or None if taken."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")      # one writer at a time: no double booking
        cur = await db.execute("SELECT 1 FROM bookings WHERE master=? AND status='active' AND start < ? AND end > ?",
                               (master, end.isoformat(), start.isoformat()))
        if await cur.fetchone():
            await db.rollback()
            return None
        cur = await db.execute(
            "INSERT INTO bookings (user_id, name, phone, service, master, start, end, created) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (user_id, name, phone, service, master, start.isoformat(), end.isoformat(),
             datetime.now().isoformat(timespec="seconds")))
        await db.commit()
        return cur.lastrowid


async def get(booking_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM bookings WHERE id=?", (booking_id,))
        r = await cur.fetchone()
        return _row(r) if r else None


async def user_upcoming(user_id: int, now: datetime) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM bookings WHERE user_id=? AND status='active' AND start >= ? "
                               "ORDER BY start", (user_id, now.isoformat()))
        return [_row(r) for r in await cur.fetchall()]


async def on_day(day: date) -> list[dict]:
    lo, hi = datetime.combine(day, datetime.min.time()), datetime.combine(day + timedelta(days=1), datetime.min.time())
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM bookings WHERE status='active' AND start >= ? AND start < ? "
                               "ORDER BY start, master", (lo.isoformat(), hi.isoformat()))
        return [_row(r) for r in await cur.fetchall()]


async def cancel(booking_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))
        await db.commit()


async def due_reminders(now: datetime, hours: int) -> list[dict]:
    """Active bookings starting within `hours` from now that have not had this reminder yet."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM bookings WHERE status='active' AND start > ? AND start <= ?",
                               (now.isoformat(), (now + timedelta(hours=hours)).isoformat()))
        rows = [_row(r) for r in await cur.fetchall()]
    return [r for r in rows if str(hours) not in r["reminded"].split(",")]


async def mark_reminded(booking_id: int, hours: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE bookings SET reminded = reminded || ? WHERE id=?", (f"{hours},", booking_id))
        await db.commit()
