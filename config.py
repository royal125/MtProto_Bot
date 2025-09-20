import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    BASE_URL = os.getenv("BASE_URL")
    SESSION_NAME = "my_bot"  # Add this line!

    @staticmethod
    def validate():
        if not Config.API_ID or not Config.API_HASH or not Config.BOT_TOKEN:
            raise ValueError("Missing required configuration in Config class")
