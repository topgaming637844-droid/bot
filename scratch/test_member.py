import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot
from config import config

async def test():
    bot = Bot(token=config.BOT_TOKEN)
    channel = "@marcel_sa"
    user_id = 8820710465
    
    print(f"Checking member {user_id} in channel {channel}...")
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        print(f"Success! Status: {member.status}")
        print(f"Type of member object: {type(member)}")
    except Exception as e:
        print(f"Failed! Exception: {e}")
        
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(test())
