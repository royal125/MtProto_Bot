🚀 VPS Setup Guide for Telegram Bot
1. Update your server
sudo apt update && sudo apt upgrade -y

2. Install dependencies
sudo apt install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx git

3. Clone your bot project
cd ~
git clone https://github.com/your-repo/MtProto_Bot.git
cd MtProto_Bot


(or if uploaded via FileZilla: cd ~/MtProto_Bot)

4. Create Python virtual environment
python3 -m venv venv
source venv/bin/activate

5. Install required Python packages
pip install --upgrade pip
pip install pyrogram tgcrypto fastapi uvicorn aiohttp aiofiles python-dotenv

6. Add your .env file

Inside ~/MtProto_Bot/.env add:

API_ID=23323985
API_HASH=d24809282e7c046a98a04ca3c66659e7
BOT_TOKEN=YOUR_BOT_TOKEN
SESSION_NAME=my_bot
BASE_URL=https://yourdomain.com


⚠️ Replace YOUR_BOT_TOKEN and yourdomain.com.

7. Test run the bot manually
cd ~/MtProto_Bot
source venv/bin/activate
uvicorn bot:app --host 0.0.0.0 --port 8000


✅ If bot responds → working fine.

8. Setup Nginx reverse proxy

Create file:

sudo nano /etc/nginx/sites-available/bot


Paste:

server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}


Enable site:

sudo ln -s /etc/nginx/sites-available/bot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

9. Enable HTTPS with Certbot
sudo certbot --nginx -d yourdomain.com


(Choose option 2 → Redirect HTTP to HTTPS)

10. Create a Systemd service
sudo nano /etc/systemd/system/telegram-bot.service


Paste:

[Unit]
Description=Telegram File Converter Bot
After=network.target

[Service]
User=root
WorkingDirectory=/root/MtProto_Bot
ExecStart=/root/MtProto_Bot/venv/bin/python3 -m uvicorn bot:app --host 0.0.0.0 --port 8000
Restart=always
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target

11. Enable & start the bot
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot


Check logs:

sudo systemctl status telegram-bot -n 20 --no-pager

12. (Optional) Auto reload on code changes

Create path unit:

sudo nano /etc/systemd/system/telegram-bot.path


Paste:

[Unit]
Description=Restart telegram-bot on code change

[Path]
PathModified=/root/MtProto_Bot/*.py
Unit=telegram-bot.service

[Install]
WantedBy=multi-user.target


Enable:

sudo systemctl enable telegram-bot.path
sudo systemctl start telegram-bot.path


✅ Done! Now your bot runs in the background with HTTPS and reloads on code changes.

Do you also want me to add a "Troubleshooting" section (common errors + fixes) for your README?
