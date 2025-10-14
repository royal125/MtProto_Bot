# ================== Imports ==================
import os
import asyncio
import logging
from datetime import datetime
from pathlib import Path
import aiohttp
import aiofiles
import urllib.parse

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import Config


# ================== Logging ==================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bot")


# ================== FastAPI ==================
app = FastAPI()


# ================== Constants ==================
CHANNEL_USERNAME = "GBEXTREME"  # users see/join this
NOTIFY_CHANNEL_ID = -1002986443155  # your channel for logs (@file2linc)
DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)

# Optional whitelist: leave empty set() to allow everyone
ALLOWED_USERS = set()  # e.g., {123456789}


# ================== Global Bot ==================
bot = Client(
    Config.SESSION_NAME,
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
)


# ================== Helpers ==================
def make_progress_bar(current: int, total: int, length: int = 10) -> str:
    if not total:
        return "⏳ Calculating..."
    pct = current / total
    filled = int(length * pct)
    return f"{'🟩' * filled}{'⬜' * (length - filled)} {pct * 100:.1f}%"


async def download_telegram_file(
    message: Message, path: Path, progress_msg: Message
) -> bool:
    """Downloads the file to a temp path with live progress."""
    try:
        await message.download(
            file_name=str(path),
            progress=lambda cur, total: asyncio.get_event_loop().create_task(
                progress_msg.edit_text(
                    f"⏬ Downloading...\n{make_progress_bar(cur, total)}\n"
                    f"{cur/1024/1024:.1f}MB / {total/1024/1024:.1f}MB"
                )
            ),
        )
        return True
    except Exception as e:
        logger.error(f"Download failed: {e}")
        try:
            await progress_msg.edit_text(f"❌ Download failed: {e}")
        except Exception:
            pass
        return False


async def upload_to_uplodash(file_path: str) -> str | None:
    """Uploads the local file to Uploda.sh and returns a share URL, or None on fail."""
    try:
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            # use normal file object so aiohttp can stream it
            form.add_field(
                "file",
                open(file_path, "rb"),
                filename=os.path.basename(file_path),
                content_type="application/octet-stream",
            )
            async with session.post("https://uploda.sh/api/upload", data=form) as resp:
                if resp.status != 200:
                    logger.warning(f"Uploda.sh HTTP {resp.status}")
                    return None
                data = await resp.json()
                if data.get("success"):
                    return data["data"]["url"]
                logger.warning(f"Uploda.sh error payload: {data}")
                return None
    except Exception as e:
        logger.error(f"Upload to Uploda.sh failed: {e}")
        return None


async def notify_channel(user, file_name: str, file_size_bytes: int, link: str):
    """Sends a log message to your channel when a link is generated."""
    try:
        name = (user.first_name or "") + (
            " " + user.last_name if user.last_name else ""
        )
        uname = f"@{user.username}" if user.username else "(no username)"
        size_mb = (file_size_bytes or 0) / (1024 * 1024)
        text = (
            "📥 <b>New Upload</b>\n\n"
            f"👤 <b>User:</b> {name.strip() or 'Unknown'} ({uname})\n"
            f"🆔 <b>User ID:</b> <code>{user.id}</code>\n\n"
            f"📁 <b>File:</b> <code>{file_name}</code>\n"
            f"📦 <b>Size:</b> {size_mb:.2f} MB\n"
            f"🔗 <b>Link:</b> {link}\n"
            f"⏰ <i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
        )
        await bot.send_message(NOTIFY_CHANNEL_ID, text, disable_web_page_preview=True)
    except Exception as e:
        logger.warning(f"notify_channel failed: {e}")


# ================== Handlers ==================
@bot.on_message(filters.command("start"))
async def start_handler(c: Client, m: Message):
    try:
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "✅ I Have Joined", callback_data="joined_ignore_check"
                    )
                ],
            ]
        )
        await m.reply_text(
            f"👋 Welcome {m.from_user.first_name}!\n\n"
            f"To use this bot, please join @{CHANNEL_USERNAME}.\n"
            f"After joining, tap <b>✅ I Have Joined</b>.",
            reply_markup=kb,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"/start error: {e}")


@bot.on_callback_query(filters.regex("^joined_ignore_check$"))
async def joined_ignore_check(c: Client, q):
    """Allow usage without re-checking membership."""
    try:
        await q.message.edit_reply_markup(None)
        await q.message.reply_text(
            "✅ Great! Now send me any file and I’ll create a Uploda.sh link for you. 🚀"
        )
        await q.answer("You may now send files.", show_alert=False)
    except Exception as e:
        logger.error(f"joined_ignore_check error: {e}")


@bot.on_message(filters.media)
async def on_media(c: Client, m: Message):
    try:
        # Optional whitelist
        if ALLOWED_USERS and m.from_user.id not in ALLOWED_USERS:
            return await m.reply_text("⚠️ Join @GBEXTREME to use this bot.")

        # Detect file meta
        file_name = (
            m.document.file_name
            if m.document
            else (
                m.video.file_name
                if m.video
                else (
                    m.audio.file_name
                    if m.audio
                    else f"photo_{m.id}.jpg" if m.photo else "file"
                )
            )
        )
        file_size = (
            m.document.file_size
            if m.document
            else (
                m.video.file_size
                if m.video
                else (
                    m.audio.file_size
                    if m.audio
                    else (m.photo.sizes[-1].file_size if m.photo else 0)
                )
            )
        )

        safe_name = (
            "".join(c for c in file_name if c.isalnum() or c in "._ ").strip() or "file"
        )
        path = DOWNLOADS_DIR / f"{m.id}_{safe_name}"

        prog = await m.reply_text("⏳ Preparing...")

        # Download from Telegram
        ok = await download_telegram_file(m, path, prog)
        if not ok:
            return

        await prog.edit_text("📤 Uploading to Uploda.sh...")

        # Upload to Uploda.sh
        link = await upload_to_uplodash(str(path))
        if not link:
            return await prog.edit_text("❌ Upload failed. Please try again later.")

        # Delete local file (free space)
        try:
            os.remove(path)
        except Exception:
            pass

        # Final response
        await prog.edit_text(
            "✅ <b>Upload Completed!</b>\n\n"
            f"📁 <b>File Name:</b> <code>{safe_name}</code>\n"
            f"📦 <b>File Size:</b> {file_size/1024/1024:.2f} MB\n\n"
            f"🔗 <b>File Link:</b> {link}\n"
            f"🔗 <b>File Link (Easy Copy):</b> {link}\n\n"
            f"📮 Join @{CHANNEL_USERNAME}",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

        # Notify your channel
        await notify_channel(m.from_user, safe_name, file_size, link)

    except Exception as e:
        logger.exception(f"on_media error: {e}")
        try:
            await m.reply_text(f"⚠️ Failed to process the file.\nError: {e}")
        except Exception:
            pass


# ================== FastAPI Routes ==================
@app.get("/")
async def root():
    return {"message": "Telegram File → Uploda.sh bot is running!"}


@app.get("/health")
async def health_check():
    return JSONResponse(
        {
            "status": "healthy",
            "bot_connected": True,
            "timestamp": datetime.now().isoformat(),
        }
    )


# ================== Startup / Shutdown ==================
@app.on_event("startup")
async def startup_event():
    try:
        logger.info("Starting bot…")
        Config.validate()
        await bot.start()
        logger.info("Bot started successfully.")
    except Exception as e:
        logger.error(f"Startup failed: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    try:
        await bot.stop()
        logger.info("Bot stopped.")
    except Exception as e:
        logger.error(f"Shutdown error: {e}")
