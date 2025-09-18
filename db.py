import aiosqlite
from datetime import datetime, timedelta

DB_FILE = "files.db"

# ----------------------------
# Initialize Database
# ----------------------------
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS files (
                token TEXT PRIMARY KEY,
                file_id TEXT,
                file_name TEXT,
                file_path TEXT,
                file_size INTEGER,
                created_at DATETIME
            )
        """)
        await db.commit()

# ----------------------------
# Save New Link
# ----------------------------
async def save_link(token, file_id, file_name, file_path, file_size):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT OR REPLACE INTO files (token, file_id, file_name, file_path, file_size, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (token, file_id, file_name, file_path, file_size, datetime.now()))
        await db.commit()

# ----------------------------
# Get Link by Token
# ----------------------------
async def get_link(token):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT file_id, file_name, file_path, file_size, created_at FROM files WHERE token = ?", (token,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "file_id": row[0],
                    "file_name": row[1],
                    "file_path": row[2],
                    "file_size": row[3],
                    "created_at": row[4]
                }
    return None

# ----------------------------
# Delete Expired Links
# ----------------------------
async def delete_expired_links(hours=24):
    cutoff_time = datetime.now() - timedelta(hours=hours)
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM files WHERE created_at < ?", (cutoff_time,))
        await db.commit()
