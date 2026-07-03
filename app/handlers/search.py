from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import SearchCache
from app.services.anilist import search_anilist
from app.services.scraper import search_anime_scraper

router = Router(name="search")

class SearchStates(StatesGroup):
    waiting_for_episode = State()

CACHE_EXPIRATION_HOURS = 24

@router.message(F.text & ~F.text.startswith("/"))
async def handle_anime_search(message: Message, db_session: AsyncSession, state: FSMContext):
    """
    Handles search queries. Queries database cache first,
    then normalizes using AniList GraphQL API and displays matches.
    """
    query = message.text.strip().lower()
    if not query:
        return

    # Check search cache first
    stmt = select(SearchCache).where(SearchCache.query_text == query)
    res = await db_session.execute(stmt)
    cached = res.scalar_one_or_none()

    resolved_anime = []

    # If cached and not expired (24h)
    if cached and (datetime.utcnow() - cached.created_at) < timedelta(hours=CACHE_EXPIRATION_HOURS):
        resolved_anime.append({
            "anilist_id": cached.anilist_id,
            "title_english": cached.title_english,
            "title_romaji": cached.title_romaji,
            "description": cached.description,
            "image_url": cached.image_url
        })
    else:
        # Resolve via AniList GraphQL
        status_msg = await message.answer("🔍 Normalizing query using AniList...")
        try:
            anilist_results = await search_anilist(query)
            await status_msg.delete()
            
            if not anilist_results:
                await message.answer("❌ No matching anime found on AniList. Try double-checking your query.")
                return
                
            resolved_anime = anilist_results
            
            # Cache the top result
            top_result = anilist_results[0]
            if cached:
                # Update expired entry
                cached.anilist_id = top_result["anilist_id"]
                cached.title_english = top_result["title_english"]
                cached.title_romaji = top_result["title_romaji"]
                cached.description = top_result["description"]
                cached.image_url = top_result["image_url"]
                cached.created_at = datetime.utcnow()
            else:
                # Add new entry
                new_cache = SearchCache(
                    query_text=query,
                    anilist_id=top_result["anilist_id"],
                    title_english=top_result["title_english"],
                    title_romaji=top_result["title_romaji"],
                    description=top_result["description"],
                    image_url=top_result["image_url"]
                )
                db_session.add(new_cache)
            await db_session.commit()
            
        except Exception as e:
            try:
                await status_msg.delete()
            except Exception:
                pass
            await message.answer(f"❌ Error during query normalization: {e}")
            return

    # Build selection keyboard
    keyboard_buttons = []
    for anime in resolved_anime[:5]:
        title = anime["title_english"] or anime["title_romaji"]
        # Max length of callback data is 64 bytes. Let's send anilist_id
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=title[:40] + "..." if len(title) > 43 else title,
                callback_query=f"sel_anime:{anime['anilist_id']}"
            )
        ])

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer(
        "✨ **AniList Search Results**:\nSelect the anime to load episode selection:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("sel_anime:"))
async def handle_anime_selection(callback: CallbackQuery, db_session: AsyncSession, state: FSMContext):
    """
    Handles anime selection from the keyboard.
    Displays cover image/details and transitions to FSM state to prompt for episode.
    """
    anilist_id = int(callback.data.split(":")[1])
    
    # Retrieve details from search_cache
    stmt = select(SearchCache).where(SearchCache.anilist_id == anilist_id)
    res = await db_session.execute(stmt)
    cache_entry = res.scalars().first()
    
    if not cache_entry:
        await callback.answer("❌ Anime cache details not found. Please search again.", show_alert=True)
        return
        
    title = cache_entry.title_english or cache_entry.title_romaji
    
    # Store anime details in FSM context
    await state.update_data(
        anilist_id=anilist_id,
        anime_title=title,
        title_romaji=cache_entry.title_romaji,
        title_english=cache_entry.title_english
    )
    
    # Transition to waiting for episode number
    await state.set_state(SearchStates.waiting_for_episode)
    await callback.answer()

    details_text = (
        f"🎬 **Selected Anime**: {title}\n"
        f"📝 Description: {cache_entry.description[:250] + '...' if cache_entry.description else 'None'}\n\n"
        f"🔢 **Please type the Episode Number you want to get** (e.g. `1`, `12`, `24`):"
    )
    
    if cache_entry.image_url:
        await callback.message.answer_photo(
            photo=cache_entry.image_url,
            caption=details_text,
            parse_mode="Markdown"
        )
    else:
        await callback.message.answer(details_text, parse_mode="Markdown")
