# handlers/gambler.py
import logging
import random
import math
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.text_decorations import html_decoration as hd

from database.db_manager import (
    get_player_effective_stats, update_player_xp, add_item_to_inventory,
    check_and_apply_regen
)
from game_data import (
    GAMBLER_BOX_COSTS, GAMBLER_REWARD_CHANCES, GAMBLER_ITEM_CHANCES,
    ALL_ITEMS, ITEM_TYPE_FRAGMENT, get_random_legendary_item_id
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - [%(filename)s:%(lineno)d] - %(message)s")
router = Router()

# Клавиатура для Гемблера
def get_gambler_keyboard(player_gold: int) -> InlineKeyboardMarkup:
    buttons = []
    for box_size, cost in GAMBLER_BOX_COSTS.items():
        can_afford = player_gold >= cost
        emoji = "✅" if can_afford else "❌"
        box_name = {"small": "Маленький", "medium": "Средний", "large": "Большой"}.get(box_size, box_size.capitalize())
        button_text = f"{emoji} {box_name} Ящик ({cost}💰)"
        callback_data = f"gamble:{box_size}:{cost}" if can_afford else f"gamble:info:{box_size}"
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])

    buttons.append([InlineKeyboardButton(text="Уйти", callback_data="gamble:close")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Обработчик для кнопки Гемблер
@router.message(F.text.lower() == "🎲 гемблер")
async def gambler_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    logging.info(f"User {user_id} approached the gambler.")
    try: await check_and_apply_regen(user_id, await state.get_state())
    except Exception as e: logging.error(f"Regen check error in gambler: {e}")

    player = await get_player_effective_stats(user_id)
    if not player:
        await message.answer("Сначала создайте персонажа: /start")
        return

    keyboard = get_gambler_keyboard(player['gold'])
    await message.answer(
        "🎲 Желаешь испытать удачу, изгнанник?\n"
        "Чем дороже ящик, тем выше шанс на хорошую награду... или на больший проигрыш!\n"
        f"<i>(Ваше золото: {player['gold']}💰)</i>",
        reply_markup=keyboard, parse_mode="HTML"
    )

# Обработчик нажатий кнопок у Гемблера
@router.callback_query(F.data.startswith("gamble:"))
async def handle_gamble_action(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data_parts = callback.data.split(":") # gamble:action/box_size:cost/box_size

    action_or_size = data_parts[1]

    if action_or_size == "close":
        await callback.answer("Удачи в следующий раз!")
        try: await callback.message.delete()
        except Exception: pass
        return
    if action_or_size == "info":
        await callback.answer("Недостаточно золота для этого ящика!", show_alert=True)
        return

    # Покупка ящика: gamble:box_size:cost
    try:
        box_size = action_or_size
        cost = int(data_parts[2])
        if box_size not in GAMBLER_BOX_COSTS or GAMBLER_BOX_COSTS[box_size] != cost:
            raise ValueError("Invalid box size or cost mismatch")
    except (IndexError, ValueError) as e:
        logging.error(f"Invalid gamble callback data: {callback.data} - {e}")
        await callback.answer("Ошибка данных ящика.", show_alert=True)
        return

    await callback.answer(f"Открываем {box_size} ящик...") # Временный ответ
    player = await get_player_effective_stats(user_id)
    if not player:
         await callback.answer("Ошибка получения данных игрока.", show_alert=True)
         return

    # Проверяем золото еще раз
    if player['gold'] < cost:
         await callback.answer(f"Недостаточно золота! Нужно {cost}💰.", show_alert=True)
         # Обновляем клавиатуру
         new_keyboard = get_gambler_keyboard(player['gold'])
         try: await callback.message.edit_reply_markup(reply_markup=new_keyboard)
         except Exception: pass
         return

    # --- Списываем золото ---
    success_gold, _ = await update_player_xp(user_id, gained_gold=-cost)
    if not success_gold:
        logging.error(f"Failed to deduct gold ({cost}) for gambler box for user {user_id}")
        await callback.answer("Ошибка при списании золота.", show_alert=True)
        return

    # --- Определяем тип награды ---
    reward_types = list(GAMBLER_REWARD_CHANCES.keys())
    reward_weights = list(GAMBLER_REWARD_CHANCES.values())
    chosen_reward_type = random.choices(reward_types, weights=reward_weights, k=1)[0]

    logging.info(f"User {user_id} opened '{box_size}' box (cost {cost}). Rolled reward type: {chosen_reward_type}")
    result_message = f"Вы открыли {box_size} ящик за {cost}💰...\n\n"

    # --- Генерация Награды ---
    if chosen_reward_type == "xp":
        min_xp = 10 * (list(GAMBLER_BOX_COSTS.keys()).index(box_size) + 1) # 10, 20, 30
        max_xp = 100 * (list(GAMBLER_BOX_COSTS.keys()).index(box_size) + 1) # 100, 200, 300
        xp_gained = random.randint(min_xp, max_xp)
        await update_player_xp(user_id, gained_xp=xp_gained)
        result_message += f"✨ Вы получили {xp_gained} опыта!"
        logging.info(f"Gambler reward: +{xp_gained} XP for user {user_id}")

    elif chosen_reward_type == "gold":
        # Шанс проиграть/выиграть примерно 60/40
        # Множитель от 0.2 до 2.0
        min_mult = 0.2
        max_mult = 2.0
        # Смещаем случайное число, чтобы чаще выпадали значения меньше 1
        roll = random.uniform(0, 1)
        multiplier = min_mult + (max_mult - min_mult) * (roll ** 1.5) # Степенная функция для смещения к <1

        gold_gained_or_lost = math.floor(cost * multiplier)
        # Чистая прибавка/убыток
        net_gold_change = gold_gained_or_lost - cost
        await update_player_xp(user_id, gained_gold=net_gold_change) # Передаем чистую разницу

        if net_gold_change >= 0:
             result_message += f"💰 Вам повезло! Вы выиграли {gold_gained_or_lost} золота (чистый +{net_gold_change}💰)!"
        else:
             result_message += f"💸 Увы... Вы получили только {gold_gained_or_lost} золота (чистый {net_gold_change}💰)."
        logging.info(f"Gambler reward: Gold change {net_gold_change} for user {user_id}")

    elif chosen_reward_type == "item":
        # Определяем редкость предмета
        item_rarities = list(GAMBLER_ITEM_CHANCES.keys())
        item_weights = list(GAMBLER_ITEM_CHANCES.values())
        chosen_rarity = random.choices(item_rarities, weights=item_weights, k=1)[0]
        logging.info(f"Gambler item reward: Rolled rarity '{chosen_rarity}' for user {user_id}")

        item_id_to_give = None
        item_info = None

        if chosen_rarity == "legendary":
            item_id_to_give = get_random_legendary_item_id()
        elif chosen_rarity == "fragment":
            # Даем случайный фрагмент из доступных
            fragment_ids = [id for id, data in ALL_ITEMS.items() if data.get('type') == ITEM_TYPE_FRAGMENT]
            if fragment_ids: item_id_to_give = random.choice(fragment_ids)
        else: # common, magic, rare
            # Выбираем случайный предмет нужной редкости (ИСКЛЮЧАЯ легендарки, фрагменты, квестовые)
            possible_items = [
                id for id, data in ALL_ITEMS.items()
                if data.get('rarity') == chosen_rarity and data.get('equipable') # Только надеваемые и нужной редкости
            ]
            if possible_items: item_id_to_give = random.choice(possible_items)

        if item_id_to_give:
            item_info = ALL_ITEMS.get(item_id_to_give)
            if item_info:
                added = await add_item_to_inventory(user_id, item_id_to_give)
                if added:
                    rarity_prefix = {"legendary": "✨ЛЕГЕНДАРНЫЙ✨", "fragment": "💎Фрагмент💎", "rare": "⭐Редкий⭐", "magic": "💧Магический💧"}.get(chosen_rarity, "")
                    result_message += f"🎁 Вы нашли предмет: {rarity_prefix} <b>{hd.quote(item_info['name'])}</b>!"
                    logging.info(f"Gambler reward: Item '{item_id_to_give}' ({item_info['name']}) added for user {user_id}")
                else:
                    result_message += "🎁 Вы что-то нашли, но не смогли поднять (ошибка инвентаря)."
                    logging.error(f"Failed to add gambler item '{item_id_to_give}' to inventory for user {user_id}")
            else:
                 result_message += "🎁 Вы что-то нашли, но оно рассыпалось в пыль (ошибка данных предмета)."
                 logging.error(f"Gambler rolled item_id '{item_id_to_give}' but it's not in ALL_ITEMS.")
        else:
            result_message += "💨 Ящик оказался почти пустым... Немного пыли." # Если не удалось найти предмет нужной редкости
            logging.warning(f"Could not find an item of rarity '{chosen_rarity}' for gambler reward for user {user_id}.")

    # Обновляем сообщение с результатом и клавиатуру гемблера
    player_after = await get_player_effective_stats(user_id) # Новое золото
    new_keyboard = get_gambler_keyboard(player_after['gold'])
    result_message += f"\n\n<i>(Ваше золото: {player_after['gold']}💰)</i>"
    try:
        await callback.message.edit_text(result_message, reply_markup=new_keyboard, parse_mode="HTML")
    except Exception as e:
        logging.warning(f"Could not edit gambler message after result: {e}")
        # Отправляем новым сообщением
        await callback.message.answer(result_message, reply_markup=new_keyboard, parse_mode="HTML")
