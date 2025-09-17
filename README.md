# Telegram File Link Generator Bot

A Python-based Telegram bot that converts uploaded files into streamable and downloadable links without storing files. Uses Telegram's CDN for direct access.

## Features

- 📁 **Zero Storage**: No files stored on server - direct links to Telegram's CDN
- 🔗 **Instant Links**: Generates streaming and download links immediately  
- 🎵 **Media Players**: Built-in video, audio, and image players
- 🔒 **Secure Access**: HMAC-signed URLs with time expiration
- ⚡ **Fast Delivery**: Powered by Telegram's global CDN
- 🌐 **Web Interface**: Beautiful streaming pages for all media types

## Supported File Types

- **Videos**: MP4, WebM, MOV, AVI, MKV - Stream with built-in player
- **Audio**: MP3, WAV, OGG, AAC, FLAC - Audio player with controls
- **Images**: JPG, PNG, GIF, WebP, BMP - Full-screen image viewer
- **Documents**: PDF, TXT, DOC, XLS, PPT - Direct download
- **All File Types**: Any file supported by Telegram (up to 2GB)

## Quick Setup

### 1. Get Telegram API Credentials

1. Visit [my.telegram.org/apps](https://my.telegram.org/apps)
2. Create a new application to get **API_ID** and **API_HASH**

### 2. Create Your Bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts  
3. Copy the **BOT_TOKEN**

### 3. Set Environment Variables

```bash
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash  
TELEGRAM_BOT_TOKEN=your_bot_token
URL_SECRET=your_random_secret_key
BASE_URL=https://your-deployment-url.com
```

### 4. Deploy to Koyeb

#### Option A: GitHub Deploy (Recommended)
1. Push your code to GitHub
2. Go to [Koyeb Dashboard](https://app.koyeb.com/)
3. Click "Create App" → "GitHub" → Select your repository
4. Set build method to "Dockerfile"
5. Add environment variables in Koyeb dashboard
6. Click "Deploy"

#### Option B: CLI Deploy
```bash
# Install Koyeb CLI
curl -fsSL https://cli.koyeb.com/install.sh | sh
koyeb auth login

# Deploy with environment variables
koyeb service create \
  --app telegram-file-bot \
  --git-repository https://github.com/yourusername/telegram-file-bot \
  --name bot --type web --ports 5000:http \
  --env TELEGRAM_API_ID=your_api_id \
  --env TELEGRAM_API_HASH=your_api_hash \
  --env TELEGRAM_BOT_TOKEN=your_bot_token \
  --env URL_SECRET=your_secret \
  --env BASE_URL=https://your-app.koyeb.app \
  --instance-type nano
```

#### Local Testing
```bash
# Run both bot and web server
python main.py

# Or run only web server for testing
python run_server_only.py
```

## Deployment Features

- ✅ **Docker-based deployment** on Koyeb
- ✅ **Health checks** for reliability  
- ✅ **Environment variable management**
- ✅ **Automatic scaling** (nano instance recommended)
- ✅ **Global CDN** through Koyeb edge locationspi/webhook
```

## Local Development

1. Clone this repository
2. Install dependencies:
   ```bash
   npm install
   ```

3. Create `.env.local` file:
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token
   URL_SECRET=your_secret_key
   ```

4. Run development server:
   ```bash
   npm run dev
   ```

## API Endpoints

- `GET /` - Landing page
- `POST /api/webhook` - Telegram webhook handler
- `POST /api/upload` - File upload endpoint
- `GET /api/files/[id]` - File serving endpoint

## Project Structure

```
├── api/
│   ├── webhook.js          # Telegram webhook handler
│   ├── upload.js           # File upload API
│   └── files/[id].js       # File serving API
├── lib/
│   ├── telegram.js         # Telegram bot functions
│   ├── storage.js          # File storage system
│   └── utils.js            # Utility functions
├── index.html              # Landing page
├── vercel.json            # Vercel configuration
└── package.json           # Node.js dependencies
```

## How It Works

1. **File Upload**: Users send files to the Telegram bot
2. **Processing**: Bot downloads and validates the file
3. **Storage**: File is stored with a unique ID and metadata
4. **Link Generation**: Creates secure, time-limited access URLs
5. **Response**: Bot sends streamable and downloadable links back to user

## Security Features

- **Token-based Access**: All links include HMAC tokens
- **Time Expiration**: Links expire after 24 hours
- **File Validation**: Only supported file types are processed
- **Rate Limiting**: Prevents abuse with upload limits
- **Size Limits**: Maximum 20MB per file (Telegram limit)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

For issues and questions:
- Create an issue on GitHub
- Check the documentation
- Review the error logs in Vercel dashboard

---

Built with ❤️ using Vercel serverless functions and Telegram Bot API