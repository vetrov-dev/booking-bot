# Booking Bot for Salons and Barbershops

A Telegram bot that lets clients book an appointment in a few taps: pick a service, a master, a day and a free
time slot, leave a name and phone. The owner gets every new booking instantly, clients get reminders and can
cancel themselves.

The bot's interface is in Russian; services, masters, hours and texts are set in `config.py` and `.env`.

## Features

**For clients**
- Service list with duration and price
- Master choice, then only the days the business is open
- Only free slots are shown: the bot checks the service length against existing bookings, closing time and a
  minimum lead time
- Phone by one tap (Telegram contact button) or typed by hand, with validation
- Confirmation screen, reminders 24 h and 2 h before the visit (configurable)
- "My bookings" with one-tap cancel

**For the owner**
- Instant notification of every new booking and every cancellation
- `/today`, `/tomorrow`, `/day 2026-11-20`: the schedule for a day, with a cancel button on each booking
- Cancelling a booking notifies the client

**Under the hood**
- No double booking: the slot is re-checked inside a SQLite write transaction at the moment of confirmation
- One reminder per booking per window, even across restarts
- Times are computed in the business's time zone, not the server's

## Stack

Python 3.11+, aiogram 3 (FSM, inline keyboards), aiosqlite, python-dotenv, pytest.

## Run

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip
cp .env.example .env                           # set BOT_TOKEN and ADMIN_IDS
python bot.py
```

Edit `SERVICES` and `MASTERS` in `config.py` and the hours in `.env` for a real business.

## Tests

```bash
pip install pytest
pytest -q
```

Covers slot calculation (closing time, overlaps, lead time, days off), double-booking protection and reminders.

## Project layout

| File | What it does |
|---|---|
| `bot.py` | Telegram handlers: booking flow, my bookings, admin schedule, reminder loop |
| `slots.py` | Free slot calculation and date formatting, pure functions |
| `db.py` | SQLite storage |
| `config.py` | Settings and the business catalog |
