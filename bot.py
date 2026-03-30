import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import BOT_TOKEN, GROUP_ID, MORNING_TIME, EVENING_TIME, ADMINS
from database import (
    init_db, add_task, complete_task, get_progress, 
    update_stats, get_all_stats, reset_daily_tasks, 
    get_incomplete_users, get_incomplete_users_evening, DB_NAME
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и планировщика
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# === ЗАДАЧИ ЧЕК-ЛИСТОВ ===
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

# === КЛАВИАТУРЫ ===
def create_checklist_keyboard(tasks, progress, checklist_type):
    builder = InlineKeyboardBuilder()
    for i, task in enumerate(tasks, 1):
        completed = any(p[0] == i and p[1] == 1 for p in progress)
        status = "✅" if completed else "□"
        # Обрезаем длинный текст для кнопок
        task_display = task[:28] + "..." if len(task) > 30 else task
        builder.button(
            text=f"{status} {i}. {task_display}",
            callback_data=f"task_{checklist_type}_{i}"
        )
    
    builder.button(text="✅ ГОТОВО", callback_data=f"done_{checklist_type}")
    builder.adjust(1)
    return builder.as_markup()

# === ОТПРАВКА ЧЕК-ЛИСТОВ ===
async def send_checklist_to_group(checklist_type):
    try:
        if checklist_type == "morning":
            text = "☀️ <b>ПОДГОТОВКА К ОТКРЫТИЮ</b>\n\nКоманда, начинаем смену!\nНажмите кнопку ниже чтобы начать:"
        else:
            text = "🌙 <b>ПОДГОТОВКА К ЗАКРЫТИЮ</b>\n\nКоманда, завершаем смену!\nНажмите кнопку ниже чтобы начать:"
        
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="📝 Начать чек-лист", callback_data=f"start_{checklist_type}")
        
        await bot.send_message(
            GROUP_ID,
            text,
            reply_markup=keyboard.as_markup(),
            disable_notification=True
        )
        logging.info(f"{checklist_type} checklist sent to group")
    except Exception as e:
        logging.error(f"Error sending checklist: {e}")

# === ОБРАБОТЧИКИ КОМАНД ===
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

@dp.callback_query(F.data.startswith("start_"))
async def start_checklist(callback: types.CallbackQuery):
    checklist_type = callback.data.split("_")[1]
    user_id = callback.from_user.id
    username = callback.from_user.username or "user"
    
    # Запускаем таймер! ⏱️
    from database import start_session_timer
    await start_session_timer(user_id, checklist_type)

    # ... остальной код создания задач и отправки сообщения (без изменений) ...
    tasks = MORNING_TASKS if checklist_type == "morning" else EVENING_TASKS
    for i in range(1, len(tasks) + 1):
        await add_task(user_id, username, checklist_type, i)
    
    progress = await get_progress(user_id, checklist_type)
    keyboard = create_checklist_keyboard(tasks, progress, checklist_type)
    
    title = "☀️ ПОДГОТОВКА К ОТКРЫТИЮ" if checklist_type == "morning" else "🌙 ПОДГОТОВКА К ЗАКРЫТИЮ"
    
    try:
        await bot.send_message(
            user_id,
            f"{title}\n\nСотрудник: @{username}\nОтметь выполненные задачи:",
            reply_markup=keyboard
        )
        await callback.message.delete()
        await callback.answer(f"✅ Чек-лист отправлен в ЛС!", show_alert=False)
    except Exception as e:
        # ... (код обработки ошибки без изменений) ...
        logging.warning(f"Не удалось отправить ЛС пользователю @{username}: {e}")
        await callback.message.delete()
        await bot.send_message(
            GROUP_ID,
            f"⚠️ <b>@{username}</b>, вы еще не запустили бота!\n\nПожалуйста, перейдите в личные сообщения с ботом и нажмите <b>/start</b>.",
            disable_notification=False
        )
        await callback.answer("❌ Сначала нажмите /start в ЛС с ботом!", show_alert=True)
# === ОБРАБОТКА ЗАДАЧ ===
@dp.callback_query(F.data.startswith("task_"))
async def task_callback(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    checklist_type = parts[1]
    task_number = int(parts[2])
    user_id = callback.from_user.id
    username = callback.from_user.username or "user"
    
    progress = await get_progress(user_id, checklist_type)
    is_completed = any(p[0] == task_number and p[1] == 1 for p in progress)
    
    if is_completed:
        await callback.answer("✅ Уже выполнено!", show_alert=False)
        return
    
    await complete_task(user_id, checklist_type, task_number)
    progress = await get_progress(user_id, checklist_type)
    
    tasks = MORNING_TASKS if checklist_type == "morning" else EVENING_TASKS
    completed_count = sum(1 for p in progress if p[1] == 1)
    total_tasks = len(tasks)
    percent = int(completed_count * 100 / total_tasks)
    
    keyboard = create_checklist_keyboard(tasks, progress, checklist_type)
    title = "☀️ ПОДГОТОВКА К ОТКРЫТИЮ" if checklist_type == "morning" else "🌙 ПОДГОТОВКА К ЗАКРЫТИЮ"
    
    new_text = (
        f"{title}\n\n"
        f"Сотрудник: @{username}\n"
        f"Выполнено: {completed_count}/{total_tasks} ({percent}%)\n\n"
        f"Отметь выполненные задачи:"
    )
    
    try:
        await callback.message.edit_text(new_text, reply_markup=keyboard)
    except Exception:
        # Игнорируем ошибку, если сообщение не изменилось или удалено
        pass
    
    await callback.answer(f"✅ Задача {task_number} выполнена!", show_alert=False)

@dp.callback_query(F.data.startswith("done_"))
async def done_callback(callback: types.CallbackQuery):
    checklist_type = callback.data.split("_")[1]
    user_id = callback.from_user.id
    username = callback.from_user.username or "user"
    
    progress = await get_progress(user_id, checklist_type)
    tasks = MORNING_TASKS if checklist_type == "morning" else EVENING_TASKS
    completed_count = sum(1 for p in progress if p[1] == 1)
    
    if completed_count == len(tasks):
        # ⏱️ Считаем время прохождения
        from database import get_session_duration, clear_session_timer
        duration = await get_session_duration(user_id, checklist_type)
        await clear_session_timer(user_id, checklist_type)
        
        # Обновляем статистику с временем
        await update_stats(user_id, username, checklist_type, duration)
        
        # Формируем сообщение о времени
        time_msg = f"⏱️ Время прохождения: {duration} мин."
        if duration > 60:
            hours = duration // 60
            mins = duration % 60
            time_msg = f"⏱️ Время прохождения: {hours} ч. {mins} мин."
        
        await callback.message.edit_text(
            f"{'☀️ УТРЕННИЙ' if checklist_type == 'morning' else '🌙 ВЕЧЕРНИЙ'} ЧЕК-ЛИСТ\n\n"
            f"Сотрудник: @{username}\n"
            f"✅ <b>ВСЕ ЗАДАЧИ ВЫПОЛНЕНЫ!</b>\n"
            f"Прогресс: {completed_count}/{len(tasks)} (100%)\n"
            f"{time_msg}\n\n"
            f"Молодец! 🎉",
        )
        
        await bot.send_message(
            GROUP_ID,
            f"✅ @{username} завершил {'утренний' if checklist_type == 'morning' else 'вечерний'} чек-лист за {duration} мин.!",
            disable_notification=True
        )
        await callback.answer("🎉 Чек-лист завершен!", show_alert=False)
    else:
        await callback.answer(
            f"⚠️ Сначала выполните все задачи!\nВыполнено: {completed_count}/{len(tasks)}",
            show_alert=True
        )

# === СТАТИСТИКА И АДМИНСТВО ===
@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.username not in ADMINS:
        await message.answer("❌ Только админы могут смотреть статистику")
        return
    
    stats = await get_all_stats()
    text = "📊 <b>Статистика команды</b>\n\n"
    
    for username, morning, evening, last, last_dur, avg_dur in stats:
        total = morning + evening
        
        # Форматирование времени
        last_time_str = f"{last_dur} мин."
        if last_dur > 60:
            last_time_str = f"{last_dur//60}ч {last_dur%60}мин"
            
        avg_time_str = f"{avg_dur} мин."
        if avg_dur > 60:
            avg_time_str = f"{avg_dur//60}ч {avg_dur%60}мин"
        
        text += f"👤 @{username}\n"
        text += f"   ☀️ Утренние: {morning} | 🌙 Вечерние: {evening}\n"
        text += f"   📈 Всего: {total}\n"
        text += f"   ⏱️ Последнее время: {last_time_str}\n"
        text += f"   📊 Среднее время: {avg_time_str}\n"
        text += f"   🕐 Последний раз: {last}\n\n"
    
    await message.answer(text)

@dp.message(Command("reset_stats"))
async def cmd_reset_stats(message: types.Message):
    if message.from_user.username not in ADMINS:
        await message.answer("❌ Только админы!")
        return
    
    # Используем DB_NAME из импорта
    import aiosqlite
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM stats")
        await db.execute("DELETE FROM checklists")
        await db.commit()
    
    await message.answer("✅ Статистика сброшена!")

@dp.message(Command("morning"))
async def cmd_morning(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "user"
    
    for i in range(1, len(MORNING_TASKS) + 1):
        await add_task(user_id, username, "morning", i)
    
    progress = await get_progress(user_id, "morning")
    keyboard = create_checklist_keyboard(MORNING_TASKS, progress, "morning")
    await message.answer("☀️ <b>УТРЕННИЙ ЧЕК-ЛИСТ</b>\n\nОтметь выполненные задачи:", reply_markup=keyboard)

@dp.message(Command("evening"))
async def cmd_evening(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "user"
    
    for i in range(1, len(EVENING_TASKS) + 1):
        await add_task(user_id, username, "evening", i)
    
    progress = await get_progress(user_id, "evening")
    keyboard = create_checklist_keyboard(EVENING_TASKS, progress, "evening")
    await message.answer("🌙 <b>ВЕЧЕРНИЙ ЧЕК-ЛИСТ</b>\n\nОтметь выполненные задачи:", reply_markup=keyboard)

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

# === НАПОМИНАНИЯ ===
async def send_reminder(checklist_type, incomplete_users):
    if checklist_type == "morning":
        text = "⚠️ <b>НАПОМИНАНИЕ</b>\n\nВы не завершили утренний чек-лист!\nПожалуйста, пройдите его как можно скорее.\n\nИспользуйте команду /morning"
        time_text = "10:00"
    else:
        text = "⚠️ <b>НАПОМИНАНИЕ</b>\n\nВы не завершили вечерний чек-лист!\nПожалуйста, пройдите его перед уходом.\n\nИспользуйте команду /evening"
        time_text = "22:00"
    
    for user_id, username in incomplete_users:
        try:
            await bot.send_message(user_id, text, disable_notification=False)
            logging.info(f"Reminder sent to @{username}")
        except Exception as e:
            logging.error(f"Failed to send reminder to {username}: {e}")
    
    if incomplete_users:
        users_text = "\n".join([f"• @{u[1]}" for u in incomplete_users])
        await bot.send_message(
            GROUP_ID,
            f"⚠️ <b>Не прошли чек-лист ({time_text}):</b>\n\n{users_text}",
            disable_notification=True
        )

async def scheduled_morning():
    await send_checklist_to_group("morning")
    await reset_daily_tasks()

async def scheduled_evening():
    await send_checklist_to_group("evening")

async def scheduled_morning_reminder():
    incomplete = await get_incomplete_users("morning")
    if incomplete:
        await send_reminder("morning", incomplete)

async def scheduled_evening_reminder():
    incomplete = await get_incomplete_users_evening()
    if incomplete:
        await send_reminder("evening", incomplete)

async def start_scheduler():
    scheduler.add_job(scheduled_morning, 'cron', hour=MORNING_TIME.split(":")[0], minute=MORNING_TIME.split(":")[1])
    scheduler.add_job(scheduled_evening, 'cron', hour=EVENING_TIME.split(":")[0], minute=EVENING_TIME.split(":")[1])
    scheduler.add_job(scheduled_morning_reminder, 'cron', hour=7, minute=0)
    scheduler.add_job(scheduled_evening_reminder, 'cron', hour=19, minute=0)
    scheduler.start()

@dp.message(Command("test_reminder"))
async def cmd_test_reminder(message: types.Message):
    if message.from_user.username not in ADMINS:
        return
    incomplete = await get_incomplete_users("morning")
    if incomplete:
        await send_reminder("morning", incomplete)
        await message.answer(f"✅ Напоминание отправлено {len(incomplete)} пользователям")
    else:
        await message.answer("✅ Все прошли утренний чек-лист!")

# === ЗАПУСК ===
async def main():
    await init_db()
    await start_scheduler()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
