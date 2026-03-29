import aiosqlite
from datetime import datetime, date

DB_NAME = "coffee_bot.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                username TEXT,
                morning_completed INTEGER DEFAULT 0,
                evening_completed INTEGER DEFAULT 0,
                last_completed DATE
            )
        """)
        await db.commit()

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

async def update_stats(user_id, username, checklist_type):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT id FROM stats WHERE user_id = ?
        """, (user_id,))
        exists = await cursor.fetchone()
        
        if exists:
            if checklist_type == "morning":
                await db.execute("""
                    UPDATE stats SET 
                        morning_completed = morning_completed + 1,
                        last_completed = date('now')
                    WHERE user_id = ?
                """, (user_id,))
            else:
                await db.execute("""
                    UPDATE stats SET 
                        evening_completed = evening_completed + 1,
                        last_completed = date('now')
                    WHERE user_id = ?
                """, (user_id,))
        else:
            if checklist_type == "morning":
                await db.execute("""
                    INSERT INTO stats (user_id, username, morning_completed, evening_completed, last_completed)
                    VALUES (?, ?, 1, 0, date('now'))
                """, (user_id, username))
            else:
                await db.execute("""
                    INSERT INTO stats (user_id, username, morning_completed, evening_completed, last_completed)
                    VALUES (?, ?, 0, 1, date('now'))
                """, (user_id, username))
        
        await db.commit()

async def get_all_stats():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT username, morning_completed, evening_completed, last_completed FROM stats
            ORDER BY (morning_completed + evening_completed) DESC
        """)
        return await cursor.fetchall()

async def reset_daily_tasks():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM checklists WHERE created_date < date('now')")
        await db.commit()

# Добавьте эти функции в конец database.py

async def get_incomplete_users(checklist_type):
    """Получить список пользователей кто начал но не завершил чек-лист"""
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
                HAVING COUNT(*) = 8  -- Для утреннего (8 задач)
            )
        """, (checklist_type, checklist_type))
        return await cursor.fetchall()

async def get_incomplete_users_evening():
    """Для вечернего чек-листа (7 задач)"""
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
                HAVING COUNT(*) = 7  -- Для вечернего (7 задач)
            )
        """)
        return await cursor.fetchall()
