"""Конфигурация бота «109: Volunteers»."""
import os

# Загружаем переменные из файла .env (если он есть)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv не установлен — берём переменные из окружения

# Токен берётся из .env или переменной окружения BOT_TOKEN (получить у @BotFather)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# ID операторов/модераторов (Telegram user_id через запятую в OPERATOR_IDS)
OPERATOR_IDS = [
    int(x) for x in os.getenv("OPERATOR_IDS", "").split(",") if x.strip().isdigit()
]

# Путь к базе данных
DB_PATH = os.getenv("DB_PATH", "data/volunteers109.db")

# Возрастные рамки волонтёров по ТЗ
VOLUNTEER_MIN_AGE = 14
VOLUNTEER_MAX_AGE = 34

# Названия категорий хранятся в locales.py (двуязычные).
# Здесь — только ключи и баллы.

# Баллы за выполненную заявку (по категориям)
CATEGORY_POINTS = {
    "food": 10,
    "clean": 15,
    "repair": 20,
    "emergency": 25,
}

# Радиус, в котором волонтёру показываются «ближайшие» заявки (км)
NEARBY_RADIUS_KM = 10.0
