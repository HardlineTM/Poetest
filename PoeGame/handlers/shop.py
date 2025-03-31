# handlers/shop.py
import logging
import time
import random
import math
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.text_decorations import html_decoration as hd
from aiogram.exceptions import TelegramBadRequest # Импортируем для обработки ошибок API

from database.db_manager import (
    get_shop_items, update_shop_items, get_player_effective_stats,
    add_item_to_inventory, update_player_xp, check_and_apply_regen
)
from game_data import (
    ALL_ITEMS, SHOP_REFRESH_INTERVAL, SHOP_WEAPON_ITEMS, SHOP_ARMOR_ITEMS,
    SHOP_LEGENDARY_CHANCE, ITEM_TYPE_WEAPON, ITEM_TYPE_HELMET, ITEM_TYPE_CHEST,
    ITEM_TYPE_GLOVES, ITEM_TYPE_BOOTS, ITEM_TYPE_FRAGMENT, ITEM_TYPE_RING, # Добавил Fragment/Ring
    ITEM_TYPE_AMULET, ITEM_TYPE_BELT, # Добавил Amulet/Belt
    get_random_legendary_item_id
)
# Импортируем функцию форматирования статов
try:
    from handlers.inventory import format_item_stats
except ImportError:
    def format_item_stats(stats: dict) -> str: return "Ошибка: format_item_stats не найдена"
    logging.error("Could not import format_item_stats from handlers.inventory in shop.py")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - [%(filename)s:%(lineno)d] - %(message)s")
router = Router()

# Словарь эмодзи для типов предметов
ITEM_TYPE_EMOJI = {
    "helmet": "🎓", "chest": "👕", "gloves": "🧤", "boots": "👢", "weapon": "⚔️",
    "ring": "💍", "amulet": "📿", "belt": "🎗️",
    "fragment": "💎",
    "legendary_helmet": "👑", "legendary_chest": "⚜️", "legendary_gloves": "✨",
    "legendary_boots": "🚀", "legendary_ring": "💎", "legendary_amulet": "🧿",
    "legendary_belt": "🔗", "legendary_weapon": "🔥",
    "default": '❓'
}

# --- Вспомогательные функции ---

async def refresh_shop_if_needed(shop_type: str) -> list[str]:
    """Проверяет время обновления магазина и обновляет ассортимент при необходимости."""
    current_time = int(time.time())
    current_item_ids, last_refresh = await get_shop_items(shop_type)

    if current_time - last_refresh >= SHOP_REFRESH_INTERVAL or not current_item_ids:
        logging.info(f"Refreshing shop '{shop_type}'...")
        new_item_ids = []
        item_count = 0
        allowed_types = []
        legendary_added = False

        if shop_type == 'weapon_shop':
            item_count = SHOP_WEAPON_ITEMS
            allowed_types = [ITEM_TYPE_WEAPON]
            if random.random() < SHOP_LEGENDARY_CHANCE:
                 leg_id = get_random_legendary_item_id()
                 if leg_id and ALL_ITEMS.get(leg_id):
                     item_data = ALL_ITEMS[leg_id]
                     # Добавляем только если это оружие (или можно любую легу?)
                     if item_data.get('equipable') and item_data.get('type', '').endswith(ITEM_TYPE_WEAPON):
                         new_item_ids.append(leg_id)
                         legendary_added = True
                         logging.info(f"Legendary weapon '{leg_id}' added to weapon shop!")

        elif shop_type == 'armor_shop':
            item_count = SHOP_ARMOR_ITEMS
            allowed_types = [ITEM_TYPE_HELMET, ITEM_TYPE_CHEST, ITEM_TYPE_GLOVES, ITEM_TYPE_BOOTS]
            if random.random() < SHOP_LEGENDARY_CHANCE:
                 leg_id = get_random_legendary_item_id()
                 if leg_id and ALL_ITEMS.get(leg_id):
                      item_data = ALL_ITEMS[leg_id]
                      # Добавляем только если это броня
                      if item_data.get('equipable') and item_data.get('type', '') in [f'legendary_{t}' for t in allowed_types]:
                          new_item_ids.append(leg_id)
                          legendary_added = True
                          logging.info(f"Legendary armor '{leg_id}' added to armor shop!")

        # Фильтруем обычные предметы нужного типа
        possible_items = [
            item_id for item_id, data in ALL_ITEMS.items()
            if data.get('type') in allowed_types and data.get('rarity') != 'legendary' and data.get('rarity') != 'quest'
        ]

        items_needed = item_count - len(new_item_ids)
        if possible_items and items_needed > 0:
             chosen_items = random.sample(possible_items, min(len(possible_items), items_needed))
             new_item_ids.extend(chosen_items)
        elif items_needed > 0:
             logging.warning(f"Not enough non-legendary items of types {allowed_types} to fill the shop '{shop_type}'.")

        await update_shop_items(shop_type, new_item_ids)
        return new_item_ids
    else:
        return current_item_ids

def get_shop_action_keyboard(shop_type: str, item_ids: list[str], player_gold: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопками Инфо и Купить/Не хватает."""
    buttons = []
    if not item_ids:
        buttons.append([InlineKeyboardButton(text="Магазин пуст", callback_data="shop:noop")])
    else:
        # Сортируем: сначала легендарки, потом по цене
        item_ids.sort(key=lambda x: (ALL_ITEMS.get(x, {}).get('rarity', '') != 'legendary', ALL_ITEMS.get(x, {}).get('cost', 99999)))

        for item_id in item_ids:
            item_data = ALL_ITEMS.get(item_id)
            if item_data:
                price = item_data.get('cost', 99999)
                can_afford = player_gold >= price
                type_emoji = ITEM_TYPE_EMOJI.get(item_data.get('type'), ITEM_TYPE_EMOJI['default'])
                item_name_short = hd.quote(item_data['name'])
                rarity_marker = "✨" if item_data.get('rarity') == 'legendary' else ""

                # Кнопка Инфо
                info_button = InlineKeyboardButton(
                    text=f"ℹ️ {type_emoji}{rarity_marker} {item_name_short} ({price}💰)",
                    callback_data=f"shop:{shop_type}:info:{item_id}"
                )

                # Кнопка Купить (если хватает денег)
                if can_afford:
                    action_button = InlineKeyboardButton(
                        text="Купить ✅",
                        callback_data=f"shop:{shop_type}:buy:{item_id}:{price}"
                    )
                    # Добавляем обе кнопки в один ряд
                    buttons.append([info_button, action_button])
                else:
                    # Если не хватает денег, только кнопка Инфо
                    buttons.append([info_button])

    buttons.append([InlineKeyboardButton(text="Обновить (завтра)", callback_data=f"shop:{shop_type}:refresh_info")])
    buttons.append([InlineKeyboardButton(text="Закрыть", callback_data=f"shop:{shop_type}:close")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def format_shop_message_text(shop_title: str, item_ids: list[str], player_gold: int) -> str:
    """Генерирует основной текст сообщения для магазина, включая статы."""
    shop_text = f"{shop_title} (Обновляется раз в день)\nВаше золото: {player_gold}💰\n\n"
    if not item_ids:
        shop_text += "<i>Ассортимент пуст. Загляните позже!</i>"
    else:
        shop_text += "<b>Товары в наличии:</b>\n"
        # Сортируем так же, как в клавиатуре
        item_ids.sort(key=lambda x: (ALL_ITEMS.get(x, {}).get('rarity', '') != 'legendary', ALL_ITEMS.get(x, {}).get('cost', 99999)))

        for item_id in item_ids:
            item_data = ALL_ITEMS.get(item_id)
            if item_data:
                price = item_data.get('cost', '??')
                stats_str = format_item_stats(item_data.get('stats', {}))
                rarity_color = {"common": "", "magic": "🔹", "rare": "⭐", "legendary": "✨"}.get(item_data.get('rarity', ''), '')
                type_emoji = ITEM_TYPE_EMOJI.get(item_data.get('type'), ITEM_TYPE_EMOJI['default'])

                shop_text += f"\n{type_emoji} <b>{hd.quote(item_data['name'])}</b> {rarity_color}\n"
                shop_text += f"<pre>{stats_str}</pre>\n"
                shop_text += f"Цена: {price}💰\n"
        shop_text += "\n<i>Нажмите ℹ️ для подробной информации или ✅ для покупки.</i>"
    return shop_text

# --- Обработчики входа в магазин ---
async def show_shop(message: types.Message, state: FSMContext, shop_type: str, shop_title: str):
    user_id = message.from_user.id
    logging.info(f"User {user_id} entered {shop_type}.")
    try: await check_and_apply_regen(user_id, await state.get_state())
    except Exception as e: logging.error(f"Regen check error in {shop_type}: {e}")

    player = await get_player_effective_stats(user_id)
    if not player:
        await message.answer("Сначала создайте персонажа: /start")
        return

    item_ids = await refresh_shop_if_needed(shop_type)
    keyboard = get_shop_action_keyboard(shop_type, item_ids, player['gold'])
    shop_text = format_shop_message_text(shop_title, item_ids, player['gold'])

    try:
        await message.answer(shop_text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest as e:
         # Частая ошибка - сообщение слишком длинное
         if "message is too long" in str(e):
              logging.warning(f"Shop message too long for user {user_id}. Sending short version.")
              await message.answer(f"{shop_title}\nВаше золото: {player['gold']}💰\n\n<i>Ассортимент слишком велик для отображения здесь. Используйте кнопки ниже.</i>", reply_markup=keyboard)
         else:
              logging.error(f"Error sending shop message for user {user_id}: {e}")
              await message.answer("Ошибка отображения магазина.", reply_markup=keyboard)


@router.message(F.text.lower() == "🛒 магазин оружия")
async def weapon_shop_start(message: types.Message, state: FSMContext):
    await show_shop(message, state, 'weapon_shop', '🛒 Магазин Оружия')

@router.message(F.text.lower() == "🛡️ магазин брони")
async def armor_shop_start(message: types.Message, state: FSMContext):
    await show_shop(message, state, 'armor_shop', '🛡️ Магазин Брони')


# --- Обработчик нажатий на кнопки магазина ---
@router.callback_query(F.data.startswith("shop:"))
async def handle_shop_action(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data_parts = callback.data.split(":") # shop:shop_type:action:item_id[:price]

    # --- ИСПРАВЛЕНО: Заменяем псевдокод на return ---
    if len(data_parts) < 3:
        logging.error(f"Invalid shop callback data (too few parts): {callback.data}")
        await callback.answer("Ошибка данных.", show_alert=True)
        return

    shop_type = data_parts[1]
    action = data_parts[2]
    shop_title = "🛒 Магазин Оружия" if shop_type == 'weapon_shop' else "🛡️ Магазин Брони"

    if action == "close":
        await callback.answer("Магазин закрыт.")
        try: await callback.message.delete()
        except Exception: pass
        return
    if action == "noop":
        await callback.answer("Магазин пуст.")
        return
    if action == "refresh_info":
        _, last_refresh = await get_shop_items(shop_type)
        time_left = SHOP_REFRESH_INTERVAL - (int(time.time()) - last_refresh)
        if time_left > 0:
             hours, rem = divmod(time_left, 3600)
             mins, _ = divmod(rem, 60)
             time_left_str = f"~{int(hours)}ч {int(mins)}м" if hours > 0 else f"~{int(mins)}м"
             await callback.answer(f"Ассортимент обновится через {time_left_str}.", show_alert=True)
        else:
             await callback.answer("Ассортимент должен скоро обновиться!", show_alert=True)
        return
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

    # Для 'buy', 'info', 'back' нужен item_id (или он не нужен для back)
    item_id = None
    item_data = None
    price = 0
    if action in ["buy", "info"]:
         try:
             item_id = data_parts[3]
             item_data = ALL_ITEMS.get(item_id)
             if not item_data: raise ValueError("Item not found in ALL_ITEMS")
             price = int(data_parts[4]) if action == "buy" and len(data_parts) > 4 else item_data.get('cost', 99999)
         except (IndexError, ValueError) as e:
             # --- ИСПРАВЛЕНО: Заменяем псевдокод на return ---
             logging.error(f"Invalid item data in shop callback: {callback.data} - {e}")
             await callback.answer("Ошибка данных предмета.", show_alert=True)
             return
             # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

    # --- Кнопка Назад к магазину ---
    if action == "back":
        player = await get_player_effective_stats(user_id)
        if not player: return
        item_ids = await get_shop_items(shop_type)
        keyboard = get_shop_action_keyboard(shop_type, item_ids, player['gold'])
        shop_text = format_shop_message_text(shop_title, item_ids, player['gold'])
        try:
            await callback.message.edit_text(shop_text, reply_markup=keyboard, parse_mode="HTML")
            await callback.answer()
        except Exception as e:
             logging.error(f"Error going back to shop {shop_type} for user {user_id}: {e}")
             await callback.answer("Ошибка возврата в магазин.", show_alert=True)
        return
    # --- Конец кнопки Назад ---

    # --- Показ информации о предмете (action == "info") ---
    if action == "info":
        if not item_data: return # Проверка
        stats_str = format_item_stats(item_data.get('stats', {}))
        description = item_data.get('description', '')
        cost_str = f"Цена: {item_data.get('cost', '???')}💰"
        equip_str = "Можно надеть" if item_data.get('equipable') else "Нельзя надеть"
        rarity = item_data.get('rarity', 'unknown').capitalize()
        type_name = item_data.get('type', 'Неизвестный тип')
        type_emoji = ITEM_TYPE_EMOJI.get(item_data.get('type'), ITEM_TYPE_EMOJI['default'])

        info_text = (
            f"{type_emoji} <b>{hd.quote(item_data['name'])}</b> ({rarity})\n"
            f"Тип: {type_name}\n<i>{equip_str}</i>\n\n"
            f"<b>Характеристики:</b>\n<pre>{stats_str}</pre>\n\n"
            f"<b>Описание:</b>\n<i>{description if description else '-'}</i>\n\n"
            f"{cost_str}"
        )
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к магазину", callback_data=f"shop:{shop_type}:back")]
        ])
        try:
            await callback.message.edit_text(info_text, reply_markup=back_keyboard, parse_mode="HTML")
            await callback.answer()
        except TelegramBadRequest as e:
             if "message is not modified" in str(e): await callback.answer()
             else:
                 logging.error(f"Error editing message for item info {item_id}: {e}")
                 await callback.answer("Не удалось показать информацию.", show_alert=True)
        except Exception as e:
             logging.error(f"Unexpected error editing message for item info {item_id}: {e}")
             await callback.answer("Ошибка.", show_alert=True)
        return

    # --- Покупка предмета (action == "buy") ---
    if action == "buy":
        if not item_data: return # Проверка
        await callback.answer("Покупаем...")
        logging.info(f"Attempting purchase: User {user_id}, Item {item_id}, Price {price}, Shop {shop_type}")
        player = await get_player_effective_stats(user_id)
        # --- ИСПРАВЛЕНО: Заменяем псевдокод на return ---
        if not player:
             await callback.answer("Ошибка получения данных игрока.", show_alert=True)
             return
        # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

        server_price = item_data.get('cost', 99999)
        # --- ИСПРАВЛЕНО: Заменяем псевдокод на return ---
        if price != server_price:
             logging.warning(f"Price mismatch for item {item_id} in {shop_type}. Callback: {price}, Server: {server_price}")
             current_item_ids, _ = await get_shop_items(shop_type)
             # Обновляем клавиатуру, чтобы показать правильную цену/доступность
             new_keyboard = get_shop_action_keyboard(shop_type, current_item_ids, player['gold'])
             try: await callback.message.edit_reply_markup(reply_markup=new_keyboard)
             except Exception: pass
             await callback.answer("Цена изменилась! Попробуйте еще раз.", show_alert=True)
             return
        # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

        # --- ИСПРАВЛЕНО: Заменяем псевдокод на return ---
        if player['gold'] < price:
             await callback.answer(f"Недостаточно золота! Нужно {price}💰.", show_alert=True)
             return
        # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

        # Списываем золото
        await update_player_xp(user_id, gained_gold=-price)
        logging.info(f"Gold deducted for user {user_id}. Adding item to inventory...")

        # Добавляем предмет
        success_add = await add_item_to_inventory(user_id, item_id)
        logging.info(f"Add item result for user {user_id}, item {item_id}: {success_add}")

        if not success_add:
             logging.error(f"Failed to add item {item_id} to inventory for user {user_id} after purchase. Attempting to return gold...")
             await update_player_xp(user_id, gained_gold=price)
             logging.info(f"Returned {price} gold to user {user_id} due to inventory add failure.")
             await callback.answer("Ошибка при добавлении предмета! Золото возвращено.", show_alert=True)
             return

        # Успешная покупка
        logging.info(f"Item {item_id} added successfully for user {user_id}. Updating shop message...")
        player_after_purchase = await get_player_effective_stats(user_id)
        current_item_ids, _ = await get_shop_items(shop_type)
        new_keyboard = get_shop_action_keyboard(shop_type, current_item_ids, player_after_purchase['gold'])
        purchase_message = f"✅ Вы купили '<b>{hd.quote(item_data['name'])}</b>' за {price}💰!"

        # Перегенерируем текст магазина
        new_shop_text = format_shop_message_text(shop_title, current_item_ids, player_after_purchase['gold'])
        final_text = f"{purchase_message}\n\n{new_shop_text}"

        try:
            await callback.message.edit_text(final_text, reply_markup=new_keyboard, parse_mode="HTML")
            logging.info(f"Shop message updated after purchase for user {user_id}.")
        except TelegramBadRequest as e:
             if "message is not modified" in str(e):
                 logging.warning(f"Message not modified when updating shop after purchase for {user_id}.")
                 await callback.answer(purchase_message, show_alert=False)
             else:
                  logging.error(f"Error editing shop message after purchase for user {user_id}: {e}")
                  await callback.answer("Ошибка обновления магазина.", show_alert=True)
        except Exception as e:
             logging.error(f"Unexpected error editing shop message after purchase for user {user_id}: {e}")
             await callback.answer("Ошибка обновления магазина.", show_alert=True)

# --- Конец файла handlers/shop.py ---
