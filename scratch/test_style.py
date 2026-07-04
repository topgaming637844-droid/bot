import sys
from aiogram.types import InlineKeyboardButton

try:
    btn = InlineKeyboardButton(text="Test", callback_data="test", style="bg_success")
    print("SUCCESS:", btn.model_dump() if hasattr(btn, 'model_dump') else btn.to_python())
except Exception as e:
    print("FAILED:", str(e))
