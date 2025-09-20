# bot.py
import os
import logging
import asyncio
import secrets
from datetime import datetime, timedelta
from pathlib import Path
import urllib.parse
import aiofiles
import aiohttp

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI()

# Downloads folder
DOWNLOADS_DIR = Path(__file__).parent / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

# File storage in-memory
file_storage = {}

# Global MTProto client
client = None
client_started = False

# Thread pool for parallel tasks
thread_pool = asyncio.get_event_loop()

# ----------------- UTILITIES -----------------

def generate_download_url(file_id: str, file_name: str, file_path: str, file_size: int) -> str:
    token = secrets.token_urlsafe(16)
    file_storage[token] = {
        "file_id": file_id,
        "file_name": file_name,
        "file_path": str(file_path),
        "file_size": file_size,
        "created_at": datetime.now()
    }
    return f"{Config.BASE_URL}/download/{token}"


async def shorten_url(long_url: str) -> str:
    """Shorten URL using TinyURL API"""
    try:
        tinyurl_api = f"https://tinyurl.com/api-create.php?url={urllib.parse.quote(long_url)}"
        async with aiohttp.ClientSession() as session:
            async with session.get(tinyurl_api) as response:
                if response.status == 200:
                    return (await response.text()).strip()
                else:
                    return long_url
    except:
        return long_url


def create_progress_bar(percentage: float, length: int = 10) -> str:
    """Visual progress bar with green gradient"""
    filled_length = int(length * percentage // 100)
    gradient = ['🟩', '🟢', '💚', '✅', '🌿']
    bar = ''
    for i in range(length):
        if i < filled_length:
            emoji_index = min(i * len(gradient) // length, len(gradient) - 1)
            bar += gradient[emoji_index]
        else:
            bar += "⬜"
    return f"{bar} {percentage:.1f}%"


async def cleanup_old_files():
    """Remove expired files older than 24 hours"""
    while True:
        await asyncio.sleep(3600)
        now = datetime.now()
        expired = []
        for token, data in file_storage.items():
            if now - data["created_at"] > timedelta(hours=24):
                expired.append(token)
                path = Path(data["file_path"])
                if path.exists():
                    try:
                        path.unlink()
                        logger.info(f"Deleted expired file: {path}")
                    except:
                        pass
        for token in expired:
            del file_storage[token]


# ----------------- FASTAPI ROUTES -----------------

@app.get("/")
async def root():
    return {"message": "MTProto Telegram File Converter Bot is running!"}


@app.get("/download/{token}")
async def download_file(token: str):
    if token not in file_storage:
        raise HTTPException(status_code=404, detail="File not found or link expired")
    file_data = file_storage[token]
    file_path = Path(file_data["file_path"]).resolve()
    if not file_path.exists():
        del file_storage[token]
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=file_path,
        filename=file_data["file_name"],
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{file_data["file_name"]}"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )


@app.get("/health")
async def health_check():
    status = "disconnected"
    if client and client_started:
        status = "connected"
    return JSONResponse({
        "status": "healthy",
        "client_status": status,
        "files_count": len(file_storage),
        "timestamp": datetime.now().isoformat()
    })


# ----------------- MTProto STARTUP -----------------

@app.on_event("startup")
async def startup_event():
    global client, client_started

    Config.validate()
    session_name = Config.SESSION_NAME + "_user"  # Ensure fresh user session

    client = Client(
        session_name,
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        phone_number=Config.PHONE_NUMBER  # From .env, MTProto login
    )

    # Start MTProto client
    await client.start()
    client_started = True
    me = await client.get_me()
    logger.info(f"MTProto client started as @{me.username}")

    # Register /start command
    @client.on_message(filters.command("start"))
    async def start_handler(c, m: Message):
        await m.reply(
            "👋 Hello! Send me any file and I'll give you a download URL.\n"
            "⚡ Progress tracking\n"
            "🔗 Short URLs\n"
            "📁 Supported files: All types\n"
            "⏰ Links expire in 24 hours"
        )

    # Register media handler
    @client.on_message(filters.media)
    async def media_handler(c, m: Message):
        try:
            if not m.media:
                return

            file_id = str(m.id)
            file_name = "file"

            if m.document:
                file_name = m.document.file_name or "document"
            elif m.video:
                file_name = m.video.file_name or "video.mp4"
            elif m.audio:
                file_name = m.audio.file_name or "audio.mp3"
            elif m.photo:
                file_name = f"photo_{m.id}.jpg"

            safe_filename = "".join(c for c in file_name if c.isalnum() or c in (' ', '.', '_')).rstrip()
            download_path = DOWNLOADS_DIR / f"{file_id}_{safe_filename}"

            progress_msg = await m.reply("🔄 Starting download...\n[░░░░░░░░░░] 0%")
            # Download the file
            await client.download_media(m, file_name=download_path)

            actual_size = download_path.stat().st_size
            long_url = generate_download_url(file_id, safe_filename, download_path, actual_size)
            await progress_msg.edit_text("🔗 Generating short URL...")
            short_url = await shorten_url(long_url)

            await progress_msg.edit_text(
                f"✅ Download Complete!\n\n"
                f"📁 {safe_filename}\n"
                f"📦 {actual_size / (1024*1024):.2f} MB\n"
                f"🔗 Short URL: {short_url}\n"
                f"🌐 Direct URL: {long_url}\n"
                f"⏰ Expires in 24 hours"
            )
        except Exception as e:
            logger.error(f"Media handler error: {e}")
            await m.reply("❌ Error processing file. Please try again.")


    # Start cleanup task
    asyncio.create_task(cleanup_old_files())
    logger.info("✅ Cleanup task started")


# ----------------- SHUTDOWN -----------------

@app.on_event("shutdown")
async def shutdown_event():
    global client, client_started
    if client and client_started:
        await client.stop()
        client_started = False
        logger.info("MTProto client stopped")
