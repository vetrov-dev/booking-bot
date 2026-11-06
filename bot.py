"""Booking bot for a barbershop or salon: clients pick a service, master, day and time; the owner gets notified;
clients get reminders and can cancel. Admins see the schedule and can cancel any booking.

    python bot.py
"""
import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message,
                           ReplyKeyboardMarkup, ReplyKeyboardRemove)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import db
from config import (ADDRESS, ADMIN_IDS, BOT_TOKEN, BUSINESS_NAME, CLOSE_HOUR, DAYS_AHEAD, DAYS_OFF, MASTERS,
                    MIN_LEAD_MINUTES, OPEN_HOUR, PHONE, REMIND_HOURS, SERVICE_BY_CODE, SERVICES, SLOT_MINUTES,
                    UTC_OFFSET)
from slots import day_slots, fmt_day, fmt_dt, open_days

log = logging.getLogger("booking")
router = Router()
TZ = timezone(timedelta(hours=UTC_OFFSET))


def now_local() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None)


class Book(StatesGroup):
    name = State()
    phone = State()


MENU = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
    [KeyboardButton(text="✂️ Записаться")],
    [KeyboardButton(text="📅 Мои записи"), KeyboardButton(text="📍 Контакты")],
])


def kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in row]
                                                 for row in rows])


# ---- client flow ---------------------------------------------------------------------------------------------

@router.message(CommandStart())
async def start(m: Message, state: FSMContext) -> None:
    await state.clear()
    await m.answer(f"Здравствуйте! Это бот записи в <b>{BUSINESS_NAME}</b>.\nВыберите, что нужно:", reply_markup=MENU)


@router.message(F.text == "📍 Контакты")
async def contacts(m: Message) -> None:
    await m.answer(f"<b>{BUSINESS_NAME}</b>\n📍 {ADDRESS}\n📞 {PHONE}\n🕙 Каждый день {OPEN_HOUR}:00–{CLOSE_HOUR}:00")


@router.message(F.text == "✂️ Записаться")
async def choose_service(m: Message, state: FSMContext) -> None:
    await state.clear()
    await m.answer("Выберите услугу:", reply_markup=kb(
        [[(f"{s.title} · {s.minutes} мин · {s.price} ₽", f"svc:{s.code}")] for s in SERVICES]))


@router.callback_query(F.data.startswith("svc:"))
async def choose_master(c: CallbackQuery, state: FSMContext) -> None:
    code = c.data.split(":", 1)[1]
    await state.update_data(service=code)
    rows = [[(name, f"mst:{i}")] for i, name in enumerate(MASTERS)] + [[("← Назад", "back:svc")]]
    await c.message.edit_text(f"<b>{SERVICE_BY_CODE[code].title}</b>\nВыберите мастера:", reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("mst:"))
async def choose_day(c: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(master=MASTERS[int(c.data.split(":", 1)[1])])
    await show_days(c, state)


async def show_days(c: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    b = InlineKeyboardBuilder()
    for d in open_days(now_local().date(), DAYS_AHEAD, DAYS_OFF):
        b.button(text=fmt_day(d), callback_data=f"day:{d.isoformat()}")
    b.adjust(2)
    b.row(InlineKeyboardButton(text="← Назад", callback_data=f"svc:{data['service']}"))
    await c.message.edit_text(f"Мастер: <b>{data['master']}</b>\nВыберите день:", reply_markup=b.as_markup())
    await c.answer()


@router.callback_query(F.data.startswith("day:"))
async def choose_time(c: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    day = date.fromisoformat(c.data.split(":", 1)[1])
    svc = SERVICE_BY_CODE[data["service"]]
    free = day_slots(day, svc.minutes, await db.busy(data["master"], day), now_local(), open_hour=OPEN_HOUR,
                     close_hour=CLOSE_HOUR, step=SLOT_MINUTES, lead_minutes=MIN_LEAD_MINUTES)
    b = InlineKeyboardBuilder()
    for t in free:
        b.button(text=f"{t:%H:%M}", callback_data=f"time:{t.isoformat(timespec='minutes')}")
    b.adjust(4)
    b.row(InlineKeyboardButton(text="← Другой день", callback_data="back:day"))
    text = f"{fmt_day(day)}, мастер {data['master']}\n"
    text += "Выберите время:" if free else "На этот день свободного времени нет, выберите другой."
    await c.message.edit_text(text, reply_markup=b.as_markup())
    await c.answer()


@router.callback_query(F.data.startswith("time:"))
async def ask_name(c: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(start=c.data.split(":", 1)[1])
    await state.set_state(Book.name)
    await c.message.edit_text(f"Время: <b>{fmt_dt(datetime.fromisoformat(c.data.split(':', 1)[1]))}</b>\n"
                              "Как вас зовут?")
    await c.answer()


@router.message(Book.name, F.text)
async def ask_phone(m: Message, state: FSMContext) -> None:
    await state.update_data(name=m.text.strip()[:60])
    await state.set_state(Book.phone)
    await m.answer("Оставьте номер телефона: нажмите кнопку ниже или напишите его.", reply_markup=ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=True,
        keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]]))


@router.message(Book.phone, F.contact | F.text)
async def confirm(m: Message, state: FSMContext) -> None:
    phone = m.contact.phone_number if m.contact else m.text.strip()
    if sum(ch.isdigit() for ch in phone) < 10:
        await m.answer("Похоже, в номере не хватает цифр. Напишите номер полностью, например +7 900 123-45-67.")
        return
    await state.update_data(phone=phone)
    d = await state.get_data()
    svc = SERVICE_BY_CODE[d["service"]]
    await m.answer("Проверьте запись:", reply_markup=ReplyKeyboardRemove())
    await m.answer(f"✂️ {svc.title}, {svc.price} ₽\n👤 Мастер: {d['master']}\n"
                   f"🕙 {fmt_dt(datetime.fromisoformat(d['start']))}\n🙋 {d['name']}, {phone}",
                   reply_markup=kb([[("✅ Подтвердить", "ok"), ("✖️ Отмена", "back:menu")]]))


@router.callback_query(F.data == "ok")
async def save(c: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    d = await state.get_data()
    if not {"service", "master", "start", "name", "phone"} <= d.keys():
        await c.answer("Запись устарела, начните заново", show_alert=True)
        return
    svc = SERVICE_BY_CODE[d["service"]]
    start_t = datetime.fromisoformat(d["start"])
    bid = await db.create(c.from_user.id, d["name"], d["phone"], svc.code, d["master"], start_t,
                          start_t + timedelta(minutes=svc.minutes))
    await state.clear()
    if bid is None:
        await c.message.edit_text("Это время только что заняли. Выберите, пожалуйста, другое.")
        await c.message.answer("Выберите, что нужно:", reply_markup=MENU)
        return
    await c.message.edit_text(f"Готово, вы записаны! ✅\n{svc.title} у мастера {d['master']}, {fmt_dt(start_t)}.\n"
                              f"Напомню заранее. Адрес: {ADDRESS}")
    await c.message.answer("Если планы изменятся, отменить запись можно в «📅 Мои записи».", reply_markup=MENU)
    await notify_admins(bot, f"🆕 Новая запись #{bid}\n{svc.title}, мастер {d['master']}\n{fmt_dt(start_t)}\n"
                             f"{d['name']}, {d['phone']}")
    await c.answer()


@router.message(F.text == "📅 Мои записи")
async def my_bookings(m: Message) -> None:
    rows = await db.user_upcoming(m.from_user.id, now_local())
    if not rows:
        await m.answer("У вас нет предстоящих записей.")
        return
    for r in rows:
        await m.answer(f"#{r['id']} · {SERVICE_BY_CODE[r['service']].title}\nМастер {r['master']}, {fmt_dt(r['start'])}",
                       reply_markup=kb([[("Отменить запись", f"cancel:{r['id']}")]]))


@router.callback_query(F.data.startswith("cancel:"))
async def cancel(c: CallbackQuery, bot: Bot) -> None:
    r = await db.get(int(c.data.split(":", 1)[1]))
    if not r or r["status"] != "active" or (r["user_id"] != c.from_user.id and c.from_user.id not in ADMIN_IDS):
        await c.answer("Запись не найдена", show_alert=True)
        return
    await db.cancel(r["id"])
    await c.message.edit_text(f"Запись #{r['id']} на {fmt_dt(r['start'])} отменена.")
    if c.from_user.id == r["user_id"]:
        await notify_admins(bot, f"❌ Клиент отменил запись #{r['id']}: {r['name']}, {fmt_dt(r['start'])}")
    else:
        await bot.send_message(r["user_id"], f"Ваша запись на {fmt_dt(r['start'])} отменена администратором. "
                                             f"Подробности по телефону {PHONE}.")
    await c.answer()


@router.callback_query(F.data.startswith("back:"))
async def back(c: CallbackQuery, state: FSMContext) -> None:
    where = c.data.split(":", 1)[1]
    if where == "svc":
        await c.message.edit_text("Выберите услугу:", reply_markup=kb(
            [[(f"{s.title} · {s.minutes} мин · {s.price} ₽", f"svc:{s.code}")] for s in SERVICES]))
        await c.answer()
    elif where == "day":
        await show_days(c, state)
    else:
        await state.clear()
        await c.message.edit_text("Запись отменена.")
        await c.message.answer("Выберите, что нужно:", reply_markup=MENU)
        await c.answer()


# ---- admin -----------------------------------------------------------------------------------------------------

async def notify_admins(bot: Bot, text: str) -> None:
    for a in ADMIN_IDS:
        try:
            await bot.send_message(a, text)
        except Exception as e:  # noqa: BLE001 - an admin who blocked the bot must not break booking
            log.warning("admin %s: %s", a, e)


@router.message(Command("today", "tomorrow", "day"))
async def schedule(m: Message) -> None:
    if m.from_user.id not in ADMIN_IDS:
        return
    cmd, _, arg = m.text.partition(" ")
    day = now_local().date()
    if cmd.startswith("/tomorrow"):
        day += timedelta(days=1)
    elif cmd.startswith("/day"):
        try:
            day = date.fromisoformat(arg.strip())
        except ValueError:
            await m.answer("Формат: /day 2026-11-20")
            return
    rows = await db.on_day(day)
    if not rows:
        await m.answer(f"{fmt_day(day)}: записей нет.")
        return
    await m.answer(f"<b>{fmt_day(day)}</b>, записей: {len(rows)}")
    for r in rows:
        await m.answer(f"{r['start']:%H:%M}–{r['end']:%H:%M} · {r['master']}\n{SERVICE_BY_CODE[r['service']].title}\n"
                       f"{r['name']}, {r['phone']}", reply_markup=kb([[("Отменить", f"cancel:{r['id']}")]]))


# ---- reminders -------------------------------------------------------------------------------------------------

async def reminder_loop(bot: Bot) -> None:
    while True:
        for h in sorted(REMIND_HOURS):
            for r in await db.due_reminders(now_local(), h):
                try:
                    await bot.send_message(r["user_id"], f"⏰ Напоминание: {SERVICE_BY_CODE[r['service']].title} "
                                                         f"у мастера {r['master']}, {fmt_dt(r['start'])}.\n📍 {ADDRESS}")
                except Exception as e:  # noqa: BLE001
                    log.warning("reminder %s: %s", r["id"], e)
                for hh in REMIND_HOURS:          # a booking made 1 h ahead gets one reminder, not two
                    if hh >= h:
                        await db.mark_reminded(r["id"], hh)
        await asyncio.sleep(60)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not BOT_TOKEN:
        raise SystemExit("Set BOT_TOKEN in .env (copy .env.example)")
    await db.init()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    asyncio.create_task(reminder_loop(bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
