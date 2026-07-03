from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

router = Router(name="start")

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Handles the /start command."""
    welcome_text = (
        "👋 **Welcome to the Advanced Anime Search & Downloader Bot!**\n\n"
        "This bot normalizes queries using **AniList GraphQL**, searches for available streaming links, "
        "and sends video files directly to you. It also implements **Smart Size Logic** to automatically "
        "downgrade video quality if a file exceeds Telegram's 2GB size limit.\n\n"
        "🔍 **How to use**:\n"
        "Just send the name of the anime you want to search (e.g. `Luffy`, `One Piece`, or even typos like `One Peice` or Arabic names).\n\n"
        "Type /help at any time to see the bot instructions."
    )
    await message.answer(welcome_text, parse_mode="Markdown")

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handles the /help command."""
    help_text = (
        "ℹ️ **Bot Instructions**:\n\n"
        "1. **Search**: Send any anime name. The bot resolves character names and typos into the official English or Romaji titles.\n"
        "2. **Select**: Choose your desired anime from the search results menu.\n"
        "3. **Episode Number**: Enter the exact episode number when prompted. (No huge, laggy button grids!).\n"
        "4. **Download Quality**: Select a specific quality, or choose **Auto (Smart Size)** to let the bot select the highest resolution under 2GB.\n\n"
        "⚙️ *Note: Standard Telegram Bot limits uploads to 50MB. Run with a local Bot API server to upload up to 2GB.*"
    )
    await message.answer(help_text, parse_mode="Markdown")
