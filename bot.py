"""
Бот «109: Volunteers» — система взаимопомощи.
Двуязычный интерфейс: русский и казахский.

Возможности:
  • выбор языка (сохраняется в БД);
  • регистрация волонтёра (ФИО, возраст, телефон, геолокация);
  • создание заявки на помощь -> модерация оператором -> публикация;
  • показ ближайших заявок волонтёру (радиус из config.NEARBY_RADIUS_KM);
  • «взять заявку» / «заявка выполнена» с начислением баллов;
  • портфолио волонтёра и место в рейтинге;
  • команды операторов: модерация заявок, экспорт реестров в Excel.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

import config
import db
import reports
from locales import t, category_name, CATEGORY_KEYS

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ------------------------------------------------------------------ #
#  Вспомогательное
# ------------------------------------------------------------------ #

# Кэш языка, чтобы не дёргать БД на каждое сообщение.
_lang_cache = {}


async def lang_of(user_id):
    """Язык пользователя: сначала кэш, потом БД, по умолчанию ru."""
    if user_id in _lang_cache:
        return _lang_cache[user_id]
    lang = await db.get_lang(user_id) or "ru"
    _lang_cache[user_id] = lang
    return lang


def lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang:ru"),
        InlineKeyboardButton(text="🇰🇿 Қазақша", callback_data="setlang:kz"),
    ]])


def main_menu(lang):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "menu_need_help")),
             KeyboardButton(text=t(lang, "menu_be_volunteer"))],
            [KeyboardButton(text=t(lang, "menu_requests")),
             KeyboardButton(text=t(lang, "menu_portfolio"))],
            [KeyboardButton(text=t(lang, "menu_lang"))],
        ],
        resize_keyboard=True,
    )


def categories_kb(lang):
    rows = [[InlineKeyboardButton(text=category_name(lang, key),
                                  callback_data=f"cat:{key}")]
            for key in CATEGORY_KEYS]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def phone_kb(lang):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, "btn_send_phone"), request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True,
    )


def location_kb(lang, with_skip=False):
    rows = [[KeyboardButton(text=t(lang, "btn_send_location"), request_location=True)]]
    if with_skip:
        rows.append([KeyboardButton(text=t(lang, "btn_skip"))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)


def take_kb(lang, req_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "btn_take"), callback_data=f"take:{req_id}")]])


def done_kb(lang, req_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "btn_done"), callback_data=f"done:{req_id}")]])


def confirm_kb(lang, req_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "btn_confirm"), callback_data=f"confirm:{req_id}")]])


def moderation_kb(lang, req_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "btn_approve"), callback_data=f"approve:{req_id}"),
        InlineKeyboardButton(text=t(lang, "btn_reject"), callback_data=f"reject:{req_id}"),
    ]])


# ------------------------------------------------------------------ #
#  FSM-состояния
# ------------------------------------------------------------------ #

class Reg(StatesGroup):          # регистрация волонтёра
    name = State()
    age = State()
    phone = State()
    location = State()


class NewReq(StatesGroup):       # создание заявки
    name = State()
    category = State()
    description = State()
    address = State()
    phone = State()
    location = State()


# ------------------------------------------------------------------ #
#  /start и выбор языка
# ------------------------------------------------------------------ #

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    saved = await db.get_lang(message.from_user.id)
    if saved:
        await message.answer(t(saved, "welcome"), reply_markup=main_menu(saved))
    else:
        await message.answer(t("ru", "choose_lang"), reply_markup=lang_keyboard())


@dp.message(Command("lang"))
async def cmd_lang(message: types.Message):
    await message.answer(t("ru", "choose_lang"), reply_markup=lang_keyboard())


@dp.callback_query(F.data.startswith("setlang:"))
async def cb_setlang(callback: types.CallbackQuery):
    lang = callback.data.split(":")[1]
    await db.set_lang(callback.from_user.id, lang)
    _lang_cache[callback.from_user.id] = lang
    await callback.message.answer(t(lang, "lang_set"))
    await callback.message.answer(t(lang, "welcome"), reply_markup=main_menu(lang))
    await callback.answer()


# Кнопка «🌐 Язык» из меню (на любом из языков)
@dp.message(F.text.in_({"🌐 Язык", "🌐 Тіл"}))
async def menu_lang(message: types.Message):
    await message.answer(t("ru", "choose_lang"), reply_markup=lang_keyboard())


# ------------------------------------------------------------------ #
#  Регистрация волонтёра
# ------------------------------------------------------------------ #

@dp.message(F.text.in_({"🤝 Стать волонтёром", "🤝 Ерікті болу"}))
async def be_volunteer(message: types.Message, state: FSMContext):
    lang = await lang_of(message.from_user.id)
    if await db.get_volunteer(message.from_user.id):
        await message.answer(t(lang, "already_volunteer"), reply_markup=main_menu(lang))
        return
    await state.set_state(Reg.name)
    await message.answer(t(lang, "reg_name"), reply_markup=ReplyKeyboardRemove())


@dp.message(Reg.name)
async def reg_name(message: types.Message, state: FSMContext):
    lang = await lang_of(message.from_user.id)
    await state.update_data(name=message.text.strip())
    await state.set_state(Reg.age)
    await message.answer(t(lang, "reg_age"))


@dp.message(Reg.age)
async def reg_age(message: types.Message, state: FSMContext):
    lang = await lang_of(message.from_user.id)
    if not message.text.strip().isdigit():
        await message.answer(t(lang, "reg_age_invalid"))
        return
    age = int(message.text.strip())
    if not (config.VOLUNTEER_MIN_AGE <= age <= config.VOLUNTEER_MAX_AGE):
        await message.answer(t(lang, "reg_age_range",
                               min=config.VOLUNTEER_MIN_AGE,
                               max=config.VOLUNTEER_MAX_AGE))
        return
    await state.update_data(age=age)
    await state.set_state(Reg.phone)
    await message.answer(t(lang, "reg_phone"), reply_markup=phone_kb(lang))


@dp.message(Reg.phone, F.contact)
async def reg_phone(message: types.Message, state: FSMContext):
    lang = await lang_of(message.from_user.id)
    await state.update_data(phone=message.contact.phone_number)
    await state.set_state(Reg.location)
    await message.answer(t(lang, "reg_location"), reply_markup=location_kb(lang))


@dp.message(Reg.location, F.location)
async def reg_location(message: types.Message, state: FSMContext):
    lang = await lang_of(message.from_user.id)
    data = await state.get_data()
    await db.add_volunteer(
        message.from_user.id, data["name"], data["age"], data["phone"],
        message.location.latitude, message.location.longitude,
    )
    await state.clear()
    await message.answer(t(lang, "reg_done"), reply_markup=main_menu(lang))


# ------------------------------------------------------------------ #
#  Создание заявки на помощь
# ------------------------------------------------------------------ #

@dp.message(F.text.in_({"🙋 Нужна помощь", "🙋 Көмек керек"}))
async def need_help(message: types.Message, state: FSMContext):
    lang = await lang_of(message.from_user.id)
    await state.set_state(NewReq.name)
    await message.answer(t(lang, "req_need_name"), reply_markup=ReplyKeyboardRemove())


@dp.message(NewReq.name)
async def req_name(message: types.Message, state: FSMContext):
    lang = await lang_of(message.from_user.id)
    await state.update_data(name=message.text.strip())
    await state.set_state(NewReq.category)
    await message.answer(t(lang, "req_category"), reply_markup=categories_kb(lang))


@dp.callback_query(NewReq.category, F.data.startswith("cat:"))
async def req_category(callback: types.CallbackQuery, state: FSMContext):
    lang = await lang_of(callback.from_user.id)
    await state.update_data(category=callback.data.split(":")[1])
    await state.set_state(NewReq.description)
    await callback.message.answer(t(lang, "req_description"))
    await callback.answer()


@dp.message(NewReq.description)
async def req_description(message: types.Message, state: FSMContext):
    lang = await lang_of(message.from_user.id)
    await state.update_data(description=message.text.strip())
    await state.set_state(NewReq.address)
    await message.answer(t(lang, "req_address"))


@dp.message(NewReq.address)
async def req_address(message: types.Message, state: FSMContext):
    lang = await lang_of(message.from_user.id)
    await state.update_data(address=message.text.strip())
    await state.set_state(NewReq.phone)
    await message.answer(t(lang, "req_phone"), reply_markup=phone_kb(lang))


@dp.message(NewReq.phone, F.contact)
async def req_phone(message: types.Message, state: FSMContext):
    lang = await lang_of(message.from_user.id)
    await state.update_data(phone=message.contact.phone_number)
    await state.set_state(NewReq.location)
    await message.answer(t(lang, "req_location"), reply_markup=location_kb(lang, with_skip=True))


async def _finish_request(message, state, lang, lat, lon):
    data = await state.get_data()
    req_id = await db.add_request(
        message.from_user.id, data["name"], data.get("phone"),
        data["category"], data["description"], data["address"], lat, lon,
    )
    await state.clear()
    await message.answer(t(lang, "req_done"), reply_markup=main_menu(lang))
    # уведомляем операторов о новой заявке на модерацию
    for op_id in config.OPERATOR_IDS:
        op_lang = await lang_of(op_id)
        try:
            await bot.send_message(
                op_id,
                t(op_lang, "mod_new", id=req_id, name=data["name"],
                  phone=data.get("phone") or "—",
                  category=category_name(op_lang, data["category"]),
                  description=data["description"], address=data["address"]),
                reply_markup=moderation_kb(op_lang, req_id),
            )
        except Exception as e:
            logging.warning("Не удалось уведомить оператора %s: %s", op_id, e)


@dp.message(NewReq.location, F.location)
async def req_location(message: types.Message, state: FSMContext):
    lang = await lang_of(message.from_user.id)
    await _finish_request(message, state, lang,
                          message.location.latitude, message.location.longitude)


@dp.message(NewReq.location, F.text.in_({"⏭ Пропустить", "⏭ Өткізіп жіберу"}))
async def req_location_skip(message: types.Message, state: FSMContext):
    lang = await lang_of(message.from_user.id)
    await _finish_request(message, state, lang, None, None)


# ------------------------------------------------------------------ #
#  Доступные заявки / взять / выполнить
# ------------------------------------------------------------------ #

@dp.message(F.text.in_({"📋 Доступные заявки", "📋 Қолжетімді өтінімдер"}))
async def show_requests(message: types.Message):
    lang = await lang_of(message.from_user.id)
    vol = await db.get_volunteer(message.from_user.id)
    if not vol:
        await message.answer(t(lang, "not_volunteer"), reply_markup=main_menu(lang))
        return

    reqs = await db.open_requests()
    shown = 0
    for r in reqs:
        dist = db.haversine_km(vol["lat"], vol["lon"], r["lat"], r["lon"])
        # если у заявки нет координат — показываем без фильтра по радиусу
        if dist != float("inf") and dist > config.NEARBY_RADIUS_KM:
            continue
        dist_text = f"{dist:.1f} км" if dist != float("inf") else t(lang, "dist_unknown")
        await message.answer(
            t(lang, "req_card", id=r["id"],
              category=category_name(lang, r["category"]),
              description=r["description"], address=r["address"] or "—",
              dist=dist_text, points=config.CATEGORY_POINTS.get(r["category"], 0)),
            reply_markup=take_kb(lang, r["id"]),
        )
        shown += 1

    if shown == 0:
        await message.answer(t(lang, "no_requests"), reply_markup=main_menu(lang))


@dp.callback_query(F.data.startswith("take:"))
async def cb_take(callback: types.CallbackQuery):
    lang = await lang_of(callback.from_user.id)
    req_id = int(callback.data.split(":")[1])
    req = await db.get_request(req_id)
    if not req or req["status"] != "open":
        await callback.answer(t(lang, "taken_already"), show_alert=True)
        return
    await db.set_request_status(req_id, "taken", volunteer_id=callback.from_user.id)
    await callback.message.answer(
        t(lang, "taken", id=req_id, name=req["client_name"],
          phone=req["client_phone"] or "—"),
        reply_markup=done_kb(lang, req_id),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("done:"))
async def cb_done(callback: types.CallbackQuery):
    lang = await lang_of(callback.from_user.id)
    req_id = int(callback.data.split(":")[1])
    req = await db.get_request(req_id)
    if not req or req["status"] != "taken":
        await callback.answer()
        return
    # Завершить может только тот волонтёр, который взял заявку.
    if req["volunteer_id"] != callback.from_user.id:
        await callback.answer(t(lang, "not_your_request"), show_alert=True)
        return
    # Не начисляем баллы сразу — ждём подтверждения заявителя.
    await db.set_request_status(req_id, "await_confirm")
    await callback.message.answer(t(lang, "vol_waiting", id=req_id),
                                  reply_markup=main_menu(lang))
    # Просим заявителя подтвердить, что помощь оказана.
    try:
        client_lang = await lang_of(req["client_id"])
        await bot.send_message(
            req["client_id"],
            t(client_lang, "confirm_request", id=req_id),
            reply_markup=confirm_kb(client_lang, req_id),
        )
    except Exception as e:
        logging.warning("Не удалось запросить подтверждение у заявителя: %s", e)
    await callback.answer()


@dp.callback_query(F.data.startswith("confirm:"))
async def cb_confirm(callback: types.CallbackQuery):
    lang = await lang_of(callback.from_user.id)
    req_id = int(callback.data.split(":")[1])
    req = await db.get_request(req_id)
    if not req or req["status"] != "await_confirm":
        await callback.answer(t(lang, "confirm_wrong_status"), show_alert=True)
        return
    # Подтвердить может только сам заявитель.
    if req["client_id"] != callback.from_user.id:
        await callback.answer(t(lang, "not_your_confirm"), show_alert=True)
        return
    # Закрываем заявку и начисляем баллы ТОМУ, кто её брал (не нажимающему).
    await db.set_request_status(req_id, "done")
    points = config.CATEGORY_POINTS.get(req["category"], 0)
    volunteer_id = req["volunteer_id"]
    await db.add_points(volunteer_id, points)
    await callback.answer()
    # Сообщаем волонтёру о начислении.
    try:
        vol_lang = await lang_of(volunteer_id)
        await bot.send_message(volunteer_id,
                               t(vol_lang, "done_thanks", id=req_id, points=points))
    except Exception as e:
        logging.warning("Не удалось уведомить волонтёра о баллах: %s", e)


# ------------------------------------------------------------------ #
#  Портфолио
# ------------------------------------------------------------------ #

@dp.message(F.text.in_({"👤 Моё портфолио", "👤 Менің профилім"}))
async def portfolio(message: types.Message):
    lang = await lang_of(message.from_user.id)
    vol = await db.get_volunteer(message.from_user.id)
    if not vol:
        await message.answer(t(lang, "not_volunteer"), reply_markup=main_menu(lang))
        return
    rank = await db.volunteer_rank(message.from_user.id)
    await message.answer(
        t(lang, "portfolio", name=vol["full_name"], age=vol["age"],
          done=vol["done_count"], points=vol["points"], rank=rank),
        reply_markup=main_menu(lang),
    )


# ------------------------------------------------------------------ #
#  Модерация и экспорт (только операторы)
# ------------------------------------------------------------------ #

def is_operator(user_id):
    return user_id in config.OPERATOR_IDS


@dp.callback_query(F.data.startswith("approve:"))
async def cb_approve(callback: types.CallbackQuery):
    if not is_operator(callback.from_user.id):
        await callback.answer()
        return
    lang = await lang_of(callback.from_user.id)
    req_id = int(callback.data.split(":")[1])
    await db.set_request_status(req_id, "open")
    await callback.message.answer(t(lang, "mod_approved", id=req_id))
    req = await db.get_request(req_id)
    if req:
        try:
            cl = await lang_of(req["client_id"])
            await bot.send_message(req["client_id"], t(cl, "req_approved_client", id=req_id))
        except Exception:
            pass
    await callback.answer()


@dp.callback_query(F.data.startswith("reject:"))
async def cb_reject(callback: types.CallbackQuery):
    if not is_operator(callback.from_user.id):
        await callback.answer()
        return
    lang = await lang_of(callback.from_user.id)
    req_id = int(callback.data.split(":")[1])
    await db.set_request_status(req_id, "rejected")
    await callback.message.answer(t(lang, "mod_rejected", id=req_id))
    req = await db.get_request(req_id)
    if req:
        try:
            cl = await lang_of(req["client_id"])
            await bot.send_message(req["client_id"], t(cl, "req_rejected_client", id=req_id))
        except Exception:
            pass
    await callback.answer()


@dp.message(Command("export"))
async def cmd_export(message: types.Message):
    if not is_operator(message.from_user.id):
        return
    vf = await reports.export_volunteers()
    rf = await reports.export_requests()
    await message.answer_document(FSInputFile(vf))
    await message.answer_document(FSInputFile(rf))


# ------------------------------------------------------------------ #
#  Запуск
# ------------------------------------------------------------------ #

async def main():
    await db.init_db()
    logging.info("База инициализирована. Бот запускается...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
