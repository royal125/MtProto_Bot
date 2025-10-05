import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")        # Optional if you want bot token fallbac
    BASE_URL = os.getenv("BASE_URL")
    SESSION_NAME = "my_bot"

    @staticmethod
    def validate():
        if not Config.API_ID or not Config.API_HASH:
            raise ValueError("Missing required API_ID or API_HASH in Config")
        # Either BOT_TOKEN or PHONE_NUMBER must exist
        if not (Config.BOT_TOKEN):
            raise ValueError("Either BOT_TOKEN must be set in Config")
