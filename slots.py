"""Free time slots. Pure functions, no I/O, so they are easy to test."""
from datetime import date, datetime, timedelta


def day_slots(day: date, minutes: int, busy: list[tuple[datetime, datetime]], now: datetime, *,
              open_hour: int, close_hour: int, step: int, lead_minutes: int) -> list[datetime]:
    """Start times on `day` where a service of `minutes` fits between opening and closing, does not overlap
    any (start, end) in `busy`, and starts at least `lead_minutes` from `now`. All datetimes are naive, in the
    business's local time."""
    out = []
    t = datetime.combine(day, datetime.min.time()).replace(hour=open_hour)
    close = t.replace(hour=close_hour)
    earliest = now + timedelta(minutes=lead_minutes)
    while t + timedelta(minutes=minutes) <= close:
        end = t + timedelta(minutes=minutes)
        if t >= earliest and all(end <= b0 or t >= b1 for b0, b1 in busy):
            out.append(t)
        t += timedelta(minutes=step)
    return out


def open_days(today: date, days_ahead: int, days_off: set[int]) -> list[date]:
    return [d for d in (today + timedelta(days=i) for i in range(days_ahead)) if d.weekday() not in days_off]


WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря"]


def fmt_day(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}"


def fmt_dt(t: datetime) -> str:
    return f"{fmt_day(t.date())}, {t:%H:%M}"
