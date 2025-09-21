# ================== Imports ==================
import os
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
import aiohttp
import aiofiles
import secrets
import urllib.parse

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import Config


# ================== Logging ==================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("bot")


# ================== FastAPI ==================
app = FastAPI()


# ================== Constants ==================
CHANNEL_USERNAME = "GBEXTREME"        # Channel/group username
CHANNEL_ID = -1002986443155           # Channel ID (for notifications)
DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)


# ================== Global Bot ==================
bot = Client(
    Config.SESSION_NAME,
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)


# ================== File Storage ==================
file_storage = {}


# ================== Helper Functions ==================
async def shorten_url(long_url: str) -> str:
    try:
        api = f"https://is.gd/create.php?format=simple&url={urllib.parse.quote(long_url)}"
        async with aiohttp.ClientSession() as session:
            async with session.get(api) as response:
                if response.status == 200:
                    return (await response.text()).strip()
    except Exception as e:
        logger.error(f"URL shortening failed: {e}")
    return long_url



def generate_download_url(file_id, file_name, file_path, file_size):
    """Generate secure download link with token."""
    token = secrets.token_urlsafe(16)
    file_storage[token] = {
        "file_id": file_id,
        "file_name": file_name,
        "file_path": str(file_path),
        "file_size": file_size,
        "created_at": datetime.now()
    }
    return f"{Config.BASE_URL}/download/{token}"

# ================== Progress Bar ==================

def make_progress_bar(current, total, length=8):
    if total == 0:
        return "⏳ Calculating..."
    percent = current / total
    filled = int(length * percent)
    empty = length - filled
    bar = "🟩" * filled + "⬜" * empty
    return f"{bar} {percent*100:.1f}%"

async def cleanup_old_files():
    while True:
        await asyncio.sleep(30)  # check every 30 seconds
        now = datetime.now()
        expired = []

        for token, data in list(file_storage.items()):
            # delete after 1 minute (for testing)
            if now - data["created_at"] > timedelta(hours=18):
                expired.append(token)
                try:
                    Path(data["file_path"]).unlink(missing_ok=True)
                    logger.info(f"🗑 Deleted expired file: {data['file_path']}")
                except Exception as e:
                    logger.error(f"❌ Failed to delete {data['file_path']}: {e}")

        for t in expired:
            file_storage.pop(t, None)

        if expired:
            logger.info(f"✅ Cleaned {len(expired)} expired files")




async def notify_channel(user, file_name, file_size, short_url, long_url):
    try:
        if not user:
            user_info = "👤 Unknown user (maybe forwarded or from a channel)"
        else:
            user_info = (
                f"👤 User: {user.first_name or ''} {user.last_name or ''}\n"
                f"🆔 User ID: {user.id}\n"
                f"{'📛 Username: @' + user.username if user.username else ''}"
            )

        file_info = (
            f"\n\n📁 File: {file_name}\n"
            f"📦 Size: {file_size / (1024*1024):.2f} MB\n"
            f"🔗 Short URL: {short_url}\n"
            f"🌐 Direct URL: {long_url}"
        )

        await bot.send_message(CHANNEL_ID, f"{user_info}{file_info}")

    except Exception as e:
        logger.error(f"Notify channel failed: {e}")



# --- /start command ---
@bot.on_message(filters.command("start"))
async def start_handler(c, m: Message):
    try:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME}")],
            [InlineKeyboardButton("✅ I Have Joined", callback_data="check_joined")]
        ])

        await m.reply_animation(
            animation="https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExMmxxcTRlcnVvejV4ejY3bmhmcDZvc2ljeWw4NnR0ZXIzODB5NGZ0eCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9cw/MTMleN1MQMYYoxJVMY/giphy.gif",
            caption=(
                f"👋 Welcome {m.from_user.first_name}!\n\n"
                f"To use this bot, please join @{CHANNEL_USERNAME}.\n\n"
                "After joining, click **✅ I Have Joined**."
            ),
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Start handler error: {e}")


# --- "I Have Joined" button ---
@bot.on_callback_query(filters.regex("check_joined"))
async def confirm_join(c, query):
    try:
        # Remove old buttons
        await query.message.edit_reply_markup(None)

        # Reply to user
        await query.message.reply(
            "✅Oh, great 😊! Now send me a file and I will create a secure download link for you."
        )

        # Answer callback so button tap feels responsive
        await query.answer("You may now send files 🚀", show_alert=False)

    except Exception as e:
        logger.error(f"Join confirm button error: {e}")



# --- Media handler ---
@bot.on_message(filters.media)
async def media_handler(c, m: Message):
    try:
        import os
        from datetime import datetime

        user = m.from_user
        file_id = str(m.id)

        # --- Detect file name & size ---
        if m.photo:
            # Telegram compresses photos, no original filename → save as jpg
            file_name = f"photo_{m.id}.jpg"
            file_size = m.photo.file_size

        elif m.document:
            file_name = m.document.file_name or "document"
            file_size = m.document.file_size

            # ✅ If file is an image (jpg or png), keep extension
            if file_name.lower().endswith(".jpg") or file_name.lower().endswith(".jpeg"):
                file_name = f"image_{m.id}.jpg"
            elif file_name.lower().endswith(".png"):
                file_name = f"image_{m.id}.png"

        elif m.video:
            file_name = m.video.file_name or "video.mp4"
            file_size = m.video.file_size

        elif m.audio:
            file_name = m.audio.file_name or "audio.mp3"
            file_size = m.audio.file_size

        else:
            file_name = f"file_{m.id}"
            file_size = 0

        # --- Safe filename ---
        safe_filename = "".join(ch for ch in file_name if ch.isalnum() or ch in (" ", ".", "_")).rstrip()

        # --- Downloads folder ---
        base_dir = os.path.join(os.getcwd(), "downloads")
        os.makedirs(base_dir, exist_ok=True)
        download_path = os.path.join(base_dir, f"{file_id}_{safe_filename}")

        # --- Progress message ---
        progress_msg = await m.reply("📥 Starting download...")
        start_time = datetime.now()

        async def progress(current, total):
            try:
                bar = make_progress_bar(current, total)
                elapsed = (datetime.now() - start_time).seconds
                speed = current / elapsed if elapsed > 0 else 0
                await progress_msg.edit_text(
                    f"📥 Downloading...\n"
                    f"{bar}\n"
                    f"{current//(1024*1024):.2f} MB / {total//1024*1024} MB\n"
                    f"⚡ {speed/(1024*1024):.2f} MB/s"
                )
            except Exception:
                pass

        # --- Download file ---
        await bot.download_media(m, file_name=str(download_path), progress=progress)

        # --- Validate file exists ---
        if not os.path.exists(download_path):
            raise FileNotFoundError(f"File not found at {download_path}")

        actual_size = os.path.getsize(download_path)

        # --- Generate links ---
        long_url = generate_download_url(file_id, safe_filename, download_path, actual_size)
        await progress_msg.edit_text("🔗 Generating short URL...")
        short_url = await shorten_url(long_url)

        # --- Success message ---
        await progress_msg.edit_text(
            f"✅ Download Complete!\n\n"
            f"📁 File: {safe_filename}\n"
            f"📦 Size: {actual_size / (1024*1024):.2f} MB\n"
            f"🔗 Short URL: {short_url}\n"
            f"🌐 Direct URL: {long_url}\n"
            f"⏰ Expires in 24 hours"
        )

        # --- Notify channel ---
        try:
            await notify_channel(user, safe_filename, actual_size, short_url, long_url)
        except Exception as e:
            logger.error(f"[media_handler] notify_channel failed: {e}")

    except Exception as e:
        logger.exception(f"Media handler error: {e}")
        await m.reply(f"⚠️ Failed to process the file.\nError: {e}")




        

# ================== FastAPI Routes ==================
@app.get("/")
async def root():
    return {"message": "Telegram File Converter Bot is running!"}


@app.get("/download/{token}")
async def download_file(token: str):
    if token not in file_storage:
        raise HTTPException(status_code=404, detail="File not found or expired")
    data = file_storage[token]
    path = Path(data["file_path"])
    if not path.exists():
        file_storage.pop(token, None)
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=data["file_name"], media_type="application/octet-stream")


@app.get("/health")
async def health_check():
    return JSONResponse({
        "status": "healthy",
        "bot_started": True,
        "files_count": len(file_storage),
        "timestamp": datetime.now().isoformat()
    })


# ================== Startup / Shutdown ==================
@app.on_event("startup")
async def startup_event():
    try:
        print("🚀 Starting bot...")
        Config.validate()
        await bot.start()
        asyncio.create_task(cleanup_old_files())
        print("✅ Bot is fully ready!")
    except Exception as e:
        logger.error(f"Startup failed: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    try:
        await bot.stop()
        print("✅ Bot stopped successfully")
    except Exception as e:
        logger.error(f"Shutdown error: {e}")
