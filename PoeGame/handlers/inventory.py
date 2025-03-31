# handlers/inventory.py
import logging
import math # Добавили math
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.text_decorations import html_decoration as hd

# Импортируем функции БД и данные
# --- ИСПРАВЛЕНИЕ: Добавляем delete_item_from_inventory в импорт ---
from database.db_manager import (
    get_inventory_items, get_item_from_inventory, equip_item, unequip_item,
    get_player_effective_stats, check_and_apply_regen,
    delete_item_from_inventory, # <--- ДОБАВЛЕНО ЗДЕСЬ
    update_player_xp # Нужен для начисления золота при продаже
)
# --- КОНЕЦ ИСПРАВЛЕНИЯ ---
from game_data import (
    ALL_ITEMS, ITEM_SLOTS, SLOT_RING1, SLOT_RING2, ITEM_TYPE_RING,
    SLOT_HELMET, SLOT_CHEST, SLOT_GLOVES, SLOT_BOOTS, SLOT_AMULET, SLOT_BELT,
    ITEM_TYPE_FRAGMENT # Нужен для подсчета в кузнеце, но здесь тоже не помешает
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - [%(filename)s:%(lineno)d] - %(message)s")
router = Router()

# --- Состояния для Экипировки ---
class EquipStates(StatesGroup):
    choosing_slot = State() # Ожидание выбора слота (особенно для колец)

# --- Вспомогательные функции ---

def format_item_stats(stats: dict) -> str:
    """Форматирует словарь статов предмета в строку."""
    if not stats:
        return "<i>(Нет бонусов)</i>"
    lines = []
    stat_map = {
        'max_hp': '❤️ Макс. HP', 'max_mana': '💧 Макс. Mana',
        'strength': '💪 Сила', 'dexterity': '🏹 Ловкость', 'intelligence': '🧠 Интеллект',
        'armor': '🦾 Броня', 'max_energy_shield': '🛡️ Макс. Энергощит'
        # Добавить другие статы по мере их появления
    }
    for stat_name, value in stats.items():
        display_name = stat_map.get(stat_name, stat_name)
        # Добавляем знак + для положительных значений
        if isinstance(value, (int, float)) and value > 0:
             lines.append(f"{display_name}: +{value}")
        elif isinstance(value, (int, float)) and value < 0: # На случай отрицательных статов
             lines.append(f"{display_name}: {value}")
        else: # Для нулевых или нечисловых (хотя их не должно быть)
             lines.append(f"{display_name}: {value}")

    return "\n".join(lines) if lines else "<i>(Нет бонусов)</i>"

def get_inventory_keyboard(items: list[dict]) -> InlineKeyboardMarkup:
    """Создает клавиатуру для отображения инвентаря с кнопками надеть/снять/продать."""
    buttons = []
    if not items:
        buttons.append([InlineKeyboardButton(text="Инвентарь пуст", callback_data="inv:noop")])
    else:
        items.sort(key=lambda x: (not x['is_equipped'], x['type'], x['name']))
        for item in items:
            item_data_from_all = ALL_ITEMS.get(item['item_id'], {}) # Получаем данные из ALL_ITEMS
            item_cost = item_data_from_all.get('cost', 0) # Базовая цена
            sell_price = math.floor(item_cost * 0.5) if item_cost > 0 else 0 # Цена продажи (50%)

        for item in items:
            type_emoji = {
                "helmet": "🎓", "chest": "👕", "gloves": "🧤", "boots": "👢",
                "ring": "💍", "amulet": "📿", "belt": "🎗️"
            }.get(item['type'], '❓')

            if item['is_equipped']:
                equip_status_prefix = "✅ "
                equip_slot_info = f" ({item['equipped_slot']})"
                # Кнопка для снятия
                action_button = InlineKeyboardButton(
                    text=f"{equip_status_prefix}{type_emoji} {hd.quote(item['name'])}{equip_slot_info} (Снять)",
                    callback_data=f"inv:unequip:{item['inventory_id']}"
                )
                buttons.append([action_button])
            else: # Предмет не надет
                # Кнопка для надевания
                equip_button = InlineKeyboardButton(
                    text=f"{type_emoji} {hd.quote(item['name'])} (Надеть)",
                    callback_data=f"inv:equip:{item['inventory_id']}"
                )
                # Кнопка для продажи (если цена > 0)
                if sell_price > 0:
                    sell_button = InlineKeyboardButton(
                        text=f"Продать 🗑️ ({sell_price}💰)",
                        callback_data=f"inv:sell:{item['inventory_id']}:{sell_price}" # Передаем цену продажи
                    )
                    # Помещаем кнопки "Надеть" и "Продать" в один ряд
                    buttons.append([equip_button, sell_button])
                else:
                     # Если предмет нельзя продать, только кнопка "Надеть"
                     buttons.append([equip_button])

    buttons.append([InlineKeyboardButton(text="Закрыть", callback_data="inv:close")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_slot_selection_keyboard(item_type: str, inventory_id: int) -> InlineKeyboardMarkup | None:
     """Создает клавиатуру для выбора слота экипировки."""
     allowed_slots = ITEM_SLOTS.get(item_type)
     if not allowed_slots: return None

     buttons = []
     if item_type == ITEM_TYPE_RING:
         buttons.append([InlineKeyboardButton(text="💍 Кольцо 1", callback_data=f"equip_slot:{inventory_id}:{SLOT_RING1}")])
         buttons.append([InlineKeyboardButton(text="💍 Кольцо 2", callback_data=f"equip_slot:{inventory_id}:{SLOT_RING2}")])
     elif len(allowed_slots) == 1:
         return None # Выбор не требуется, слот один
     else: # Для других типов с >1 слота (если появятся)
         for slot in allowed_slots:
             buttons.append([InlineKeyboardButton(text=f"Слот: {slot}", callback_data=f"equip_slot:{inventory_id}:{slot}")])

     buttons.append([InlineKeyboardButton(text="Отмена", callback_data=f"equip_slot:{inventory_id}:cancel")])
     return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- Обработчики ---

# Обработчик для кнопки "Инвентарь"
@router.message(F.text.lower() == "🎒 инвентарь")
async def show_inventory(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    logging.info(f"User {user_id} requested inventory.")
    # --- Вызов проверки регенерации ---
    try:
        current_state_str = await state.get_state()
        await check_and_apply_regen(user_id, current_state_str) # <-- Теперь функция должна быть найдена
    except Exception as e:
        logging.error(f"Error during regen check in show_inventory for user {user_id}: {e}", exc_info=False)


    inventory_items = await get_inventory_items(user_id)
    player_exists = await get_player_effective_stats(user_id) # Проверяем существование игрока

    if not player_exists:
         await message.answer("Сначала создайте персонажа: /start")
         return

    keyboard = get_inventory_keyboard(inventory_items)
    text = "🎒 <b>Ваш инвентарь:</b>\n\n"
    if not inventory_items:
        text += "Пусто..."
    else:
        # Показываем сначала экипированные предметы
        text += "<u>Надето:</u>\n"
        equipped_found = False
        for item in inventory_items:
            if item['is_equipped']:
                equipped_found = True
                type_emoji = {"helmet": "🎓", "chest": "👕", "gloves": "🧤", "boots": "👢","ring": "💍", "amulet": "📿", "belt": "🎗️"}.get(item['type'], '❓')
                item_stats_str = format_item_stats(item.get('stats', {}))
                text += f"{type_emoji} <b>{hd.quote(item['name'])}</b> ({item['equipped_slot']}):\n<pre>{item_stats_str}</pre>\n" # Используем <pre> для моноширинного текста статов

        if not equipped_found:
            text += "<i>Ничего не надето</i>\n"

        text += "\n<u>В сумках:</u>\n"
        unequipped_found = False
        for item in inventory_items:
             if not item['is_equipped']:
                 unequipped_found = True
                 type_emoji = {"helmet": "🎓", "chest": "👕", "gloves": "🧤", "boots": "👢","ring": "💍", "amulet": "📿", "belt": "🎗️"}.get(item['type'], '❓')
                 item_stats_str = format_item_stats(item.get('stats', {}))
                 text += f"{type_emoji} <b>{hd.quote(item['name'])}</b>:\n<pre>{item_stats_str}</pre>\n"

        if not unequipped_found:
             text += "<i>Рюкзак пуст</i>\n"

        text += "\n<i>Нажмите на предмет в меню ниже, чтобы надеть/снять его.</i>"


    try:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        # Если сообщение слишком длинное или ошибка разметки
        logging.error(f"Error sending inventory message for user {user_id}: {e}")
        await message.answer("🎒 **Ваш инвентарь:**\n\nНе удалось отобразить список предметов. Используйте кнопки ниже.", reply_markup=keyboard)


# Обработчик нажатий кнопок в инвентаре
@router.callback_query(F.data.startswith("inv:"))
async def handle_inventory_action(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    action_data = callback.data.split(":") # inv:action:inventory_id

    action = action_data[1]
    logging.debug(f"Inventory action '{action}' for user {user_id}, data: {callback.data}")

    if action == "close":
        await callback.answer("Инвентарь закрыт.")
        try: await callback.message.delete()
        except Exception: pass
        return
    if action == "noop":
        await callback.answer("В инвентаре пусто.")
        return

    try:
        inventory_id = int(action_data[2])
    except (IndexError, ValueError):
        logging.error(f"Invalid inventory callback data (inventory_id): {callback.data}")
        await callback.answer("Ошибка данных предмета.", show_alert=True)
        return

    # --- Снятие предмета ---
    if action == "unequip":
        await callback.answer("Снимаем предмет...") # Временный ответ
        success, message_text = await unequip_item(user_id, inventory_id)
        if success:
            logging.info(f"Item inv_id:{inventory_id} unequipped by user {user_id}.")
            # Обновляем сообщение с инвентарем
            inventory_items = await get_inventory_items(user_id)
            keyboard = get_inventory_keyboard(inventory_items)
            new_text = f"{message_text}\n\n🎒 **Ваш инвентарь:**" # TODO: Можно перегенерировать полный текст, как в show_inventory
            try:
                 await callback.message.edit_text(new_text, reply_markup=keyboard, parse_mode="HTML")
            except Exception as e:
                 logging.warning(f"Could not edit inventory message after unequip: {e}")
                 await callback.message.answer(new_text, reply_markup=keyboard, parse_mode="HTML")
                 try: await callback.message.delete()
                 except Exception: pass
        else:
            logging.warning(f"Failed to unequip item inv_id:{inventory_id} for user {user_id}: {message_text}")
            await callback.answer(message_text, show_alert=True)

    # --- Надевание предмета ---
    elif action == "equip":
        await callback.answer("Надеваем предмет...") # Временный ответ
        item_to_equip = await get_item_from_inventory(inventory_id)

        if not item_to_equip or item_to_equip['player_id'] != user_id:
            logging.warning(f"Equip failed: Item inv_id:{inventory_id} not found or wrong owner for user {user_id}.")
            await callback.answer("Предмет не найден или не принадлежит вам.", show_alert=True)
            return
        if item_to_equip['is_equipped']:
             logging.debug(f"Equip cancelled: Item inv_id:{inventory_id} already equipped by user {user_id}.")
             await callback.answer("Предмет уже надет.", show_alert=True)
             return

        item_type = item_to_equip['type']
        slot_keyboard = get_slot_selection_keyboard(item_type, inventory_id)

        if slot_keyboard:
            # Требуется выбор слота
            logging.info(f"User {user_id} needs to choose slot for item inv_id:{inventory_id}")
            try:
                await callback.message.edit_text(
                    f"Выберите слот для предмета '<b>{hd.quote(item_to_equip['name'])}</b>':",
                    reply_markup=slot_keyboard,
                    parse_mode="HTML"
                )
                await state.set_state(EquipStates.choosing_slot)
                # Сохраняем ID предмета, который пытаемся надеть, в состояние
                await state.update_data(item_to_equip_inv_id=inventory_id)
            except Exception as e:
                 logging.error(f"Error showing slot selection for user {user_id}, item {inventory_id}: {e}")
                 await callback.answer("Ошибка отображения выбора слота.", show_alert=True)

        else:
            # Слот только один, надеваем сразу
            allowed_slots = ITEM_SLOTS.get(item_type)
            if allowed_slots and len(allowed_slots) == 1:
                target_slot = allowed_slots[0]
                logging.info(f"Auto-equipping item inv_id:{inventory_id} to single slot '{target_slot}' for user {user_id}.")
                success, message_text = await equip_item(user_id, inventory_id, target_slot)
                if success:
                    logging.info(f"Item inv_id:{inventory_id} equipped by user {user_id} to slot '{target_slot}'.")
                    inventory_items = await get_inventory_items(user_id)
                    keyboard = get_inventory_keyboard(inventory_items)
                    new_text = f"{message_text}\n\n🎒 **Ваш инвентарь:**" # TODO: Можно перегенерировать полный текст
                    try:
                         await callback.message.edit_text(new_text, reply_markup=keyboard, parse_mode="HTML")
                    except Exception as e:
                         logging.warning(f"Could not edit inventory message after auto-equip: {e}")
                         await callback.message.answer(new_text, reply_markup=keyboard, parse_mode="HTML")
                         try: await callback.message.delete()
                         except Exception: pass
                else:
                    logging.warning(f"Failed to auto-equip item inv_id:{inventory_id} for user {user_id}: {message_text}")
                    await callback.answer(message_text, show_alert=True)
            else:
                logging.error(f"Cannot auto-equip item inv_id:{inventory_id} for user {user_id}: No single slot defined for type '{item_type}'.")
                await callback.answer(f"Не удалось определить единственный слот для предмета типа '{item_type}'.", show_alert=True)
    # --- Продажа предмета ---
    elif action == "sell":
        try:
            # Получаем цену продажи из callback для проверки
            expected_sell_price = int(action_data[3])
        except (IndexError, ValueError):
            logging.error(f"Invalid sell callback data (price missing): {callback.data}")
            await callback.answer("Ошибка данных продажи.", show_alert=True)
            return

        await callback.answer("Продаем предмет...")
        item_to_sell = await get_item_from_inventory(inventory_id)

        if not item_to_sell or item_to_sell['player_id'] != user_id:
            await callback.answer("Предмет не найден или не принадлежит вам.", show_alert=True)
            return
        if item_to_sell['is_equipped']:
             await callback.answer("Сначала снимите предмет, чтобы продать.", show_alert=True)
             return

        # Получаем базовую цену и считаем цену продажи на сервере
        item_base_cost = ALL_ITEMS.get(item_to_sell['item_id'], {}).get('cost', 0)
        actual_sell_price = math.floor(item_base_cost * 0.5) if item_base_cost > 0 else 0

        if actual_sell_price <= 0:
             await callback.answer("Этот предмет нельзя продать.", show_alert=True)
             return
        # Проверяем совпадение цены (защита от старых кнопок)
        if actual_sell_price != expected_sell_price:
             logging.warning(f"Sell price mismatch for inv_id {inventory_id}. CB: {expected_sell_price}, Server: {actual_sell_price}")
             await callback.answer("Цена продажи изменилась! Попробуйте снова.", show_alert=True)
             # Обновляем клавиатуру инвентаря
             inventory_items_refresh = await get_inventory_items(user_id)
             keyboard_refresh = get_inventory_keyboard(inventory_items_refresh)
             try: await callback.message.edit_reply_markup(reply_markup=keyboard_refresh)
             except Exception: pass
             return

        # Удаляем предмет из БД
        deleted = await delete_item_from_inventory(inventory_id)
        if not deleted:
             await callback.answer("Не удалось удалить предмет из инвентаря.", show_alert=True)
             return

        # Начисляем золото
        await update_player_xp(user_id, gained_gold=actual_sell_price)
        logging.info(f"User {user_id} sold item inv_id:{inventory_id} ('{item_to_sell.get('name','???')}') for {actual_sell_price} gold.")

        # Обновляем сообщение инвентаря
        inventory_items_after_sell = await get_inventory_items(user_id)
        keyboard_after_sell = get_inventory_keyboard(inventory_items_after_sell)
        sell_message = f"🗑️ Вы продали '{hd.quote(item_to_sell['name'])}' за {actual_sell_price}💰."
        # TODO: Обновить текст сообщения полностью, как в show_inventory
        new_text = f"{sell_message}\n\n🎒 **Ваш инвентарь:**"
        try:
            await callback.message.edit_text(new_text, reply_markup=keyboard_after_sell, parse_mode="HTML")
        except Exception as e:
            logging.warning(f"Could not edit inventory message after sell: {e}")
            await callback.message.answer(sell_message, parse_mode="HTML")
            await callback.message.answer("🎒 Ваш инвентарь:", reply_markup=keyboard_after_sell)
            try: await callback.message.delete() # Удаляем старое
            except Exception: pass

    else:
         logging.warning(f"Unknown inventory action '{action}' from user {user_id}. Callback: {callback.data}")
         await callback.answer("Неизвестное действие.", show_alert=True)


# Обработчик выбора слота (когда нажали кнопку слота)
@router.callback_query(EquipStates.choosing_slot, F.data.startswith("equip_slot:"))
async def handle_slot_selection(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    action_data = callback.data.split(":") # equip_slot:inventory_id:slot_name / cancel

    try:
        inventory_id = int(action_data[1])
        target_slot = action_data[2]
    except (IndexError, ValueError):
        logging.error(f"Invalid slot selection callback data format: {callback.data}")
        await callback.answer("Ошибка данных слота.", show_alert=True)
        await state.clear()
        # Попытаемся вернуть к инвентарю
        inventory_items = await get_inventory_items(user_id)
        keyboard = get_inventory_keyboard(inventory_items)
        try: await callback.message.edit_text("Ошибка выбора слота. Ваш инвентарь:", reply_markup=keyboard)
        except Exception: pass
        return

    logging.debug(f"Slot selection action for user {user_id}: slot='{target_slot}', inv_id='{inventory_id}'")

    if target_slot == "cancel":
        await callback.answer("Отмена выбора слота.")
        # Возвращаем к списку инвентаря
        inventory_items = await get_inventory_items(user_id)
        keyboard = get_inventory_keyboard(inventory_items)
        # TODO: Можно перегенерировать полный текст инвентаря
        new_text = "🎒 **Ваш инвентарь:**\n\nВыберите предмет..."
        try: await callback.message.edit_text(new_text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as e:
            logging.warning(f"Could not edit message on slot selection cancel: {e}")
        await state.clear()
        return

    # Проверяем, совпадает ли inventory_id из callback с тем, что в state
    state_data = await state.get_data()
    item_to_equip_inv_id = state_data.get("item_to_equip_inv_id")
    if item_to_equip_inv_id != inventory_id:
         logging.warning(f"Inventory ID mismatch in slot selection state for user {user_id}. State: {item_to_equip_inv_id}, Callback: {inventory_id}")
         await callback.answer("Ошибка состояния выбора предмета.", show_alert=True)
         await state.clear()
         # Вернуть к инвентарю
         inventory_items = await get_inventory_items(user_id)
         keyboard = get_inventory_keyboard(inventory_items)
         try: await callback.message.edit_text("Ошибка состояния. Ваш инвентарь:", reply_markup=keyboard)
         except Exception: pass
         return

    # Надеваем предмет в выбранный слот
    logging.info(f"Attempting to equip item inv_id:{inventory_id} to slot '{target_slot}' for user {user_id}")
    success, message_text = await equip_item(user_id, inventory_id, target_slot)
    await state.clear() # Сбрасываем состояние после попытки надеть

    if success:
        logging.info(f"Item inv_id:{inventory_id} equipped successfully to slot '{target_slot}' by user {user_id}.")
        # Обновляем клавиатуру инвентаря
        inventory_items = await get_inventory_items(user_id)
        keyboard = get_inventory_keyboard(inventory_items)
        # TODO: Можно перегенерировать полный текст инвентаря
        new_text = f"{message_text}\n\n🎒 **Ваш инвентарь:**"
        try:
            await callback.message.edit_text(new_text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as e:
            logging.warning(f"Could not edit inventory message after slot equip success: {e}")
            await callback.message.answer(new_text, reply_markup=keyboard, parse_mode="HTML")
            try: await callback.message.delete()
            except Exception: pass
    else:
        # Если надеть не удалось
        logging.warning(f"Failed to equip item inv_id:{inventory_id} to slot '{target_slot}' for user {user_id}: {message_text}")
        await callback.answer(message_text, show_alert=True)
        # Возвращаем к инвентарю
        inventory_items = await get_inventory_items(user_id)
        keyboard = get_inventory_keyboard(inventory_items)
        new_text = "Не удалось надеть предмет. Ваш инвентарь:"
        try: await callback.message.edit_text(new_text, reply_markup=keyboard)
        except Exception as e:
            logging.warning(f"Could not edit message after slot equip failure: {e}")


# Обработчик нажатий кнопок слотов ВНЕ состояния
@router.callback_query(F.data.startswith("equip_slot:"))
async def handle_equip_slot_outside_state(callback: types.CallbackQuery):
    logging.warning(f"User {callback.from_user.id} pressed equip_slot button outside of state. Callback: {callback.data}")
    await callback.answer("Выбор слота больше не актуален.", show_alert=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        logging.warning(f"Could not edit old slot selection message markup: {e}")
