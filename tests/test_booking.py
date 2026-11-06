import asyncio
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")

import db  # noqa: E402
from slots import day_slots, open_days  # noqa: E402

DAY = date(2026, 11, 20)          # a Friday
EARLY = datetime(2026, 11, 19, 9, 0)


def slots(minutes, busy=(), now=EARLY):
    return [t.strftime("%H:%M") for t in day_slots(DAY, minutes, list(busy), now, open_hour=10, close_hour=13,
                                                   step=30, lead_minutes=60)]


def test_empty_day():
    assert slots(60) == ["10:00", "10:30", "11:00", "11:30", "12:00"]


def test_service_must_fit_before_closing():
    assert slots(90)[-1] == "11:30"


def test_busy_interval_blocks_overlaps_only():
    busy = [(datetime(2026, 11, 20, 11, 0), datetime(2026, 11, 20, 12, 0))]
    assert slots(60, busy) == ["10:00", "12:00"]


def test_lead_time():
    assert slots(30, now=datetime(2026, 11, 20, 10, 40)) == ["12:00", "12:30"]


def test_days_off():
    days = open_days(DAY, 7, {6})
    assert len(days) == 6 and all(d.weekday() != 6 for d in days)


def test_no_double_booking_and_reminders():
    async def run():
        await db.init()
        s = datetime(2026, 11, 20, 11, 0)
        a = await db.create(1, "A", "+70000000000", "cut", "Алексей", s, s + timedelta(minutes=60))
        b = await db.create(2, "B", "+70000000001", "cut", "Алексей", s + timedelta(minutes=30),
                            s + timedelta(minutes=90))
        c = await db.create(3, "C", "+70000000002", "cut", "Ирина", s, s + timedelta(minutes=60))
        assert a and c and b is None                       # same master overlap refused, other master fine
        due = await db.due_reminders(s - timedelta(hours=1), 2)
        assert {r["id"] for r in due} == {a, c}
        await db.mark_reminded(a, 2)
        assert {r["id"] for r in await db.due_reminders(s - timedelta(hours=1), 2)} == {c}
        await db.cancel(c)
        assert await db.busy("Ирина", DAY) == []
    asyncio.run(run())
