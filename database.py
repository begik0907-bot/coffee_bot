import aiosqlite
from datetime import datetime, date

DB_NAME = "coffee_bot.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Таблица задач
        await db.execute("""
            CREATE TABLE IF NOT EXISTS checklists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                checklist_type TEXT,
                task_number INTEGER,
                completed INTEGER DEFAULT 0,
                created_date DATE DEFAULT CURRENT_DATE
            )
        """)
        
        # Таблица статистики (добавляем новые поля, если их нет)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id UNIQUE,
                username TEXT,
                morning_completed INTEGER DEFAULT 0,
                evening_completed INTEGER DEFAULT 0,
                last_completed DATE,
                last_duration_minutes INTEGER DEFAULT 0,
                avg_duration_minutes INTEGER DEFAULT 0
            )
        """)
        
        # Миграция: добавляем колонки, если они вдруг отсутствуют (для старых баз)
        try:
            await db.execute("ALTER TABLE stats ADD COLUMN last_duration_minutes INTEGER DEFAULT 0")
        except aiosqlite.OperationalError:
            pass # Колонка уже есть
            
        try:
            await db.execute("ALTER TABLE stats ADD COLUMN avg_duration_minutes INTEGER DEFAULT 0")
        except aiosqlite.OperationalError:
            pass # Колонка уже есть

        # Таблица для хранения времени старта сессии (временная)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS session_timer (
                user_id INTEGER,
                checklist_type TEXT,
                start_time TIMESTAMP,
                PRIMARY KEY (user_id, checklist_type)
            )
        """)
        
        await db.commit()

# ... (функции add_task, complete_task, get_progress остаются без изменений) ...
async def add_task(user_id, username, checklist_type, task_number):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO checklists (user_id, username, checklist_type, task_number)
            VALUES (?, ?, ?, ?)
        """, (user_id, username, checklist_type, task_number))
        await db.commit()

async def complete_task(user_id, checklist_type, task_number):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            UPDATE checklists SET completed = 1
            WHERE user_id = ? AND checklist_type = ? AND task_number = ?
        """, (user_id, checklist_type, task_number))
        await db.commit()

async def get_progress(user_id, checklist_type):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT task_number, completed FROM checklists
            WHERE user_id = ? AND checklist_type = ? AND created_date = date('now')
            ORDER BY task_number
        """, (user_id, checklist_type))
        return await cursor.fetchall()

# === НОВЫЕ ФУНКЦИИ ДЛЯ ТАЙМЕРА ===

async def start_session_timer(user_id, checklist_type):
    """Записывает время начала прохождения чек-листа"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT OR REPLACE INTO session_timer (user_id, checklist_type, start_time)
            VALUES (?, ?, ?)
        """, (user_id, checklist_type, datetime.now()))
        await db.commit()

async def get_session_duration(user_id, checklist_type):
    """Возвращает длительность сессии в минутах. Если таймер не запущен - 0"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT start_time FROM session_timer
            WHERE user_id = ? AND checklist_type = ?
        """, (user_id, checklist_type))
        row = await cursor.fetchone()
        
        if not row:
            return 0
        
        start_time = datetime.fromisoformat(row[0])
        now = datetime.now()
        duration = (now - start_time).total_seconds() / 60.0
        return int(duration)

async def clear_session_timer(user_id, checklist_type):
    """Удаляет таймер после завершения"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            DELETE FROM session_timer
            WHERE user_id = ? AND checklist_type = ?
        """, (user_id, checklist_type))
        await db.commit()

# ... (обновленная функция update_stats) ...
async def update_stats(user_id, username, checklist_type, duration_minutes):
    """Обновляет статистику с учетом времени"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT id FROM stats WHERE user_id = ?", (user_id,))
        exists = await cursor.fetchone()
        
        # Расчет нового среднего времени
        if exists:
            current_row = await db.execute("SELECT morning_completed, evening_completed, avg_duration_minutes FROM stats WHERE user_id=?", (user_id,))
            row_data = await current_row.fetchone()
            m_count, e_count, old_avg = row_data
            
            total_count = m_count + e_count
            # Новая формула среднего: ((старое_среднее * кол-во) + новое_время) / (кол-во + 1)
            new_avg = int(((old_avg * total_count) + duration_minutes) / (total_count + 1))
            
            if checklist_type == "morning":
                await db.execute("""
                    UPDATE stats SET 
                        morning_completed = morning_completed + 1,
                        last_completed = date('now'),
                        last_duration_minutes = ?,
                        avg_duration_minutes = ?
                    WHERE user_id = ?
                """, (duration_minutes, new_avg, user_id))
            else:
                await db.execute("""
                    UPDATE stats SET 
                        evening_completed = evening_completed + 1,
                        last_completed = date('now'),
                        last_duration_minutes = ?,
                        avg_duration_minutes = ?
                    WHERE user_id = ?
                """, (duration_minutes, new_avg, user_id))
        else:
            # Первый раз
            if checklist_type == "morning":
                await db.execute("""
                    INSERT INTO stats (user_id, username, morning_completed, evening_completed, last_completed, last_duration_minutes, avg_duration_minutes)
                    VALUES (?, ?, 1, 0, date('now'), ?, ?)
                """, (user_id, username, duration_minutes, duration_minutes))
            else:
                await db.execute("""
                    INSERT INTO stats (user_id, username, morning_completed, evening_completed, last_completed, last_duration_minutes, avg_duration_minutes)
                    VALUES (?, ?, 0, 1, date('now'), ?, ?)
                """, (user_id, username, duration_minutes, duration_minutes))
        
        await db.commit()

async def get_all_stats():
    async with aiosqlite.connect(DB_NAME) as db:
        # Возвращаем также last_duration и avg_duration
        cursor = await db.execute("""
            SELECT username, morning_completed, evening_completed, last_completed, last_duration_minutes, avg_duration_minutes 
            FROM stats
            ORDER BY (morning_completed + evening_completed) DESC
        """)
        return await cursor.fetchall()

async def reset_daily_tasks():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM checklists WHERE created_date < date('now')")
        # Таймеры тоже можно чистить раз в сутки, если кто-то начал и бросил
        await db.execute("DELETE FROM session_timer") 
        await db.commit()

# Функции get_incomplete_users остаются без изменений
async def get_incomplete_users(checklist_type):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT DISTINCT user_id, username FROM checklists
            WHERE checklist_type = ? 
            AND created_date = date('now')
            AND user_id NOT IN (
                SELECT user_id FROM checklists
                WHERE checklist_type = ?
                AND created_date = date('now')
                GROUP BY user_id
                HAVING COUNT(*) = 8
            )
        """, (checklist_type, checklist_type))
        return await cursor.fetchall()

async def get_incomplete_users_evening():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT DISTINCT user_id, username FROM checklists
            WHERE checklist_type = 'evening'
            AND created_date = date('now')
            AND user_id NOT IN (
                SELECT user_id FROM checklists
                WHERE checklist_type = 'evening'
                AND created_date = date('now')
                GROUP BY user_id
                HAVING COUNT(*) = 7
            )
        """)
        return await cursor.fetchall()
