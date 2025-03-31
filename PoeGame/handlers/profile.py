# handlers/profile.py
import logging
import math
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.utils.text_decorations import html_decoration as hd

# --- ИСПРАВЛЕНИЕ: Импортируем get_player_effective_stats вместо/в дополнение get_player ---
from database.db_manager import get_player_effective_stats, check_and_apply_regen
# --- КОНЕЦ ИСПРАВЛЕНИЯ ---

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - [%(filename)s:%(lineno)d] - %(message)s")

router = Router()

# Вспомогательная функция регена (может быть и в common.py)
async def trigger_regen_check(user_id: int, state: FSMContext):
     try:
        current_state_str = await state.get_state()
        await check_and_apply_regen(user_id, current_state_str)
     except Exception as e:
         logging.error(f"Error during regen check in profile for user {user_id}: {e}", exc_info=False)

# Обработчик для кнопки "Профиль"
@router.message(F.text.lower() == "👤 профиль")
async def handle_profile_button(message: Message, state: FSMContext):
    user_id = message.from_user.id
    logging.info(f"User {user_id} requested profile.")

    # Проверяем реген
    await trigger_regen_check(user_id, state)

    # --- ИСПРАВЛЕНИЕ: Используем get_player_effective_stats ---
    player = await get_player_effective_stats(user_id)
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

    if player:
        logging.debug(f"Displaying profile for user {user_id}. Effective stats: {dict(player)}")
        # Экранируем переменные данные
        username_escaped = hd.quote(player.get('username', f"User_{user_id}")) # Используем .get для безопасности
        class_escaped = hd.quote(player.get('class', 'Неизвестный'))
        quest_monster_key_escaped = hd.quote(player.get('quest_monster_key', '')) if player.get('quest_monster_key') else ""

        # Рассчитываем производные статы (уклонение, снижение урона)
        # Важно: Используем УЖЕ посчитанные эффективные статы из словаря player
        dexterity = player.get('dexterity', 0)
        armor = player.get('armor', 0)
        dodge_chance = min(75.0, dexterity / 5.0)
        damage_reduction = armor // 20

        # Форматируем вывод профиля
        # Теперь все значения статов (strength, armor, max_hp и т.д.) будут УЧИТЫВАТЬ экипировку
        profile_text = (
            f"👤 <b>Профиль персонажа: {username_escaped}</b>\n\n"
            f"⚔️ Класс: {class_escaped}\n"
            f"🌟 Уровень: {player.get('level', 1)} ({player.get('xp', 0)}/{player.get('xp_to_next_level', 100)} XP)\n"
            f"✨ Очки прокачки: {player.get('stat_points', 0)}\n\n"

            f"❤️ Здоровье: {player.get('current_hp', 0)} / {player.get('max_hp', 0)}\n"
            f"🛡️ Энергощит: {player.get('energy_shield', 0)} / {player.get('max_energy_shield', 0)}\n"
            f"💧 Мана: {player.get('current_mana', 0)} / {player.get('max_mana', 0)}\n\n"

            f"💪 Сила: {player.get('strength', 0)}\n"
            f"🏹 Ловкость: {dexterity} (Уклонение: {dodge_chance:.1f}%)\n"
            f"🧠 Интеллект: {player.get('intelligence', 0)}\n\n"

            f"🦾 Броня: {armor} (Снижение физ. урона: {damage_reduction})\n"
            f"💥 Шанс крит. удара: {player.get('crit_chance', 5.0):.1f}%\n"
            f"🔥 Множитель крит. урона: {player.get('crit_damage', 150.0):.0f}%\n\n"

            f"💰 Золото: {player.get('gold', 0)}\n\n"

            f"📜 <b>Ежедневное задание:</b>\n"
        )
        if player.get('quest_monster_key'):
            profile_text += (
                f"   Цель: Убить {quest_monster_key_escaped} ({player.get('quest_current_count', 0)}/{player.get('quest_target_count', 0)})\n"
                f"   Награда: {player.get('quest_gold_reward', 0)} золота, {player.get('quest_xp_reward', 0)} XP\n"
            )
        else:
            profile_text += "   <i>Нет активного задания.</i>\n"

        # TODO: В будущем можно добавить опцию показа базовых статов и бонусов от шмота отдельно
        # profile_text += "\n<i>(Статы указаны с учетом экипировки)</i>"

        try:
            await message.answer(profile_text, parse_mode="HTML")
            logging.debug(f"Effective profile sent successfully to user {user_id}.")
        except Exception as e:
            logging.error(f"Failed to send profile with HTML for user {user_id}: {e}\nText was:\n{profile_text}")
            plain_text = profile_text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<pre>","").replace("</pre>","").replace("<u>","").replace("</u>","").replace("<ins>","").replace("</ins>","")
            try:
                await message.answer(plain_text)
                logging.info(f"Profile sent as plain text to user {user_id} after HTML error.")
            except Exception as plain_e:
                logging.error(f"Failed even to send plain text profile to user {user_id}: {plain_e}")

    else:
        logging.warning(f"Attempted to view profile for non-existent player {user_id}.")
        await message.answer("У вас еще нет персонажа. Используйте команду /start, чтобы начать игру.")
