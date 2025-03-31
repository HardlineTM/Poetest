# handlers/stats.py
import logging
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.text_decorations import html_decoration as hd
from aiogram.exceptions import TelegramBadRequest # Для обработки ошибок API

# Импортируем нужные функции из базы данных
from database.db_manager import get_player, update_stat_points, increase_attribute, check_and_apply_regen

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - [%(filename)s:%(lineno)d] - %(message)s")

router = Router()

# Определяем состояния для процесса распределения очков
class StatAllocationStates(StatesGroup):
    choosing_attribute = State() # Состояние выбора атрибута для прокачки

# Словарь для красивого отображения имен атрибутов на кнопках и в сообщениях
ATTRIBUTE_NAMES = {
    'strength': '💪 Сила',
    'dexterity': '🏹 Ловкость',
    'intelligence': '🧠 Интеллект'
}

# --- Вспомогательная функция для вызова регенерации ---
# (Дублируется из common.py, можно вынести в utils)
async def trigger_regen_check(user_id: int, state: FSMContext):
     try:
        current_state_str = await state.get_state()
        await check_and_apply_regen(user_id, current_state_str)
     except Exception as e:
         logging.error(f"Error during regen check in stats handler for user {user_id}: {e}", exc_info=False)


# --- Клавиатура для распределения очков ---
def get_stat_allocation_keyboard(player_stats: types.User) -> InlineKeyboardMarkup: # player_stats - это sqlite3.Row
    """
    Генерирует клавиатуру для распределения очков характеристик.
    Показывает кнопки для увеличения каждого стата, если есть очки.
    """
    buttons = []
    logging.debug(f"[get_stat_keyboard] Input player_stats type: {type(player_stats)}")
    # --- Используем доступ по ключу [] ---
    try:
        available_points = player_stats['stat_points']
        if not isinstance(available_points, int):
            logging.warning(f"[get_stat_keyboard] 'stat_points' is not an integer: {available_points}. Defaulting to 0.")
            available_points = 0
    except KeyError:
        logging.error("[get_stat_keyboard] KeyError: 'stat_points' not found in player_stats. Defaulting to 0.")
        available_points = 0
    except Exception as e:
        logging.error(f"[get_stat_keyboard] Error accessing 'stat_points': {e}. Defaulting to 0.")
        available_points = 0

    logging.debug(f"[get_stat_keyboard] Calculated available_points: {available_points}")

    if available_points > 0:
        logging.debug("[get_stat_keyboard] Points > 0. Generating attribute buttons...")
        for attr_code, attr_name in ATTRIBUTE_NAMES.items():
            logging.debug(f"[get_stat_keyboard] Processing attribute: {attr_code}")
            try:
                # --- Используем доступ по ключу [] ---
                current_value = player_stats[attr_code]
                if not isinstance(current_value, (int, float)):
                     logging.warning(f"[get_stat_keyboard] '{attr_code}' is not a number: {current_value}. Defaulting to 0.")
                     current_value = 0
            except KeyError:
                logging.error(f"[get_stat_keyboard] KeyError: '{attr_code}' not found. Defaulting to 0.")
                current_value = 0
            except Exception as e:
                 logging.error(f"[get_stat_keyboard] Error accessing '{attr_code}': {e}. Defaulting to 0.")
                 current_value = 0

            logging.debug(f"[get_stat_keyboard] Current value for {attr_code}: {current_value}. Adding button.")
            buttons.append([
                InlineKeyboardButton(
                    text=f"{attr_name}: {current_value} (+1)",
                    callback_data=f"allocate:{attr_code}"
                )
            ])
    else:
        logging.debug("[get_stat_keyboard] No points available. Adding 'noop' button.")
        buttons.append([InlineKeyboardButton(text="Нет доступных очков", callback_data="allocate:noop")])

    logging.debug("[get_stat_keyboard] Adding 'Cancel' button.")
    buttons.append([InlineKeyboardButton(text="Завершить", callback_data="allocate:cancel")])

    logging.debug(f"[get_stat_keyboard] Final buttons list: {buttons}")
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    logging.debug(f"[get_stat_keyboard] Generated keyboard JSON: {keyboard.model_dump_json(exclude_none=True)}")
    return keyboard


# --- Обработчики ---

# Обработчик для кнопки "Прокачка" из главного меню
@router.message(F.text.lower() == "💪 прокачка")
async def stats_allocation_start(message: types.Message, state: FSMContext):
    """
    Начинает процесс распределения очков характеристик.
    Вызывается при нажатии кнопки 'Прокачка'.
    """
    user_id = message.from_user.id
    logging.info(f"User {user_id} initiated stat allocation via button.")
    # Проверяем реген перед показом
    await trigger_regen_check(user_id, state)
    player = await get_player(user_id) # Используем get_player, т.к. нужны базовые статы и очки

    if not player:
        logging.warning(f"Non-player {user_id} tried to access stat allocation.")
        await message.answer("Сначала создайте персонажа: /start")
        return

    # Логирование для проверки значения из БД
    try:
        retrieved_stat_points = player['stat_points']
        logging.info(f"User {user_id} - Checking stat points. Retrieved value from DB: {retrieved_stat_points} (Type: {type(retrieved_stat_points)})")
    except KeyError:
        retrieved_stat_points = 0
        logging.error(f"User {user_id} - 'stat_points' key not found in player data!")
    except Exception as e:
        retrieved_stat_points = 0
        logging.error(f"User {user_id} - Error retrieving stat_points: {e}")

    available_points = retrieved_stat_points if isinstance(retrieved_stat_points, int) else 0

    if available_points > 0:
        logging.info(f"User {user_id} has {available_points} points. Generating keyboard...")
        try:
            # Генерируем клавиатуру с опциями
            keyboard = get_stat_allocation_keyboard(player)
            logging.debug(f"Keyboard generated for user {user_id}: {keyboard.model_dump_json(exclude_none=True)}")

            await message.answer(
                f"У вас есть <b>{available_points}</b> свободных очков характеристик.\n"
                "Выберите, куда вложить очко:",
                reply_markup=keyboard, # Прикрепляем клавиатуру
                parse_mode="HTML"
            )
            await state.set_state(StatAllocationStates.choosing_attribute) # Устанавливаем состояние
            logging.info(f"Allocation menu sent to user {user_id}. State set to choosing_attribute.")
        except Exception as e:
            logging.error(f"Error generating or sending keyboard for user {user_id}: {e}", exc_info=True)
            await message.answer("Произошла ошибка при отображении меню прокачки.")

    else:
        logging.info(f"User {user_id} has no stat points (available_points calculated as {available_points}). Showing 'no points' message.")
        await message.answer(
            "У вас нет доступных очков характеристик для распределения.\n"
            "Вы получаете их при повышении уровня."
        )


# Обработчик нажатий кнопок в меню распределения очков
@router.callback_query(StatAllocationStates.choosing_attribute, F.data.startswith("allocate:"))
async def process_stat_allocation(callback: types.CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие кнопки с выбором атрибута или кнопки 'Завершить'.
    Работает только когда пользователь в состоянии choosing_attribute.
    """
    await callback.answer() # Убираем часики
    user_id = callback.from_user.id
    action_data = callback.data.split(":")
    action = action_data[1]

    logging.info(f"User {user_id} pressed allocation button: {action} in state {await state.get_state()}")

    # Обработка управляющих кнопок
    if action == "cancel":
        logging.info(f"User {user_id} finished stat allocation via 'Cancel' button.")
        try:
            # Редактируем сообщение, убираем клавиатуру
            await callback.message.edit_text("Распределение очков завершено.", reply_markup=None)
        except TelegramBadRequest as e: # Ошибка, если сообщение не изменилось
             if "message is not modified" in str(e): logging.debug("Message not modified on allocation cancel.")
             else: logging.warning(f"Could not edit message on allocation cancel: {e}")
        except Exception as e:
             logging.warning(f"Could not edit message on allocation cancel: {e}")
        await state.clear() # Сбрасываем состояние
        return

    if action == "noop":
        logging.debug(f"User {user_id} pressed 'noop' allocation button.")
        # Можно добавить show_alert=True, если нужно явно сказать, что очков нет
        # await callback.answer("У вас нет доступных очков.", show_alert=True)
        return

    # Обработка кнопки атрибута
    attribute_to_increase = action
    if attribute_to_increase not in ATTRIBUTE_NAMES:
         logging.error(f"Invalid attribute '{attribute_to_increase}' in allocation callback data: {callback.data} for user {user_id}")
         try:
             await callback.message.edit_text("Произошла ошибка выбора атрибута. Попробуйте снова.", reply_markup=None)
         except Exception as e: logging.warning(f"Could not edit message on invalid attribute error: {e}")
         await state.clear()
         return

    # Логика траты очка и увеличения стата
    player_before = await get_player(user_id) # Снова получаем базовые данные
    if not player_before:
        logging.error(f"Could not retrieve player data for {user_id} during stat allocation processing.")
        try: await callback.message.edit_text("Ошибка: Не удалось получить данные вашего персонажа.", reply_markup=None)
        except Exception as e: logging.warning(f"Could not edit message on player data retrieval error: {e}")
        await state.clear()
        return

    # Проверяем наличие очков перед тратой
    if player_before['stat_points'] <= 0:
        logging.warning(f"User {user_id} tried to allocate stats via callback but has 0 points (state: {await state.get_state()}).")
        try:
             await callback.message.edit_text("У вас закончились очки характеристик.", reply_markup=None)
        except Exception as e: logging.warning(f"Could not edit message after running out of points via callback: {e}")
        await state.clear()
        return

    # Уменьшаем очки И увеличиваем атрибут
    await update_stat_points(user_id, -1) # Тратим 1 очко
    increase_success = await increase_attribute(user_id, attribute_to_increase, 1)

    if not increase_success:
        logging.error(f"Failed to increase attribute {attribute_to_increase} for user {user_id} after attempting to spend point.")
        try:
            await callback.message.edit_text("Не удалось увеличить характеристику. Очко не потрачено (попытка отмены).", reply_markup=None)
        except Exception as e: logging.warning(f"Could not edit message on attribute increase failure: {e}")
        await update_stat_points(user_id, 1) # Пытаемся вернуть очко
        await state.clear()
        return

    # Успешное распределение очка
    player_after = await get_player(user_id) # Получаем обновленные базовые данные
    if not player_after:
         logging.error(f"Could not retrieve updated player data for {user_id} after successful stat allocation.")
         try:
             await callback.message.edit_text(f"Очко вложено в {ATTRIBUTE_NAMES[attribute_to_increase]}! (Ошибка получения новых данных)", reply_markup=None)
         except Exception as e: logging.warning(f"Could not edit message after failed data retrieval post-allocation: {e}")
         await state.clear()
         return

    available_points_after = player_after['stat_points']
    new_stat_value = player_after[attribute_to_increase]
    logging.info(f"User {user_id} successfully allocated 1 point to {attribute_to_increase}. New value: {new_stat_value}. Points left: {available_points_after}")

    feedback_text = f"Вы вложили очко в {ATTRIBUTE_NAMES[attribute_to_increase]}! (Новое значение: {new_stat_value})\n"

    if available_points_after > 0:
         feedback_text += f"У вас осталось <b>{available_points_after}</b> очков.\nВыберите следующее улучшение:"
         new_keyboard = get_stat_allocation_keyboard(player_after) # Генерируем новую клавиатуру
         try:
             await callback.message.edit_text(feedback_text, reply_markup=new_keyboard, parse_mode="HTML")
             logging.debug(f"Allocation message updated for user {user_id}. Points left: {available_points_after}")
         except TelegramBadRequest as e:
             if "message is not modified" in str(e): logging.debug(f"Message not modified for user {user_id}, points left {available_points_after}.")
             else: logging.error(f"Error editing message after stat allocation for {user_id}: {e}")
         except Exception as e:
              logging.error(f"Error editing message after stat allocation for {user_id}: {e}")
         # Остаемся в состоянии choosing_attribute
    else:
         feedback_text += "Все очки распределены."
         try:
             await callback.message.edit_text(feedback_text, reply_markup=None, parse_mode="HTML") # Убираем клавиатуру
             logging.info(f"User {user_id} spent all allocation points. Clearing state.")
         except TelegramBadRequest as e:
              if "message is not modified" in str(e): logging.debug("Message not modified on final allocation.")
              else: logging.error(f"Error editing final stat allocation message for user {user_id}: {e}")
         except Exception as e:
              logging.error(f"Error editing final stat allocation message for user {user_id}: {e}")
         await state.clear() # Сбрасываем состояние


# Обработчик для случая, если нажали кнопку прокачки вне состояния
@router.callback_query(F.data.startswith("allocate:"))
async def handle_allocate_action_outside_state(callback: types.CallbackQuery, state: FSMContext): # Добавили state для логгирования
    """Ловит нажатия на кнопки allocate:, если пользователь НЕ в состоянии choosing_attribute."""
    logging.warning(f"User {callback.from_user.id} pressed allocate button outside of state '{await state.get_state()}'. Callback: {callback.data}")
    await callback.answer("Это меню прокачки больше неактивно.", show_alert=True)
    try:
        # Просто убираем клавиатуру из старого сообщения
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        logging.warning(f"Could not edit old allocation message markup when handling outside state action: {e}")

# --- Конец файла handlers/stats.py ---
