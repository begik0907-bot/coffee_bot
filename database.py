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
                user_id INTEGER,
                username TEXT,
                completed_checklists INTEGER DEFAULT 0,
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

async def update_stats(user_id, username):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO stats (user_id, username, completed_checklists, last_completed)
            VALUES (?, ?, 1, date('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                completed_checklists = completed_checklists + 1,
                last_completed = date('now')
        """, (user_id, username))
        await db.commit()

async def get_all_stats():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT username, completed_checklists, last_completed FROM stats
            ORDER BY completed_checklists DESC
        """)
        return await cursor.fetchall()

async def reset_daily_tasks():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM checklists WHERE created_date < date('now')")
        await db.commit()