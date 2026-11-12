"""Экспорт реестров в Excel — под требования ТЗ:
- электронный реестр волонтёров (ФИО, возраст, телефон)
- электронный реестр выполненных заявок
"""
import os
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill

import config
import db
from locales import category_name

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")


def _style_header(ws, ncols):
    for col in range(1, ncols + 1):
        c = ws.cell(row=1, column=col)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = Alignment(horizontal="center", vertical="center")


async def export_volunteers(path="data/реестр_волонтёров.xlsx"):
    vols = await db.all_volunteers()
    wb = Workbook()
    ws = wb.active
    ws.title = "Волонтёры"
    headers = ["№", "ФИО", "Возраст", "Телефон", "Баллы", "Выполнено заявок", "Дата регистрации"]
    ws.append(headers)
    _style_header(ws, len(headers))
    for i, v in enumerate(vols, 1):
        ws.append([i, v["full_name"], v["age"], v["phone"],
                   v["points"], v["done_count"], v["registered_at"][:10]])
    widths = [5, 30, 9, 16, 8, 17, 18]
    for col, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + col)].width = w
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb.save(path)
    return path


async def export_requests(path="data/реестр_заявок.xlsx"):
    reqs = await db.all_requests()
    wb = Workbook()
    ws = wb.active
    ws.title = "Заявки"
    headers = ["№ заявки", "Заявитель", "Телефон", "Категория", "Описание",
               "Адрес", "Статус", "ID волонтёра", "Создана", "Закрыта"]
    ws.append(headers)
    _style_header(ws, len(headers))
    status_ru = {"moderation": "На модерации", "open": "Открыта",
                 "taken": "В работе", "await_confirm": "Ждёт подтверждения",
                 "done": "Выполнена", "rejected": "Отклонена"}
    for r in reqs:
        ws.append([
            r["id"], r["client_name"], r["client_phone"],
            category_name("ru", r["category"]),
            r["description"], r["address"],
            status_ru.get(r["status"], r["status"]),
            r["volunteer_id"] or "", r["created_at"][:16].replace("T", " "),
            (r["closed_at"] or "")[:16].replace("T", " "),
        ])
    widths = [9, 22, 16, 28, 35, 30, 14, 12, 18, 18]
    for col, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + col)].width = w
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb.save(path)
    return path
