import os
import logging
import asyncio
import secrets
from datetime import datetime, timedelta
from pathlib import Path
import urllib.parse
import aiofiles
import aiohttp
import concurrent.futures

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import Config

# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ----------------------------
# FastAPI app
# ----------------------------
app = FastAPI()

# ----------------------------
# Directories & storage
# ----------------------------
DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)
file_storage = {}
allowed_users = set()  # Users allowed to bypass group check

# ----------------------------
# Thread pool
# ----------------------------
thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=10)

# ----------------------------
# Bot instance
# ----------------------------
bot = None
bot_started = False

# ----------------------------
# Utilities
# ----------------------------
async def check_group_subscription(user_id: int) -> bool:
    """Check if user is member of the required group"""
    try:
        group_username = "GBEXTREME"  # Without '@'
        member = await bot.get_chat_member(group_username, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Group subscription check error: {e}")
        return False

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

async def send_download_notification(file_name: str, file_size: int, download_url: str, user_info: str):
    """Send notification to channel when someone gets a download link"""
    try:
        channel_id = -1002986443155  # Your channel ID
        
        message_text = (
            f"📥 **New Download Generated**\n\n"
            f"📁 **File:** `{file_name}`\n"
            f"📦 **Size:** {file_size / (1024*1024):.2f} MB\n"
            f"👤 **User:** {user_info}\n"
            f"🔗 **Download URL:** {download_url}\n"
            f"⏰ **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        await bot.send_message(channel_id, message_text)
        logger.info(f"Download notification sent for {file_name}")
        
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")

async def shorten_url(long_url: str) -> str:
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
    filled_length = int(length * percentage // 100)
    gradient = ['🟩', '🟢', '💚', '✅', '🌿']
    bar = ''
    for i in range(length):
        if i < filled_length:
            emoji_index = min(i * len(gradient) // length, len(gradient) - 1)
            bar += gradient[emoji_index]
        else:
            bar += '⬜'
    return f"{bar} {percentage:.1f}%"

def format_eta(time_elapsed: float, downloaded: int, total_size: int) -> str:
    if downloaded == 0: return "Calculating..."
    remaining_bytes = total_size - downloaded
    download_speed = downloaded / time_elapsed if time_elapsed > 0 else 0
    seconds_remaining = remaining_bytes / download_speed if download_speed > 0 else 0
    if seconds_remaining < 60:
        return f"{int(seconds_remaining)}s"
    elif seconds_remaining < 3600:
        return f"{int(seconds_remaining // 60)}m {int(seconds_remaining % 60)}s"
    else:
        return f"{int(seconds_remaining // 3600)}h {int((seconds_remaining % 3600) // 60)}m"

# ----------------------------
# File download
# ----------------------------
async def download_telegram_file(message: Message, download_path: Path, progress_message: Message) -> bool:
    try:
        chunk_size = 524288  # 512KB
        downloaded = 0
        start_time = datetime.now()
        total_size = 0
        if message.document:
            total_size = message.document.file_size
        elif message.video:
            total_size = message.video.file_size
        elif message.audio:
            total_size = message.audio.file_size
        elif message.photo:
            total_size = max(message.photo.sizes, key=lambda s: s.file_size).file_size
        last_update_time = datetime.now()
        async with aiofiles.open(download_path, 'wb') as f:
            async for chunk in bot.stream_media(message, limit=chunk_size):
                await f.write(chunk)
                downloaded += len(chunk)
                current_time = datetime.now()
                if (current_time - last_update_time).total_seconds() >= 2 or downloaded == total_size:
                    if total_size > 0:
                        percentage = (downloaded / total_size) * 100
                        progress_bar = create_progress_bar(percentage)
                        time_elapsed = (current_time - start_time).total_seconds()
                        download_speed = (downloaded / 1024) / time_elapsed if time_elapsed > 0 else 0
                        try:
                            await progress_message.edit_text(
                                f"📥 **Downloading...**\n\n{progress_bar}\n\n"
                                f"**Progress:** {downloaded//1024}KB / {total_size//1024}KB\n"
                                f"**Speed:** {download_speed:.1f}KB/s\n"
                                f"**ETA:** {format_eta(time_elapsed, downloaded, total_size)}"
                            )
                        except: pass
                        last_update_time = current_time
        return True
    except Exception as e:
        logger.error(f"Download error: {e}")
        if download_path.exists(): download_path.unlink()
        return False

# ----------------------------
# FastAPI routes
# ----------------------------
@app.get("/")
async def root():
    return {"message": "Telegram File Converter Bot is running!"}

@app.get("/download/{token}")
async def download_file(token: str):
    if token not in file_storage: raise HTTPException(status_code=404, detail="File not found or expired")
    data = file_storage[token]
    path = Path(data['file_path'])
    if not path.exists(): del file_storage[token]; raise HTTPException(status_code=404, detail="File not found")
    filename_encoded = urllib.parse.quote(data['file_name'])
    return FileResponse(path=path, filename=data['file_name'], media_type='application/octet-stream',
                        headers={'Content-Disposition': f'attachment; filename="{filename_encoded}"',
                                 'Cache-Control': 'no-cache, no-store, must-revalidate'})

# ----------------------------
# Bot startup
# ----------------------------
@app.on_event("startup")
async def startup_event():
    global bot, bot_started
    try:
        # Optimize server
        await optimize_server_performance()
        Config.validate()

        # Initialize bot
        bot = Client(
            Config.SESSION_NAME,
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workers=8,
            sleep_threshold=120,
            max_concurrent_transmissions=10
        )

        # /start handler
        @bot.on_message(filters.command("start"))
        async def start_handler(client, message):
            user_id = message.from_user.id
            if user_id not in allowed_users:
                await message.reply(
                    "⚠️ **Group Membership Required**\n\n"
                    "To use this bot, join @GBEXTREME and click below.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Join Group 👥", url="https://t.me/GBEXTREME")],
                        [InlineKeyboardButton("✅ I've Joined", callback_data="joined_ignore_check")]
                    ])
                )
                return
            await message.reply(
                "👋 **Welcome back!**\n\n"
                "✅ You can now send any file and get a download link."
            )

        # Callback for "I've Joined"
        @bot.on_callback_query(filters.regex("^joined_ignore_check$"))
        async def joined_ignore_check_callback(client, callback_query):
            user_id = callback_query.from_user.id
            allowed_users.add(user_id)
            await callback_query.message.edit_text(
                "✅ **Thanks for joining!**\n\n"
                "🎉 You can now send any file and I'll create a download link for you!"
            )

        # Media handler
        @bot.on_message(filters.media)
        async def media_handler(client, message):
            try:
                user_id = message.from_user.id
                if user_id not in allowed_users:
                    is_subscribed = await check_group_subscription(user_id)
                    if not is_subscribed:
                                               await message.reply("⚠️ You must join @GBEXTREME to use this bot.")
                    return
                allowed_users.add(user_id)
                

                # Process file
                file_name = "file"
                file_size = 0
                file_id = str(message.id)
                if message.document:
                    file_name = message.document.file_name or "document"
                    file_size = message.document.file_size
                elif message.video:
                    file_name = message.video.file_name or "video.mp4"
                    file_size = message.video.file_size
                elif message.audio:
                    file_name = message.audio.file_name or "audio.mp3"
                    file_size = message.audio.file_size
                elif message.photo:
                    file_name = f"photo_{message.id}.jpg"
                    file_size = max(message.photo.sizes, key=lambda s: s.file_size).file_size

                safe_filename = "".join(c for c in file_name if c.isalnum() or c in (' ', '.', '_')).rstrip()
                download_path = DOWNLOADS_DIR / f"{file_id}_{safe_filename}"

                # Send initial progress message
                progress_msg = await message.reply("🔄 Starting download...\n[░░░░░░░░░░] 0%")

                # Download the file
                success = await download_telegram_file(message, download_path, progress_msg)

                if success and download_path.exists():
                    actual_size = download_path.stat().st_size
                    long_url = generate_download_url(file_id, safe_filename, download_path, actual_size)

                    # Shorten the URL
                    await progress_msg.edit_text("🔗 Generating short URL...")
                    short_url = await shorten_url(long_url)

                    # Prepare user info for notification
                    user_info = message.from_user.first_name
                    if message.from_user.username:
                        user_info = f"@{message.from_user.username}"
                    user_info += f" (ID: {message.from_user.id})"

                    # Send notification to the channel
                    asyncio.create_task(send_download_notification(safe_filename, actual_size, short_url, user_info))

                    # Send final message to user
                    await progress_msg.edit_text(
                        f"✅ **Download Complete!**\n\n"
                        f"📁 **File:** `{safe_filename}`\n"
                        f"📦 **Size:** {actual_size / (1024*1024):.2f} MB\n\n"
                        f"🔗 **Short URL:** {short_url}\n"
                        f"🌐 **Direct URL:** `{long_url}`\n\n"
                        f"⏰ **Expires in 24 hours**"
                    )
                else:
                    await progress_msg.edit_text("❌ **Download failed!** Please try again.")

            except Exception as e:
                logger.error(f"Media handler error: {e}")
                try:
                    await message.reply("❌ **Error processing file!** Please try again.")
                except:
                    pass

        # Start the bot
        await bot.start()
        bot_started = True
        me = await bot.get_me()
        print(f"Bot started as @{me.username}")
        asyncio.create_task(cleanup_old_files())

    except Exception as e:
        bot_started = False
        print(f"❌ Failed to start bot: {e}")
        import traceback
        traceback.print_exc()

# ----------------------------
# Cleanup old files
# ----------------------------
async def cleanup_old_files():
    while True:
        await asyncio.sleep(3600)
        current_time = datetime.now()
        expired_tokens = []
        for token, data in file_storage.items():
            if current_time - data['created_at'] > timedelta(hours=24):
                expired_tokens.append(token)
                file_path = Path(data['file_path'])
                if file_path.exists():
                    try:
                        file_path.unlink()
                        logger.info(f"Deleted expired file: {file_path}")
                    except:
                        pass
        for token in expired_tokens:
            del file_storage[token]

# ----------------------------
# Optimize server
# ----------------------------
async def optimize_server_performance():
    try:
        if os.name != 'nt':
            os.system('sysctl -w net.core.rmem_max=26214400 2>/dev/null || true')
            os.system('sysctl -w net.core.wmem_max=26214400 2>/dev/null || true')
    except: 
        pass

# ----------------------------
# Shutdown bot
# ----------------------------
@app.on_event("shutdown")
async def shutdown_event():
    global bot, bot_started
    if bot and bot_started:
        try:
            await bot.stop()
            bot_started = False
            print("Telegram bot stopped.")
        except Exception as e:
            print(f"Error stopping bot: {e}")

