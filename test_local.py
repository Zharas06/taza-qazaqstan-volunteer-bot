"""Локальный тест логики (без реального Telegram-токена)."""
import asyncio
import os
import config
config.DB_PATH = "data/test.db"

import db
from reports import export_volunteers, export_requests


async def main():
    if os.path.exists(config.DB_PATH):
        os.remove(config.DB_PATH)
    await db.init_db()

    # Регистрируем 3 волонтёров
    await db.add_volunteer(101, "Алимов Алишер", 24, "+77010000001", 47.094, 51.923)
    await db.add_volunteer(102, "Сериков Данияр", 19, "+77010000002", 47.100, 51.930)
    await db.add_volunteer(103, "Жумабаева Айгерим", 30, "+77010000003", 47.200, 52.000)

    # Заявитель создаёт заявку
    rid = await db.add_request(900, "Бабушка Мария", "+77020000001",
                               "food", "Купить продукты и лекарства",
                               "ул. Сатпаева 10, кв 5", 47.095, 51.924)
    print("Создана заявка:", rid, "(статус moderation)")

    # Оператор одобряет
    await db.set_request_status(rid, "open")
    print("После одобрения статус:", (await db.get_request(rid))["status"])

    # Проверка ближайших волонтёров
    req = await db.get_request(rid)
    print("\nРасстояния до волонтёров:")
    for v in await db.all_volunteers():
        d = db.haversine_km(v["lat"], v["lon"], req["lat"], req["lon"])
        near = "✅ в радиусе" if d <= config.NEARBY_RADIUS_KM else "❌ далеко"
        print(f"  {v['full_name']}: {d:.2f} км {near}")

    # Волонтёр берёт и выполняет
    await db.set_request_status(rid, "taken", volunteer_id=101)
    await db.set_request_status(rid, "done")
    await db.add_points(101, config.CATEGORY_POINTS["food"])
    v = await db.get_volunteer(101)
    print(f"\nПосле выполнения: {v['full_name']} — {v['points']} баллов, {v['done_count']} заявок")

    # Экспорт реестров
    vf = await export_volunteers("data/test_volunteers.xlsx")
    rf = await export_requests("data/test_requests.xlsx")
    print("\nЭкспорт:")
    print(" ", vf, os.path.getsize(vf), "байт")
    print(" ", rf, os.path.getsize(rf), "байт")
    print("\n✅ Все проверки прошли успешно.")


asyncio.run(main())
