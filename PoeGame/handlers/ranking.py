# handlers/ranking.py
import logging
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.text_decorations import html_decoration as hd

from database.db_manager import get_top_players, check_and_apply_regen

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - [%(filename)s:%(lineno)d] - %(message)s")
router = Router()

RANKING_LIMIT = 10 # Сколько игроков показывать в топе

# Клавиатура для выбора типа рейтинга
def get_ranking_type_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🏆 По Уровню/Опыту", callback_data="rank:level_xp")],
        [InlineKeyboardButton(text="💰 По Золоту", callback_data="rank:gold")],
        [InlineKeyboardButton(text="Закрыть", callback_data="rank:close")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Обработчик кнопки/команды Рейтинг
@router.message(F.text.lower() == "🏆 рейтинг")
# @router.message(Command("ranking")) # Можно добавить и команду
async def show_ranking_options(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    logging.info(f"User {user_id} requested ranking.")
    # Проверяем реген
    try:
        current_state_str = await state.get_state()
        await check_and_apply_regen(user_id, current_state_str)
    except Exception as e:
        logging.error(f"Error during regen check in ranking for user {user_id}: {e}", exc_info=False)

    await message.answer("Выберите тип рейтинга:", reply_markup=get_ranking_type_keyboard())

# Обработчик выбора типа рейтинга
@router.callback_query(F.data.startswith("rank:"))
async def process_ranking_selection(callback: types.CallbackQuery):
    action = callback.data.split(":")[1]
    user_id = callback.from_user.id

    if action == "close":
        await callback.answer("Рейтинг закрыт.")
        try: await callback.message.delete()
        except Exception: pass
        return

    if action not in ['level_xp', 'gold']:
        await callback.answer("Неизвестный тип рейтинга.", show_alert=True)
        return

    await callback.answer(f"Загружаем топ по {'опыту' if action == 'level_xp' else 'золоту'}...")

    try:
        top_players = await get_top_players(by=action, limit=RANKING_LIMIT)

        if not top_players:
            text = "В рейтинге пока пусто..."
        else:
            if action == 'level_xp':
                text = f"🏆 <b>Топ-{RANKING_LIMIT} игроков по Уровню/Опыту:</b>\n\n"
                for i, player in enumerate(top_players):
                    text += f"{i+1}. {hd.quote(player['username'])} - Ур. {player['level']} ({player['xp']} XP)\n"
            else: # action == 'gold'
                text = f"💰 <b>Топ-{RANKING_LIMIT} игроков по Золоту:</b>\n\n"
                for i, player in enumerate(top_players):
                    text += f"{i+1}. {hd.quote(player['username'])} - {player['gold']} 💰\n"

        # Обновляем сообщение с рейтингом и клавиатурой выбора
        await callback.message.edit_text(text, reply_markup=get_ranking_type_keyboard(), parse_mode="HTML")

    except Exception as e:
        logging.error(f"Error fetching or displaying ranking for action '{action}': {e}", exc_info=True)
        await callback.answer("Ошибка при загрузке рейтинга.", show_alert=True)
        # Можно вернуть к выбору или закрыть
        try: await callback.message.edit_text("Не удалось загрузить рейтинг.", reply_markup=get_ranking_type_keyboard())
        except Exception: pass
