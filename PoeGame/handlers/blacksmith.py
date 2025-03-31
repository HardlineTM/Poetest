# handlers/blacksmith.py
import logging
import time
import random
import math # Добавим math на всякий случай
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.text_decorations import html_decoration as hd
from aiogram.exceptions import TelegramBadRequest # Для обработки ошибок API

# Импортируем все необходимое из БД
from database.db_manager import (
    get_blacksmith_items, update_blacksmith_items,
    get_player_effective_stats, check_and_apply_regen,
    # count_player_fragments, # Эта функция больше не нужна, считаем по инвентарю
    get_inventory_items, # Нужна для подсчета фрагментов
    remove_player_fragments, add_item_to_inventory,
    update_player_xp # Нужен для возврата фрагментов (хотя это сложно)
)
# Импортируем данные игры
from game_data import (
    ALL_ITEMS, BLACKSMITH_ITEMS_COUNT, BLACKSMITH_REFRESH_INTERVAL,
    BLACKSMITH_CRAFT_COST, ITEM_TYPE_FRAGMENT
)
# Импортируем форматирование статов и эмодзи
try:
    from handlers.inventory import format_item_stats
    from handlers.shop import ITEM_TYPE_EMOJI # Используем тот же словарь эмодзи
except ImportError:
    # Заглушки на случай проблем с импортом
    def format_item_stats(stats: dict) -> str: return "Ошибка: format_item_stats не найдена"
    ITEM_TYPE_EMOJI = {"default": '❓'}
    logging.error("Could not import format_item_stats or ITEM_TYPE_EMOJI")


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - [%(filename)s:%(lineno)d] - %(message)s")
router = Router()

# --- Вспомогательные функции ---
async def refresh_blacksmith_if_needed() -> list[str]:
    """Проверяет и обновляет ассортимент кузнеца."""
    current_time = int(time.time())
    current_legendary_ids, last_refresh = await get_blacksmith_items()

    if current_time - last_refresh >= BLACKSMITH_REFRESH_INTERVAL or not current_legendary_ids:
        logging.info("Refreshing blacksmith items...")
        # Выбираем случайные легендарки (только надеваемые)
        possible_legendaries = [
            id for id, data in ALL_ITEMS.items()
            if data.get('rarity') == 'legendary' and data.get('equipable')
        ]
        if not possible_legendaries:
             logging.error("No equipable legendary items found for blacksmith.")
             await update_blacksmith_items([]) # Очищаем ассортимент, если лег нет
             return []

        new_legendary_ids = random.sample(
            possible_legendaries,
            min(len(possible_legendaries), BLACKSMITH_ITEMS_COUNT)
        )
        await update_blacksmith_items(new_legendary_ids)
        logging.info(f"Blacksmith items refreshed: {new_legendary_ids}")
        return new_legendary_ids
    else:
        return current_legendary_ids

# --- ИСПРАВЛЕНИЕ: Клавиатура с ДВУМЯ кнопками (Инфо и Создать/Не хватает) ---
def get_blacksmith_keyboard(legendary_ids: list[str], player_fragments_count: dict[str, int]) -> InlineKeyboardMarkup:
    """Создает клавиатуру для кузнеца с кнопками Инфо и Создать/Не хватает."""
    buttons = []
    required_fragments_count = BLACKSMITH_CRAFT_COST # Сколько нужно любых фрагментов

    if not legendary_ids:
        buttons.append([InlineKeyboardButton(text="У меня пока ничего нет...", callback_data="smith:noop")])
    else:
        # Считаем общее количество ВСЕХ фрагментов у игрока
        total_player_fragments = sum(player_fragments_count.values())
        logging.debug(f"Total fragments for keyboard: {total_player_fragments}, Required: {required_fragments_count}")

        for leg_id in legendary_ids:
            leg_data = ALL_ITEMS.get(leg_id)
            if leg_data:
                can_craft = total_player_fragments >= required_fragments_count
                cost_str = f"({required_fragments_count} Любых Фрагм.)"
                type_emoji = ITEM_TYPE_EMOJI.get(leg_data.get('type'), ITEM_TYPE_EMOJI['default'])
                item_name_short = hd.quote(leg_data['name'])

                # Кнопка Инфо (всегда есть)
                info_button = InlineKeyboardButton(
                    text=f"ℹ️ {type_emoji}✨ {item_name_short} {cost_str}", # Добавил ✨ для легендарок
                    callback_data=f"smith:info:{leg_id}"
                )

                # Кнопка Создать (если хватает фрагментов)
                if can_craft:
                    action_button = InlineKeyboardButton(
                        text="Создать ✅",
                        callback_data=f"smith:craft:{leg_id}"
                    )
                    # Добавляем обе кнопки в ряд
                    buttons.append([info_button, action_button])
                else:
                    # Если не хватает фрагментов, только кнопка Инфо
                    buttons.append([info_button])

    buttons.append([InlineKeyboardButton(text="Обновить (завтра)", callback_data="smith:refresh_info")])
    buttons.append([InlineKeyboardButton(text="Уйти", callback_data="smith:close")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
# --- КОНЕЦ ИСПРАВЛЕНИЯ КЛАВИАТУРЫ ---


# --- ИСПРАВЛЕНИЕ: Функция для генерации текста кузнеца со статами ---
def format_blacksmith_message_text(legendary_ids: list[str], player_fragments_count: dict[str, int]) -> str:
    """Генерирует основной текст сообщения для кузнеца, включая статы."""
    fragments_text = "\n".join([f"  - {ALL_ITEMS.get(fid, {}).get('name', fid)}: {count} шт."
                               for fid, count in player_fragments_count.items()])
    if not fragments_text: fragments_text = "  <i>У вас нет фрагментов.</i>"

    blacksmith_text = (
        f"🔨 Приветствую у наковальни, изгнанник!\n"
        f"Я могу создать для тебя нечто особенное, если принесешь нужные фрагменты.\n\n"
        f"<b>Предложения на сегодня:</b>\n(Требуется: {BLACKSMITH_CRAFT_COST} любых фрагментов)\n"
    )

    if not legendary_ids:
        blacksmith_text += "\n<i>Пока нет чертежей... Загляни завтра.</i>"
    else:
        legendary_ids.sort(key=lambda x: ALL_ITEMS.get(x, {}).get('name', '')) # Сортируем по имени
        for leg_id in legendary_ids:
            leg_data = ALL_ITEMS.get(leg_id)
            if leg_data:
                stats_str = format_item_stats(leg_data.get('stats', {}))
                type_emoji = ITEM_TYPE_EMOJI.get(leg_data.get('type'), ITEM_TYPE_EMOJI['default'])
                blacksmith_text += f"\n{type_emoji}✨ <b>{hd.quote(leg_data['name'])}</b>\n<pre>{stats_str}</pre>\n"

    blacksmith_text += f"\n<b>Ваши фрагменты:</b>\n{fragments_text}\n\n"
    blacksmith_text += "<i>Нажмите ℹ️ для подробной информации или ✅ для создания.</i>"
    return blacksmith_text
# --- КОНЕЦ ФУНКЦИИ ГЕНЕРАЦИИ ТЕКСТА ---

# --- Обработчик входа к кузнецу ---
@router.message(F.text.lower() == "🔨 кузнец")
async def blacksmith_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    logging.info(f"User {user_id} visited the blacksmith.")
    try: await check_and_apply_regen(user_id, await state.get_state())
    except Exception as e: logging.error(f"Regen check error in blacksmith: {e}")

    player = await get_player_effective_stats(user_id)
    if not player:
        await message.answer("Сначала создайте персонажа: /start")
        return

    legendary_ids = await refresh_blacksmith_if_needed()

    # Получаем и считаем фрагменты
    inventory_items = await get_inventory_items(user_id)
    player_fragments_count = {}
    for item in inventory_items:
        item_type = item.get('type')
        if item_type == ITEM_TYPE_FRAGMENT:
             item_id = item.get('item_id')
             if item_id: # Убедимся, что ID есть
                 player_fragments_count[item_id] = player_fragments_count.get(item_id, 0) + 1

    # Используем новые функции для клавиатуры и текста
    keyboard = get_blacksmith_keyboard(legendary_ids, player_fragments_count)
    blacksmith_text = format_blacksmith_message_text(legendary_ids, player_fragments_count)

    try:
        await message.answer(blacksmith_text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest as e:
         if "message is too long" in str(e):
              logging.warning(f"Blacksmith message too long for user {user_id}. Sending short version.")
              fragments_total = sum(player_fragments_count.values())
              await message.answer(f"🔨 Кузнец.\nУ вас {fragments_total} фрагментов.\n\n<i>Ассортимент слишком велик для отображения здесь. Используйте кнопки ниже.</i>", reply_markup=keyboard)
         else:
              logging.error(f"Error sending blacksmith message for user {user_id}: {e}")
              await message.answer("Ошибка отображения кузницы.", reply_markup=keyboard)


# --- Обработчик нажатий кнопок кузнеца ---
@router.callback_query(F.data.startswith("smith:"))
async def handle_blacksmith_action(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data_parts = callback.data.split(":") # smith:action:item_id

    if len(data_parts) < 2: # Минимум smith:action
         logging.error(f"Invalid blacksmith callback data (too few parts): {callback.data}")
         await callback.answer("Ошибка данных.", show_alert=True)
         return

    action = data_parts[1]
    logging.info(f"Blacksmith action '{action}' initiated by user {user_id}. CB: {callback.data}")

    if action == "close":
        await callback.answer("Возвращайся, когда будешь готов.")
        try: await callback.message.delete()
        except Exception: pass
        return
    if action == "noop":
        await callback.answer("Загляни завтра, может, что появится.")
        return
    if action == "refresh_info":
        _, last_refresh = await get_blacksmith_items()
        time_left = BLACKSMITH_REFRESH_INTERVAL - (int(time.time()) - last_refresh)
        if time_left > 0:
             hours, rem = divmod(time_left, 3600)
             mins, _ = divmod(rem, 60)
             time_left_str = f"~{int(hours)}ч {int(mins)}м" if hours > 0 else f"~{int(mins)}м"
             await callback.answer(f"Новые чертежи появятся через {time_left_str}.", show_alert=True)
        else:
             await callback.answer("Новые чертежи должны скоро появиться!", show_alert=True)
        return
    if action == "back": # Кнопка Назад из инфо
        # Перегенерируем основное меню кузнеца
        player = await get_player_effective_stats(user_id) # Нужен для проверки? Нет.
        legendary_ids_after, _ = await get_blacksmith_items()
        inventory_items_after = await get_inventory_items(user_id)
        player_fragments_count_after = {}
        for item in inventory_items_after:
            if item.get('type') == ITEM_TYPE_FRAGMENT:
                 item_id_frag = item.get('item_id')
                 if item_id_frag:
                     player_fragments_count_after[item_id_frag] = player_fragments_count_after.get(item_id_frag, 0) + 1

        new_keyboard = get_blacksmith_keyboard(legendary_ids_after, player_fragments_count_after)
        new_text = format_blacksmith_message_text(legendary_ids_after, player_fragments_count_after)
        try:
            await callback.message.edit_text(new_text, reply_markup=new_keyboard, parse_mode="HTML")
            await callback.answer()
        except Exception as e:
             logging.error(f"Error going back to blacksmith for user {user_id}: {e}")
             await callback.answer("Ошибка возврата к кузнецу.", show_alert=True)
        return

    # Для 'craft' и 'info' нужен item_id
    try:
        if len(data_parts) < 3: raise ValueError("Missing item_id")
        item_id = data_parts[2]
        item_data = ALL_ITEMS.get(item_id)
        # Проверяем, что это легендарка (или будущий крафтовый предмет)
        if not item_data or not item_data.get('equipable') or item_data.get('rarity') != 'legendary':
            raise ValueError("Invalid or non-legendary item ID for blacksmith")
    except (IndexError, ValueError) as e:
        logging.error(f"Invalid blacksmith callback data (item_id): {callback.data} - {e}")
        await callback.answer("Ошибка данных предмета.", show_alert=True)
        return

    # --- Показ информации о легендарке (action == "info") ---
    if action == "info":
        if not item_data: return
        stats_str = format_item_stats(item_data.get('stats', {}))
        description = item_data.get('description', '')
        cost_str = f"Стоимость: {BLACKSMITH_CRAFT_COST} любых фрагментов"
        type_emoji = ITEM_TYPE_EMOJI.get(item_data.get('type'), ITEM_TYPE_EMOJI['default'])

        info_text = (
            f"{type_emoji}✨ <b>{hd.quote(item_data['name'])}</b> (Легендарный)\n\n"
            f"<b>Характеристики:</b>\n<pre>{stats_str}</pre>\n\n"
            f"<b>Описание:</b>\n<i>{description if description else '-'}</i>\n\n"
            f"{cost_str}"
        )
        # --- ИСПРАВЛЕНИЕ: Используем edit_text и кнопку Назад ---
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к кузнецу", callback_data="smith:back")] # Используем smith:back
        ])
        try:
            await callback.message.edit_text(info_text, reply_markup=back_keyboard, parse_mode="HTML")
            await callback.answer()
        except TelegramBadRequest as e:
             if "message is not modified" in str(e): await callback.answer()
             else:
                 logging.error(f"Error editing message for blacksmith item info {item_id}: {e}")
                 await callback.answer("Не удалось показать информацию.", show_alert=True)
        except Exception as e:
             logging.error(f"Unexpected error editing message for blacksmith item info {item_id}: {e}")
             await callback.answer("Ошибка.", show_alert=True)
        return
        # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

    # --- Крафт предмета (action == "craft") ---
    if action == "craft":
        if not item_data: return
        await callback.answer("Пытаемся создать предмет...")
        # Пересчитываем фрагменты на момент крафта
        inventory_items = await get_inventory_items(user_id)
        player_fragments = [item for item in inventory_items if item.get('type') == ITEM_TYPE_FRAGMENT]
        total_fragments = len(player_fragments)

        if total_fragments < BLACKSMITH_CRAFT_COST:
             logging.warning(f"User {user_id} attempted craft with insufficient fragments ({total_fragments}/{BLACKSMITH_CRAFT_COST})")
             await callback.answer(f"Недостаточно фрагментов! Нужно {BLACKSMITH_CRAFT_COST}, у вас {total_fragments}.", show_alert=True)
             return

        # --- Удаляем нужное количество фрагментов ---
        # Берем первые N фрагментов из списка
        fragments_to_remove_inv_ids = [item['inventory_id'] for item in player_fragments[:BLACKSMITH_CRAFT_COST]]
        fragments_removed_count = 0
        logging.info(f"Attempting to remove fragments: {fragments_to_remove_inv_ids} for user {user_id}")
        async with aiosqlite.connect(DB_NAME) as db:
             # Используем транзакцию для удаления и добавления
             try:
                 async with db.execute("BEGIN"):
                     # Удаляем фрагменты
                     placeholders = ', '.join('?' * len(fragments_to_remove_inv_ids))
                     cursor = await db.execute(f"DELETE FROM inventory WHERE inventory_id IN ({placeholders})", fragments_to_remove_inv_ids)
                     fragments_removed_count = cursor.rowcount

                     if fragments_removed_count != BLACKSMITH_CRAFT_COST:
                          raise ValueError(f"Removed {fragments_removed_count} fragments instead of {BLACKSMITH_CRAFT_COST}")

                     # Добавляем легендарку
                     await db.execute(
                         "INSERT INTO inventory (player_id, item_id) VALUES (?, ?)",
                         (user_id, item_id)
                     )
                 # Если все успешно, коммитим транзакцию
                 logging.info(f"Removed {fragments_removed_count} fragments and added legendary '{item_id}' for user {user_id}.")
                 craft_success = True
             except Exception as e:
                 # Откатываем транзакцию при любой ошибке
                 # await db.execute("ROLLBACK") # aiosqlite делает это автоматически при выходе из 'async with' с ошибкой
                 logging.error(f"Craft transaction failed for user {user_id}, item {item_id}: {e}", exc_info=True)
                 await callback.answer("Ошибка во время создания предмета!", show_alert=True)
                 craft_success = False
                 return # Прерываем

        # --- Обновляем сообщение кузнеца после крафта ---
        if craft_success:
            player_after = await get_player_effective_stats(user_id)
            legendary_ids_after, _ = await get_blacksmith_items()
            inventory_items_after = await get_inventory_items(user_id)
            player_fragments_count_after = {}
            for item in inventory_items_after:
                if item.get('type') == ITEM_TYPE_FRAGMENT:
                     item_id_frag = item.get('item_id')
                     if item_id_frag:
                         player_fragments_count_after[item_id_frag] = player_fragments_count_after.get(item_id_frag, 0) + 1

            new_keyboard = get_blacksmith_keyboard(legendary_ids_after, player_fragments_count_after)
            craft_message = f"✨ Вы успешно создали: <b>{hd.quote(item_data['name'])}</b>!"
            new_blacksmith_text = format_blacksmith_message_text(legendary_ids_after, player_fragments_count_after)
            final_text = f"{craft_message}\n\n{new_blacksmith_text}"

            try:
                await callback.message.edit_text(final_text, reply_markup=new_keyboard, parse_mode="HTML")
            except TelegramBadRequest as e:
                if "message is not modified" in str(e): logging.debug("Blacksmith message not modified after craft.")
                else: logging.warning(f"Could not edit blacksmith message after craft: {e}")
                # Отправляем сообщение об успехе отдельно, если редактирование не удалось
                await callback.message.answer(craft_message, parse_mode="HTML")
            except Exception as e:
                 logging.warning(f"Could not edit blacksmith message after craft: {e}")
                 await callback.message.answer(craft_message, parse_mode="HTML")


# Обработчик нажатий кнопок кузнеца ВНЕ состояния (здесь нет состояний FSM)
# @router.callback_query(F.data.startswith("smith:"))
# async def handle_blacksmith_action_outside_state(callback: types.CallbackQuery):
#     # Эта логика больше не нужна, так как кузнец не использует FSM
#     pass
