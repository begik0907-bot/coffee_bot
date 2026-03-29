from dotenv import load_dotenv
import os

load_dotenv()

# Токен бота от @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ID группы (как получить - в инструкции ниже)
GROUP_ID = os.getenv("GROUP_ID")

# Время отправки (час:минута)
MORNING_TIME = "07:00"
EVENING_TIME = "20:00"

# Админы бота (username без @)
ADMINS = ["misericordiamZ"]