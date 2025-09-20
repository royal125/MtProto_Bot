import os
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

class Config:
    API_ID = int(os.getenv("API_ID", 23323985))
    API_HASH = os.getenv("API_HASH", "d24809282e7c046a98a04ca3c66659e7")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "8433225445:AAFSS3wf7QG7MTewIOnho7AJ7Qg3Chh0xDg")
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 8000))
    BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
    SESSION_NAME = os.getenv("SESSION_NAME", "session")

    # Validate required credentials
    @classmethod
    def validate(cls):
        if not cls.API_ID:
            raise ValueError("❌ API_ID must be set in environment variables")
        if not cls.API_HASH:
            raise ValueError("❌ API_HASH must be set in environment variables")
        if not cls.BOT_TOKEN:
            raise ValueError("❌ BOT_TOKEN must be set in environment variables")
        print("✓ Configuration validated successfully")
        return True

# Validate configuration when imported
try:
    Config.validate()
except ValueError as e:
    print(f"Configuration Error: {e}")
    print("Please check your .env file")
