# Telegram Auto Download Bot

A Telegram bot that automatically downloads and backs up media files from forwarded messages and their replies to the server for permanent storage.

## Features

- 🤖 Telegram bot interface for easy interaction
- 📥 Downloads media from forwarded messages and all their replies
- 💾 Permanently stores files on server for backup purposes
- 🎯 Supports photos, videos, GIFs, audio files, and documents
- 🔍 Smart file naming with timestamps and message IDs
- 📊 Progress updates during backup process
- 📁 Organized storage in timestamped directories

## Requirements

- Python 3.8+
- Telegram API credentials (API ID and API Hash)
- Bot Token from @BotFather
- Phone number for Telegram authentication

## Installation

1. Clone the repository:

```bash
git clone <repository-url>
cd telegram_auto_download
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set up configuration:
   - Create a `.env` file in the project root
   - Fill in your Telegram API credentials

## Configuration

### Getting Telegram API Credentials

1. **API ID and API Hash:**
   - Go to <https://my.telegram.org/apps>
   - Log in with your phone number
   - Create a new application
   - Copy the `api_id` and `api_hash`

2. **Bot Token:**
   - Message @BotFather on Telegram
   - Create a new bot with `/newbot`
   - Copy the bot token

3. **Phone Number:**
   - Your Telegram account phone number (with country code)

### Environment Variables

Create a `.env` file in the project root:

```env
API_ID=your_api_id_here
API_HASH=your_api_hash_here
PHONE_NUMBER=your_phone_number_here
BOT_TOKEN=your_bot_token_here
```

## Usage

1. Start the bot:

```bash
python main.py
```

2. In Telegram:
   - Find your bot by username
   - Forward any message with media to the bot
   - The bot will backup all media from the message
   - Receive confirmation with backup details (file count, size, storage location)

## Project Structure

```
telegram_auto_download/
├── src/
│   └── telegram_bot.py          # Main bot application
├── config/
│   └── config.py               # Configuration management
├── main.py                     # Main entry point
├── logs/                       # Log files (auto-created)
├── downloads/                  # Permanent backup directory
├── requirements.txt            # Python dependencies
├── ChangeLog.md               # Project changelog
└── README.md                  # This file
```

## Supported Media Types

- 📷 Photos (JPG format)
- 🎥 Videos (MP4 and other formats)
- 🎬 GIFs
- 🎵 Audio files (MP3 and other formats)
- 📄 Documents and files

## Error Handling

The bot includes comprehensive error handling for:

- Invalid API credentials
- Network connection issues
- File download failures
- Storage directory creation
- Telegram API rate limits

## Security Notes

- Never commit your `.env` file or API credentials
- Keep your bot token secure and private
- Files are permanently stored in organized backup directories
- All session files are ignored by git

## Troubleshooting

### Common Issues

1. **"Unable to get original message"**
   - Ensure the bot has access to the forwarded chat
   - Check if the message is from a private chat (not supported)

2. **"Storage issues"**
   - Ensure sufficient disk space for media backups
   - Check directory permissions for backup storage

3. **Authentication errors**
   - Verify your API credentials in `.env`
   - Ensure phone number includes country code

### Logs

Check the console output or log files in the `logs/` directory for detailed error information.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This bot is for educational and personal backup use. Ensure you comply with Telegram's Terms of Service and respect copyright when backing up media files. Only backup content you have permission to store.
