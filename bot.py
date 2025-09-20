import os
import logging
import asyncio
import secrets
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import MessageMediaType
import urllib.parse
from pathlib import Path
import aiofiles
import concurrent.futures
import aiohttp
import math

from config import Config

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI()

# Create downloads directory
DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)

# Global bot instance
bot = None
bot_started = False

# Thread pool for parallel processing
thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=10)

# In-memory storage for file links
file_storage = {}

async def shorten_url(long_url: str) -> str:
    """Shorten URL using TinyURL API"""
    try:
        tinyurl_api = f"https://tinyurl.com/api-create.php?url={urllib.parse.quote(long_url)}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(tinyurl_api) as response:
                if response.status == 200:
                    short_url = await response.text()
                    return short_url.strip()
                else:
                    logger.warning(f"TinyURL API failed: {response.status}")
                    return long_url
    except Exception as e:
        logger.error(f"URL shortening error: {e}")
        return long_url

def generate_download_url(file_id: str, file_name: str, file_path: str, file_size: int) -> str:
    """Generate a secure download URL"""
    token = secrets.token_urlsafe(16)
    file_storage[token] = {
        'file_id': file_id,
        'file_name': file_name,
        'file_path': str(file_path),
        'file_size': file_size,
        'created_at': datetime.now()
    }
    return f"{Config.BASE_URL}/download/{token}"

async def cleanup_old_files():
    """Clean up files older than 24 hours"""
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
                    except Exception as e:
                        logger.error(f"Error deleting file {file_path}: {e}")
        
        for token in expired_tokens:
            del file_storage[token]
        
        if expired_tokens:
            logger.info(f"Cleaned up {len(expired_tokens)} expired files")

async def download_telegram_file(message: Message, download_path: Path, progress_message: Message) -> bool:
    """Download file from Telegram with progress updates"""
    try:
        chunk_size = 524288  # 512KB
        downloaded = 0
        
        # Get total file size
        if message.document:
            total_size = message.document.file_size
        elif message.video:
            total_size = message.video.file_size
        elif message.audio:
            total_size = message.audio.file_size
        elif message.photo:
            total_size = max(message.photo.sizes, key=lambda s: s.file_size).file_size
        else:
            total_size = 0
        
        last_update_time = datetime.now()
        
        async with aiofiles.open(download_path, 'wb') as f:
            async for chunk in bot.stream_media(message, limit=chunk_size):
                await f.write(chunk)
                downloaded += len(chunk)
                
                # Update progress every 2 seconds or 5% change
                current_time = datetime.now()
                if (current_time - last_update_time).total_seconds() >= 2 or downloaded == total_size:
                    if total_size > 0:
                        percentage = (downloaded / total_size) * 100
                        progress_bar = create_progress_bar(percentage)
                        
                        # Update progress message
                        try:

                            # update progress with green color gradient write a function create_progress_bar
                            progress_bar = create_progress_bar(percentage)


                            await progress_message.edit_text(
                                f"📥 Downloading...\n"
                                f"{progress_bar}\n"
                                f"**{percentage:.1f}%** ({downloaded//1024}KB / {total_size//1024}KB)"
                            )
                        except:
                            pass  # Ignore edit errors
                        
                        last_update_time = current_time
        
        return True
    except Exception as e:
        logger.error(f"Download error: {e}")
        if download_path.exists():
            try:
                download_path.unlink()
            except:
                pass
        return False

def create_progress_bar(percentage: float, length: int = 10) -> str:
    """Create a visual progress bar with green color gradient"""
    filled_length = int(length * percentage // 100)
    
    # Green gradient emojis: from dark green to bright green
    gradient = ['🟩', '🟢', '💚', '✅', '🌿']  # Different green emojis for gradient effect
    
    # Create the progress bar with gradient
    bar = ''
    for i in range(length):
        if i < filled_length:
            # Use different green emojis based on position for gradient effect
            emoji_index = min(i * len(gradient) // length, len(gradient) - 1)
            bar += gradient[emoji_index]
        else:
            bar += '⬜'  # White square for unfilled portion
    
    return f"{bar} {percentage:.1f}%"

async def optimize_server_performance():
    """Optimize server performance settings"""
    try:
        # Increase TCP buffer sizes for better throughput (Linux/Mac)
        if os.name != 'nt':  # Not Windows
            os.system('sysctl -w net.core.rmem_max=26214400 2>/dev/null || true')
            os.system('sysctl -w net.core.wmem_max=26214400 2>/dev/null || true')
        
        logger.info("Server performance optimized")
    except:
        pass

# FastAPI routes
@app.get("/")
async def root():
    return {"message": "Telegram File Converter Bot is running!"}

@app.get("/download/{token}")
async def download_file(token: str):
    """Handle file downloads with optimized speed"""
    try:
        if token not in file_storage:
            raise HTTPException(status_code=404, detail="File not found or link expired")
        
        file_data = file_storage[token]
        file_path = Path(file_data['file_path'])
        
        if not file_path.exists():
            if token in file_storage:
                del file_storage[token]
            raise HTTPException(status_code=404, detail="File not found")
        
        filename_encoded = urllib.parse.quote(file_data['file_name'])
        
        return FileResponse(
            path=file_path,
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
    except Exception as e:
        logger.error(f"Download endpoint error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/health")
async def health_check():
    """Health check endpoint with bot status"""
    try:
        bot_status = "disconnected"
        if bot and hasattr(bot, 'is_connected'):
            bot_status = "connected" if bot.is_connected else "disconnected"
        
        return JSONResponse({
            "status": "healthy", 
            "bot_status": bot_status,
            "bot_started": bot_started,
            "files_count": len(file_storage),
            "server_optimized": True,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return JSONResponse({
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }, status_code=500)

# ... (other routes remain the same) ...

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Start the bot and cleanup task"""
    global bot, bot_started
    
    try:
        print("=" * 50)
        print("Starting Telegram File Converter Bot...")
        print("=" * 50)
        
        # Optimize server performance
        await optimize_server_performance()
        
        # Validate config first
        from config import Config
        Config.validate()
        print("✓ Configuration validated")
        
        # Initialize bot with optimized settings
        bot = Client(
            Config.SESSION_NAME,
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workers=8,
            sleep_threshold=120,
            max_concurrent_transmissions=10
        )
        
        print("✓ Bot client initialized with optimized settings")
        
        # Register handlers
        @bot.on_message(filters.command("start"))
        async def start_handler(client, message):
            await message.reply(
                "👋 Hello! I'm a high-speed file to URL converter bot!\n\n"
                "Send me any file and I'll convert it to a downloadable URL.\n\n"
                "⚡ Progress tracking\n"
                "🔗 Short URLs\n"
                "📁 Supported files: All types\n"
                "📦 Max file size: 2GB\n"
                "⏰ Link expiration: 24 hours"
            )
        
        @bot.on_message(filters.media)
        async def media_handler(client, message):
            try:
                if not message.media:
                    return
                
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
                
                # Create safe filename
                safe_filename = "".join(c for c in file_name if c.isalnum() or c in (' ', '.', '_')).rstrip()
                download_path = DOWNLOADS_DIR / f"{file_id}_{safe_filename}"
                
                # Send initial progress message
                progress_msg = await message.reply("🔄 Starting download...\n[░░░░░░░░░░] 0%")
                
                # Download file with progress updates
                success = await download_telegram_file(message, download_path, progress_msg)
                
                if success and download_path.exists():
                    actual_size = download_path.stat().st_size
                    long_url = generate_download_url(file_id, safe_filename, download_path, actual_size)
                    
                    # Shorten the URL
                    await progress_msg.edit_text("🔗 Generating short URL...")
                    short_url = await shorten_url(long_url)
                    
                    # Final success message
                    await progress_msg.edit_text(
                        f"✅ **Download Complete!**\n\n"
                        f"📁 **File:** `{safe_filename}`\n"
                        f"📦 **Size:** {actual_size / (1024*1024):.2f} MB\n\n"
                        f"🔗 **Short URL:** {short_url}\n"
                        f"🌐 **Direct URL:** `{long_url}`\n\n"
                        f"⚡ **Fast download available**\n"
                        f"⏰ **Expires in 24 hours**"
                    )
                else:
                    await progress_msg.edit_text("❌ **Download failed!**\nPlease try again with a smaller file.")
                    
            except Exception as e:
                logger.error(f"Media handler error: {e}")
                try:
                    await progress_msg.edit_text("❌ **Error processing file!**\nPlease try again.")
                except:
                    await message.reply("❌ Error processing file. Please try again.")




                    
        
        # Start the bot
        await bot.start()
        bot_started = True
        
        # Get bot info
        me = await bot.get_me()
        print(f"✓ Bot started as @{me.username}")
        print(f"✓ Download directory: {DOWNLOADS_DIR.absolute()}")
        print("✓ URL shortening enabled")
        print("✓ Progress tracking enabled")
        
        # Start cleanup task
        asyncio.create_task(cleanup_old_files())
        print("✓ Cleanup task started")
        print("=" * 50)
        print("Enhanced bot is ready! 🚀")
        print("=" * 50)
        
    except Exception as e:
        bot_started = False
        print(f"❌ Failed to start bot: {e}")
        import traceback
        traceback.print_exc()

@app.on_event("shutdown")
async def shutdown_event():
    """Stop the bot"""
    global bot, bot_started
    if bot and bot_started:
        try:
            print("Stopping Telegram bot...")
            await bot.stop()
            bot_started = False
            print("Telegram bot stopped.")
        except Exception as e:
            print(f"Error stopping bot: {e}")
