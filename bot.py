import os   
from pyrogram.errors 
import logging
import asyncio
import secrets
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pyrogram import Client, filters
from pyrogram.types import Message
import urllib.parse
from pathlib import Path
import aiohttp

from config import Config

# ------------------- Logging -------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------- FastAPI app -------------------
app = FastAPI()

# ------------------- Downloads -------------------
DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)
file_storage = {}  # token -> file info

# ------------------- Channel info -------------------
CHANNEL_USERNAME = "@GBEXTREME"
CHANNEL_ID = -1002986443155

# ------------------- Helper functions -------------------
def generate_download_url(file_id: str, file_name: str, file_path: str, file_size: int) -> str:
    token = secrets.token_urlsafe(16)
    file_storage[token] = {
        'file_id': file_id,
        'file_name': file_name,
        'file_path': str(file_path),
        'file_size': file_size,
        'created_at': datetime.now()
    }
    return f"{Config.BASE_URL}/download/{token}"

async def shorten_url(long_url: str) -> str:
    try:
        tinyurl_api = f"https://tinyurl.com/api-create.php?url={urllib.parse.quote(long_url)}"
        async with aiohttp.ClientSession() as session:
            async with session.get(tinyurl_api) as response:
                if response.status == 200:
                    return (await response.text()).strip()
    except Exception as e:
        logger.error(f"URL shortening error: {e}")
    return long_url

async def cleanup_old_files():
    while True:
        await asyncio.sleep(3600)
        now = datetime.now()
        expired = []
        for token, data in file_storage.items():
            if now - data['created_at'] > timedelta(hours=24):
                try:
                    Path(data['file_path']).unlink()
                    logger.info(f"Deleted expired file: {data['file_path']}")
                except:
                    pass
                expired.append(token)
        for token in expired:
            del file_storage[token]

def create_progress_bar(percentage: float, length: int = 10) -> str:
    filled = int(length * percentage // 100)
    gradient = ['🟩', '🟢', '💚', '✅', '🌿']
    bar = ''
    for i in range(length):
        if i < filled:
            idx = min(i * len(gradient) // length, len(gradient)-1)
            bar += gradient[idx]
        else:
            bar += '⬜'
    return f"{bar} {percentage:.1f}%"

# ------------------- FastAPI endpoints -------------------
@app.get("/")
async def root():
    return {"message": "Telegram File Converter Bot is running!"}

@app.get("/download/{token}")
async def download_file(token: str):
    if token not in file_storage:
        raise HTTPException(status_code=404, detail="File not found or expired")
    file_data = file_storage[token]
    path = Path(file_data['file_path'])
    if not path.exists():
        del file_storage[token]
        raise HTTPException(status_code=404, detail="File not found")
    filename_encoded = urllib.parse.quote(file_data['file_name'])
    return FileResponse(
        path,
        filename=file_data['file_name'],
        media_type='application/octet-stream',
        headers={
            'Content-Disposition': f'attachment; filename="{filename_encoded}"',
            'X-Accel-Buffering': 'no',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    )

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "bot_started": bot_started,
        "files_count": len(file_storage),
        "timestamp": datetime.now().isoformat()
    }

# ------------------- Bot -------------------
bot = None
bot_started = False

async def notify_channel(user, file_name, file_size, short_url, long_url):
    try:
        msg = (
            f"📌 New file link created!\n\n"
            f"👤 User: {user.first_name} {user.last_name or ''} (@{user.username or 'N/A'})\n"
            f"🆔 User ID: {user.id}\n"
            f"📁 File: {file_name}\n"
            f"📦 Size: {file_size / (1024*1024):.2f} MB\n"
            f"🔗 Short URL: {short_url}\n"
            f"🌐 Direct URL: {long_url}\n"
        )
        await bot.send_message(CHANNEL_ID, msg)
    except Exception as e:
        logger.error(f"Error sending info to channel: {e}")

# ------------------- Startup -------------------
@app.on_event("startup")
async def startup_event():
    global bot, bot_started
    try:
        print("Starting bot...")
        await start_bot()  # auto-session recovery

        # ------------------- Register handlers here -------------------
        # /start, media_handler, etc.

        asyncio.create_task(cleanup_old_files())
        print("✅ Bot is fully ready!")

    except Exception as e:
        bot_started = False
        logger.error(f"Startup failed: {e}")


        # ------------------- /start handler -------------------
        @bot.on_message(filters.command("start"))
        async def start_handler(c, m: Message):
            try:
                member = await bot.get_chat_member(CHANNEL_USERNAME, m.from_user.id)
                if member.status not in ("kicked", "left"):
                    await m.reply(
                        "👋 Welcome! Send me any file and I will create a download link for you."
                    )
                else:
                    await m.reply(
                        f"👋 Hello! To use this bot, we recommend joining our channel {CHANNEL_USERNAME}.\n"
                        "After joining, just send me a file and I will create a download link for you!"
                    )
            except:
                await m.reply(
                    f"👋 Hello! To use this bot, we recommend joining our channel {CHANNEL_USERNAME}.\n"
                    "After joining, just send me a file and I will create a download link for you!"
                )

        # ------------------- Media handler -------------------
        @bot.on_message(filters.media)
        async def media_handler(c, m: Message):
            try:
                user = m.from_user
                # File info
                file_id = str(m.id)
                file_name = "file"
                if m.document:
                    file_name = m.document.file_name or "document"
                    file_size = m.document.file_size
                elif m.video:
                    file_name = m.video.file_name or "video.mp4"
                    file_size = m.video.file_size
                elif m.audio:
                    file_name = m.audio.file_name or "audio.mp3"
                    file_size = m.audio.file_size
                elif m.photo:
                    file_name = f"photo_{m.id}.jpg"
                    file_size = max(m.photo.sizes, key=lambda s: s.file_size).file_size
                else:
                    file_size = 0
                safe_filename = "".join(c for c in file_name if c.isalnum() or c in (' ', '.', '_')).rstrip()
                download_path = DOWNLOADS_DIR / f"{file_id}_{safe_filename}"

                progress_msg = await m.reply("🔄 Starting download...\n[░░░░░░░░░░] 0%")

                await bot.download_media(m, file_name=download_path)
                actual_size = download_path.stat().st_size

                long_url = generate_download_url(file_id, safe_filename, download_path, actual_size)
                await progress_msg.edit_text("🔗 Generating short URL...")
                short_url = await shorten_url(long_url)

                await progress_msg.edit_text(
                    f"✅ Download Complete!\n\n"
                    f"📁 File: {safe_filename}\n"
                    f"📦 Size: {actual_size / (1024*1024):.2f} MB\n"
                    f"🔗 Short URL: {short_url}\n"
                    f"🌐 Direct URL: {long_url}\n"
                    f"⏰ Expires in 24 hours"
                )

                # Notify channel
                await notify_channel(user, safe_filename, actual_size, short_url, long_url)

            except Exception as e:
                logger.error(f"Media handler error: {e}")
                try:
                    await m.reply("❌ Error processing file. Please try again.")
                except:
                    pass

        # ------------------- Start cleanup task -------------------
        asyncio.create_task(cleanup_old_files())

    except Exception as e:
        bot_started = False
        logger.error(f"Startup failed: {e}")

# ------------------- Shutdown -------------------
@app.on_event("shutdown")
async def shutdown_event():
    global bot, bot_started
    if bot and bot_started:
        try:
            await bot.stop()
            bot_started = False
            print("✅ Bot stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")
