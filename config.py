from dotenv import load_dotenv
import os

load_dotenv()

# Токен бота от @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ID группы (как получить - в инструкции ниже)
GROUP_ID = os.getenv("GROUP_ID")

# Время отправки (час:минута)
MORNING_TIME = "04:00"      # 07:00 MSK
EVENING_TIME = "09:50"      # 20:00 MSK
MORNING_REMINDER = "07:00"  # 10:00 MSK
EVENING_REMINDER = "19:00"  # 22:00 MSK

# Админы бота (username без @)
ADMINS = ["misericordiamZ", "tobaccoshopI"]
