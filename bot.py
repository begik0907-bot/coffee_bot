import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import BOT_TOKEN, GROUP_ID, MORNING_TIME, EVENING_TIME, ADMINS
from database import init_db, add_task, complete_task, get_progress, update_stats, get_all_stats, reset_daily_tasks
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# Задачи чек-листов
MORNING_TASKS = [
    "Достать выпечку на расстойку (по 1-2 шт)",
    "Залить воду в мультиварку (для тапиоки)",
    "Замесить тесто для вафель/корндогов (если его нет)",
    "Осмотр холодильников и витрин, выставка остатков",
    "Замесить сырную шапку",
    "Приготовить выпечку",
    "Приготовить тапиоку",
    "Залить воду из термопотов в термосы"
]

EVENING_TASKS = [
    "Осмотр холодильников и витрин, выставка остатков",
    "Замесить тесто для вафель/корндогов (УБРАТЬ В ХОЛОДИЛЬНИК)",
    "Списать остатки выпечки",
    "Проверить остатки на следующую смену: Смеси, Сиропы, Десерты, и т.п.",
    "Уборка: Помыть противни, Протереть столы, Убраться при входе, Помыть посуду",
    "Залить в термопоты воду на завтра",
    "Проверить закрыты ли окна"
]

# Создание кнопок для чек-листа
def create_checklist_keyboard(tasks, progress, checklist_type):
    builder = InlineKeyboardBuilder()
    for i, task in enumerate(tasks, 1):
        completed = any(p[0] == i and p[1] == 1 for p in progress)
        status = "✅" if completed else "□"
        task_display = task[:28] + "..." if len(task) > 30 else task
        builder.button(
            text=f"{status} {i}. {task_display}",
            callback_data=f"task_{checklist_type}_{i}"
        )
    # Кнопка "Готово" вместо "Мой прогресс"
    builder.button(text="✅ ГОТОВО", callback_data=f"done_{checklist_type}")
    builder.adjust(1)
    return builder.as_markup()

# Отправка чек-листа в группу
async def send_checklist_to_group(checklist_type):
    try:
        if checklist_type == "morning":
            text = "☀️ <b>УТРЕННИЙ ЧЕК-ЛИСТ</b>\n\nКоманда, начинаем смену!\nНажмите кнопку ниже чтобы начать:"
            tasks = MORNING_TASKS
        else:
            text = "🌙 <b>ВЕЧЕРНИЙ ЧЕК-ЛИСТ</b>\n\nКоманда, завершаем смену!\nНажмите кнопку ниже чтобы начать:"
            tasks = EVENING_TASKS
        
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="📝 Начать чек-лист", callback_data=f"start_{checklist_type}")
        
        await bot.send_message(GROUP_ID, text, reply_markup=keyboard.as_markup())
        logging.info(f"{checklist_type} checklist sent to group")
    except Exception as e:
        logging.error(f"Error sending checklist: {e}")

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        f"👋 Привет, {message.from_user.username}!\n\n"
        "Я бот для чек-листов кофейни.\n"
        "Используй команды:\n"
        "/morning - Утренний чек-лист\n"
        "/evening - Вечерний чек-лист\n"
        "/stats - Статистика команды\n"
        "/help - Помощь"
    )

# Обработчик кнопки "Начать чек-лист"
@dp.callback_query(F.data.startswith("start_"))
async def start_checklist(callback: types.CallbackQuery):
    checklist_type = callback.data.split("_")[1]
    user_id = callback.from_user.id
    username = callback.from_user.username or "user"
    
    # Создаём задачи в БД
    tasks = MORNING_TASKS if checklist_type == "morning" else EVENING_TASKS
    for i in range(1, len(tasks) + 1):
        await add_task(user_id, username, checklist_type, i)
    
    progress = await get_progress(user_id, checklist_type)
    keyboard = create_checklist_keyboard(tasks, progress, checklist_type)
    
    title = "☀️ УТРЕННИЙ ЧЕК-ЛИСТ" if checklist_type == "morning" else "🌙 ВЕЧЕРНИЙ ЧЕК-ЛИСТ"
    await callback.message.edit_text(
        f"{title}\n\nСотрудник: @{username}\n"
        f"Отметь выполненные задачи:",
        reply_markup=keyboard
    )

# Обработчик нажатия на задачу
@dp.callback_query(F.data.startswith("task_"))
async def task_callback(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    checklist_type = parts[1]
    task_number = int(parts[2])
    user_id = callback.from_user.id
    username = callback.from_user.username or "user"
    
    await complete_task(user_id, checklist_type, task_number)
    progress = await get_progress(user_id, checklist_type)
    tasks = MORNING_TASKS if checklist_type == "morning" else EVENING_TASKS
    
    # Проверка завершения всех задач
    completed_count = sum(1 for p in progress if p[1] == 1)
    keyboard = create_checklist_keyboard(tasks, progress, checklist_type)
    
    await callback.message.edit_text(
        f"{'☀️ УТРЕННИЙ' if checklist_type == 'morning' else '🌙 ВЕЧЕРНИЙ'} ЧЕК-ЛИСТ\n\n"
        f"Сотрудник: @{username}\n"
        f"Выполнено: {completed_count}/{len(tasks)} ({completed_count*100//len(tasks)}%)\n\n"
        f"Отметь выполненные задачи:",
        reply_markup=keyboard
    )
    
    # Если все задачи выполнены
    if completed_count == len(tasks):
        await update_stats(user_id, username)
        await bot.send_message(
            GROUP_ID,
            f"✅ @{username} завершил {'утренний' if checklist_type == 'morning' else 'вечерний'} чек-лист!"
        )

# Обработчик /stats
@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.username not in ADMINS:
        await message.answer("❌ Только админы могут смотреть статистику")
        return
    
    stats = await get_all_stats()
    text = "📊 <b>Статистика команды</b>\n\n"
    for username, completed, last in stats:
        text += f"👤 @{username}: {completed} чек-листов (последний: {last})\n"
    
    await message.answer(text)

# Обработчик /morning
@dp.message(Command("morning"))
async def cmd_morning(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "user"
    
    for i in range(1, len(MORNING_TASKS) + 1):
        await add_task(user_id, username, "morning", i)
    
    progress = await get_progress(user_id, "morning")
    keyboard = create_checklist_keyboard(MORNING_TASKS, progress, "morning")
    
    await message.answer("☀️ <b>УТРЕННИЙ ЧЕК-ЛИСТ</b>\n\nОтметь выполненные задачи:", reply_markup=keyboard)

# Обработчик /evening
@dp.message(Command("evening"))
async def cmd_evening(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "user"
    
    for i in range(1, len(EVENING_TASKS) + 1):
        await add_task(user_id, username, "evening", i)
    
    progress = await get_progress(user_id, "evening")
    keyboard = create_checklist_keyboard(EVENING_TASKS, progress, "evening")
    
    await message.answer("🌙 <b>ВЕЧЕРНИЙ ЧЕК-ЛИСТ</b>\n\nОтметь выполненные задачи:", reply_markup=keyboard)

# Обработчик /help
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📋 <b>Команды бота:</b>\n\n"
        "/start - Запуск бота\n"
        "/morning - Утренний чек-лист\n"
        "/evening - Вечерний чек-лист\n"
        "/stats - Статистика (только админы)\n"
        "/help - Эта справка\n\n"
        "Бот автоматически отправляет чек-листы в группу утром и вечером."
    )

# Планировщик задач
async def scheduled_morning():
    await send_checklist_to_group("morning")
    await reset_daily_tasks()

async def scheduled_evening():
    await send_checklist_to_group("evening")

async def start_scheduler():
    scheduler.add_job(scheduled_morning, 'cron', hour=MORNING_TIME.split(":")[0], minute=MORNING_TIME.split(":")[1])
    scheduler.add_job(scheduled_evening, 'cron', hour=EVENING_TIME.split(":")[0], minute=EVENING_TIME.split(":")[1])
    scheduler.start()

# Запуск бота
async def main():
    await init_db()
    await start_scheduler()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
