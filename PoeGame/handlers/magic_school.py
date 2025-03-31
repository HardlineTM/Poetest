# handlers/magic_school.py
import logging
import math # Добавим math для расчетов, если понадобится
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.text_decorations import html_decoration as hd
from aiogram.exceptions import TelegramBadRequest

# Импортируем нужные функции и данные
from database.db_manager import (
    get_player_effective_stats, check_and_apply_regen,
    get_learned_spells, learn_spell
)
from game_data import SPELLS

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - [%(filename)s:%(lineno)d] - %(message)s")
router = Router()

# --- Вспомогательная функция для расчета требования интеллекта ---
def get_spell_intelligence_requirement(level_req: int) -> int:
    """Рассчитывает требование интеллекта на основе уровня заклинания."""
    # Формула: 20 + (уровень_спелла - 1) * 5
    # Например: Ур.1 -> 20, Ур.2 -> 25, Ур.3 -> 30, ...
    if level_req <= 0: return 0 # На всякий случай
    return 20 + (level_req - 1) * 5

# --- Клавиатура для Школы Магов (Обновленная) ---
def get_magic_school_keyboard(player_level: int, player_intelligence: int, learned_spell_ids: list[str]) -> InlineKeyboardMarkup:
    """
    Генерирует клавиатуру со списком заклинаний.
    Показывает требования уровня и интеллекта.
    Делает кнопку активной только если все требования выполнены.
    """
    buttons = []
    available_to_learn_display = [] # Список для доступных и недоступных спеллов

    # Собираем все спеллы, которые игрок еще не выучил
    for spell_id, spell_data in SPELLS.items():
        if spell_id not in learned_spell_ids:
            available_to_learn_display.append({'id': spell_id, **spell_data})

    # Сортируем по уровню требования
    available_to_learn_display.sort(key=lambda s: s.get('level_req', 999))

    if not available_to_learn_display:
        buttons.append([InlineKeyboardButton(text="Вы уже изучили все доступные заклинания!", callback_data="magic:noop")])
    else:
        for spell in available_to_learn_display:
            spell_id = spell['id']
            level_req = spell.get('level_req', 999)
            # --- Рассчитываем требование интеллекта ---
            int_req = get_spell_intelligence_requirement(level_req)

            # --- Проверяем ВСЕ условия ---
            level_ok = player_level >= level_req
            int_ok = player_intelligence >= int_req
            can_learn = level_ok and int_ok

            # Формируем текст кнопки
            mana_cost = spell.get('mana_cost', '?')
            req_text_parts = []
            if not level_ok:
                req_text_parts.append(f"🔒Ур.{level_req}")
            else:
                req_text_parts.append(f"Ур.{level_req}")

            if not int_ok:
                req_text_parts.append(f"🔒Инт.{int_req}")
            else:
                req_text_parts.append(f"Инт.{int_req}")

            req_text = " / ".join(req_text_parts) # Собираем требования: "Ур.5 / 🔒Инт.40"

            button_prefix = "✅" if can_learn else "❌" # Эмодзи доступности
            button_text = (
                f"{button_prefix} {hd.quote(spell['name'])} "
                f"({req_text}, {mana_cost} Маны)"
            )

            # Устанавливаем callback_data
            if can_learn:
                callback_data = f"magic:learn:{spell_id}"
            else:
                # Если нельзя выучить, кнопка будет показывать инфо (или ничего не делать)
                callback_data = f"magic:info:{spell_id}" # Показываем инфо при нажатии на недоступный спелл

            buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])

    buttons.append([InlineKeyboardButton(text="Уйти", callback_data="magic:close")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- Обработчики ---

# Обработчик для кнопки "Школа магов"
@router.message(F.text.lower() == "🔮 школа магов")
async def magic_school_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    logging.info(f"User {user_id} entered the Magic School.")
    try: await check_and_apply_regen(user_id, await state.get_state())
    except Exception as e: logging.error(f"Regen check error in magic school: {e}")

    player = await get_player_effective_stats(user_id) # Нужен уровень и ИНТЕЛЛЕКТ
    if not player:
        await message.answer("Сначала создайте персонажа: /start")
        return

    learned_spells = await get_learned_spells(user_id)
    learned_spell_ids = [s['id'] for s in learned_spells]

    # --- Передаем интеллект в клавиатуру ---
    keyboard = get_magic_school_keyboard(player['level'], player['intelligence'], learned_spell_ids)

    learned_spells_text = "\n".join(
        [f" - {hd.quote(s['name'])} ({s['mana_cost']} Маны): <i>{s.get('description','Нет описания')}</i>" for s in learned_spells]
    )
    if not learned_spells_text: learned_spells_text = "<i>Вы еще не изучили ни одного заклинания.</i>"

    message_text = (
        f"🔮 Добро пожаловать в Школу Магов, {hd.quote(player['username'])}!\n"
        f"Здесь ты можешь изучить новые заклинания, если соответствуешь требованиям по уровню и интеллекту.\n"
        f"(Ваш Ур.: {player['level']}, Ваш Инт.: {player['intelligence']})\n\n" # Показываем текущие значения игрока
        f"<b>Изученные заклинания:</b>\n{learned_spells_text}\n\n"
        f"<b>Доступно для изучения:</b> (✅ - можно изучить, ❌ - нельзя)"
    )

    try:
        await message.answer(message_text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest as e:
         if "message is too long" in str(e):
              logging.warning(f"Magic school message too long for user {user_id}.")
              await message.answer("🔮 Школа Магов.\n<i>Список заклинаний слишком велик. Используйте кнопки ниже.</i>", reply_markup=keyboard)
         else:
              logging.error(f"Error sending magic school message for user {user_id}: {e}")
              await message.answer("Ошибка отображения школы магов.", reply_markup=keyboard)


# Обработчик нажатий кнопок в Школе Магов
@router.callback_query(F.data.startswith("magic:"))
async def handle_magic_school_action(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data_parts = callback.data.split(":") # magic:action:spell_id

    action = data_parts[1]

    if action == "close":
        await callback.answer("Знание - сила!")
        try: await callback.message.delete()
        except Exception: pass
        return
    if action == "noop":
        await callback.answer("Возвращайся, когда поднимешь уровень или интеллект.")
        return

    # Получаем ID спелла для info или learn
    try:
        spell_id = data_parts[2]
        spell_data = SPELLS.get(spell_id)
        if not spell_data: raise ValueError("Spell not found in SPELLS")
    except (IndexError, ValueError) as e:
        logging.error(f"Invalid magic school callback data: {callback.data} - {e}")
        await callback.answer("Ошибка данных заклинания.", show_alert=True)
        return

    # --- Показ Информации о недоступном спелле ---
    if action == "info":
        level_req = spell_data.get('level_req', '?')
        int_req = get_spell_intelligence_requirement(level_req if isinstance(level_req, int) else 999)
        description = spell_data.get('description', 'Нет описания.')
        mana_cost = spell_data.get('mana_cost', '?')

        info_text = (
            f"📜 <b>{hd.quote(spell_data['name'])}</b>\n"
            f"{description}\n\n"
            f"Требования: <b>Ур. {level_req}</b>, <b>Инт. {int_req}</b>\n"
            f"Стоимость: {mana_cost} Маны"
        )
        await callback.answer(info_text, show_alert=True, parse_mode="HTML")
        return

    # --- Изучение заклинания ---
    if action == "learn":
        await callback.answer(f"Изучаем '{spell_data['name']}'...")

        # Получаем АКТУАЛЬНЫЕ данные игрока перед изучением
        player = await get_player_effective_stats(user_id)
        level_req = spell_data.get('level_req', 999)
        int_req = get_spell_intelligence_requirement(level_req)

        # Проверяем уровень И ИНТЕЛЛЕКТ
        if not player:
             await callback.answer("Ошибка получения данных игрока.", show_alert=True)
             return
        if player['level'] < level_req:
             await callback.answer(f"Недостаточный уровень! Требуется {level_req}.", show_alert=True)
             return
        if player['intelligence'] < int_req:
             await callback.answer(f"Недостаточно интеллекта! Требуется {int_req}.", show_alert=True)
             return

        # Пытаемся изучить
        learned_success = await learn_spell(user_id, spell_id)

        if learned_success:
             logging.info(f"User {user_id} successfully learned spell '{spell_id}'.")
             await callback.answer(f"Заклинание '{spell_data['name']}' изучено!", show_alert=False)
             # Обновляем сообщение Школы Магов
             learned_spells_after = await get_learned_spells(user_id)
             learned_spell_ids_after = [s['id'] for s in learned_spells_after]
             # Передаем актуальный интеллект
             keyboard_after = get_magic_school_keyboard(player['level'], player['intelligence'], learned_spell_ids_after)
             # TODO: Обновить текст сообщения (перегенерировать)
             learned_spells_text_after = "\n".join(
                 [f" - {hd.quote(s['name'])} ({s['mana_cost']} Маны): <i>{s.get('description','-')}</i>" for s in learned_spells_after]
             ) or "<i>Нет изученных заклинаний.</i>"
             message_text_after = (
                 f"🔮 Школа Магов\n(Ур.: {player['level']}, Инт.: {player['intelligence']})\n\n"
                 f"<b>Изученные:</b>\n{learned_spells_text_after}\n\n"
                 f"<b>Доступно для изучения:</b> (✅/❌)"
             )
             try:
                 await callback.message.edit_text(message_text_after, reply_markup=keyboard_after, parse_mode="HTML")
             except Exception as e:
                  logging.warning(f"Could not edit magic school message after learning: {e}")
        else:
             # Проверяем, изучено ли уже (learn_spell вернет False и при ошибке, и при дубликате)
             learned_spells_check = await get_learned_spells(user_id)
             if spell_id in [s['id'] for s in learned_spells_check]:
                 await callback.answer("Это заклинание уже изучено.", show_alert=True)
             else:
                 await callback.answer("Не удалось изучить заклинание (ошибка).", show_alert=True)
