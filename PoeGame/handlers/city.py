# handlers/city.py
import logging
import math
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.text_decorations import html_decoration as hd

# Импортируем необходимые функции из базы данных
from database.db_manager import get_player, update_player_vitals, update_player_xp, check_and_apply_regen

# Настройка логирования (если нужно для отладки)
# logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")

router = Router()

# Определяем состояния для взаимодействия с лекарем
class HealerStates(StatesGroup):
    choosing_heal_option = State() # Состояние, когда игрок видит опции лечения

# Константы для расчета стоимости лечения
HEAL_BASE_COST = 5 # Базовая стоимость за 25% лечения на 1 уровне
HEAL_LEVEL_MULTIPLIER = 0.1 # Стоимость увеличивается на 10% за каждый уровень выше первого

# --- Вспомогательная функция для создания клавиатуры Лекаря ---
def get_healer_options_keyboard(player_level: int, current_hp: int, max_hp: int, current_mana: int, max_mana: int, player_gold: int) -> InlineKeyboardMarkup:
    """
    Генерирует инлайн-клавиатуру с опциями лечения у Лекаря.
    Кнопки показывают процент восстановления, стоимость и доступны ли они.
    """
    buttons = []
    # Словарь опций: тип ресурса -> список процентов
    options = {
        'hp': [25, 50, 100],
        'mana': [25, 50, 100]
    }

    for resource_type, percentages in options.items():
        for percent in percentages:
            # Рассчитываем стоимость для данной опции
            # Формула: база * (процент/25) * (1 + (уровень - 1) * множитель)
            cost_multiplier = 1 + (player_level - 1) * HEAL_LEVEL_MULTIPLIER
            # Округляем стоимость вверх до целого числа
            cost = math.ceil(HEAL_BASE_COST * (percent / 25) * cost_multiplier)

            # Определяем текст кнопки и её callback_data
            label_prefix = "❤️ HP" if resource_type == 'hp' else "💧 Mana"
            # Проверяем, полный ли ресурс у игрока
            is_full = (resource_type == 'hp' and current_hp >= max_hp) or \
                      (resource_type == 'mana' and current_mana >= max_mana)
            # Проверяем, хватает ли золота
            can_afford = player_gold >= cost

            if is_full:
                # Если ресурс полный, кнопка неактивна и показывает галочку
                button_text = f"✅ {label_prefix} (Полное)"
                callback_data = "heal:noop" # noop - нет операции
            elif can_afford:
                # Если можно купить, показываем стоимость и активную кнопку
                button_text = f"{label_prefix} +{percent}% ({cost}💰)"
                callback_data = f"heal:{resource_type}:{percent}:{cost}"
            else:
                # Если не хватает золота, показываем крестик и стоимость
                button_text = f"❌ {label_prefix} +{percent}% ({cost}💰)"
                callback_data = f"heal:no_gold:{cost}" # Отдельный callback для обработки нехватки золота

            # Добавляем кнопку в список
            buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])

    # Добавляем кнопку для выхода из меню лекаря
    buttons.append([InlineKeyboardButton(text="Выйти", callback_data="heal:cancel")])

    # Создаем и возвращаем объект клавиатуры
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- Обработчик Сообщения для кнопки "Лекарь" ---
@router.message(F.text.lower() == "⚕️ лекарь")
async def healer_start(message: types.Message, state: FSMContext):
    """
    Обрабатывает нажатие кнопки "Лекарь" в меню города.
    Показывает приветствие лекаря и кнопки с опциями лечения.
    """
    user_id = message.from_user.id
    logging.info(f"User {user_id} accessed the healer.")

    # Проверяем и применяем регенерацию перед отображением опций
    current_state_str = await state.get_state()
    await check_and_apply_regen(user_id, current_state_str)

    # Получаем обновленные данные игрока ПОСЛЕ регенерации
    player = await get_player(user_id)

    if not player:
        logging.warning(f"Non-player {user_id} tried to access the healer.")
        await message.answer("Сначала создайте персонажа: /start")
        return

    # Генерируем клавиатуру на основе текущих данных игрока
    keyboard = get_healer_options_keyboard(
        player['level'], player['current_hp'], player['max_hp'],
        player['current_mana'], player['max_mana'], player['gold']
    )

    # Отправляем сообщение с клавиатурой
    await message.answer(
        "Приветствую, изгнанник! Хочешь подлечиться или восстановить силы?\n"
        f"<i>(Ваше золото: {player['gold']}💰)</i>\n" # Показываем текущее золото
        "Выбери услугу:",
        reply_markup=keyboard,
        parse_mode="HTML" # Используем HTML для курсива
    )
    # Устанавливаем состояние, что игрок выбирает опцию у лекаря
    await state.set_state(HealerStates.choosing_heal_option)


# --- Обработчик Callback'ов от кнопок Лекаря ---
@router.callback_query(HealerStates.choosing_heal_option, F.data.startswith("heal:"))
async def process_healer_option(callback: types.CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатия на инлайн-кнопки в меню лекаря.
    Работает только если пользователь находится в состоянии choosing_heal_option.
    """
    # Отвечаем на callback, чтобы убрать "часики"
    await callback.answer()
    user_id = callback.from_user.id
    # Разбираем callback_data, например: "heal:hp:50:20" или "heal:cancel"
    action_data = callback.data.split(":")
    action = action_data[1] # Тип действия: hp, mana, cancel, noop, no_gold

    logging.debug(f"User {user_id} healer action: {action}, data: {callback.data}")

    # Обрабатываем управляющие действия
    if action == "cancel":
        logging.info(f"User {user_id} cancelled healing.")
        await callback.message.edit_text("Береги себя, изгнанник!")
        await state.clear() # Выходим из состояния лекаря
        return
    if action == "noop":
        # Нажата кнопка для полного ресурса, ничего не делаем
        logging.debug(f"User {user_id} clicked noop heal button.")
        return
    if action == "no_gold":
        # Нажата кнопка, на которую не хватает золота
        try:
            needed_gold = int(action_data[2])
            # Отвечаем всплывающим уведомлением (alert)
            await callback.answer(f"Недостаточно золота! Требуется {needed_gold}💰.", show_alert=True)
        except (IndexError, ValueError):
            # Если стоимость не передалась, показываем общее сообщение
            await callback.answer("Недостаточно золота!", show_alert=True)
        logging.debug(f"User {user_id} clicked unaffordable heal button ({callback.data}).")
        # Не меняем сообщение и не сбрасываем состояние, чтобы дать выбрать другую опцию
        return

    # --- Обработка покупки лечения ---
    # Ожидаемый формат: "heal:type:percent:cost"
    if len(action_data) != 4:
         logging.error(f"Invalid healer callback data format: {callback.data} for user {user_id}")
         await callback.message.edit_text("Произошла ошибка обработки данных. Попробуйте снова.")
         await state.clear()
         return

    resource_type = action_data[1] # 'hp' или 'mana'
    try:
        # Извлекаем процент и ожидаемую стоимость из callback'а
        percent_to_heal = int(action_data[2])
        expected_cost = int(action_data[3])
    except ValueError:
        logging.error(f"Invalid numeric values in healer callback data: {callback.data} for user {user_id}")
        await callback.message.edit_text("Произошла ошибка числовых данных. Попробуйте снова.")
        await state.clear()
        return

    # Получаем актуальные данные игрока для проверки и расчета
    player = await get_player(user_id)
    if not player:
        logging.error(f"Could not retrieve player data for {user_id} during healing purchase.")
        await callback.message.edit_text("Не удалось найти данные вашего персонажа.")
        await state.clear()
        return

    # --- Проверка безопасности: пересчитываем стоимость на сервере ---
    cost_multiplier = 1 + (player['level'] - 1) * HEAL_LEVEL_MULTIPLIER
    actual_cost = math.ceil(HEAL_BASE_COST * (percent_to_heal / 25) * cost_multiplier)

    # Сравниваем стоимость с кнопки и рассчитанную на сервере
    if actual_cost != expected_cost:
         logging.warning(f"Healer cost mismatch for user {user_id}. Button cost: {expected_cost}, Server cost: {actual_cost}. Callback: {callback.data}")
         # Генерируем новую клавиатуру с актуальными ценами
         new_keyboard = get_healer_options_keyboard(
             player['level'], player['current_hp'], player['max_hp'],
             player['current_mana'], player['max_mana'], player['gold']
         )
         # Просим пользователя выбрать снова
         await callback.message.edit_text(
             "Цены на лечение могли измениться. Пожалуйста, выберите снова:",
             reply_markup=new_keyboard
         )
         # Не сбрасываем состояние, даем выбрать еще раз
         return

    # Проверяем, хватает ли золота (хотя кнопка no_gold должна была это отсечь)
    if player['gold'] < actual_cost:
        logging.warning(f"User {user_id} attempted to buy healing without enough gold. Needed: {actual_cost}, Has: {player['gold']}")
        await callback.message.edit_text(f"У вас недостаточно золота! Нужно {actual_cost}💰, а у вас {player['gold']}💰.")
        await state.clear() # Сбрасываем состояние, так как транзакция не удалась
        return

    # --- Проведение лечения ---
    amount_to_restore_calc = 0 # Сколько единиц пытаемся восстановить
    target_value = 0           # До какого значения восстановится ресурс
    current_value = 0          # Текущее значение ресурса до лечения
    resource_name = ""         # Название ресурса для сообщения

    if resource_type == 'hp':
        resource_name = "здоровье"
        current_value = player['current_hp']
        # Проверяем, нужно ли вообще лечить HP
        if current_value >= player['max_hp']:
             logging.debug(f"User {user_id} tried to heal full HP.")
             await callback.answer("Ваше здоровье уже полное!", show_alert=True)
             return # Остаемся в меню лекаря

        # Рассчитываем количество HP к восстановлению от МАКСИМАЛЬНОГО HP
        amount_to_restore_calc = math.ceil(player['max_hp'] * (percent_to_heal / 100.0))
        # Целевое значение - текущее + восстановление, но не больше максимума
        target_value = min(player['max_hp'], current_value + amount_to_restore_calc)
        # Применяем изменение через set_hp для точности
        await update_player_vitals(user_id, set_hp=target_value)

    elif resource_type == 'mana':
        resource_name = "ману"
        current_value = player['current_mana']
        # Проверяем, нужно ли восстанавливать ману
        if current_value >= player['max_mana']:
            logging.debug(f"User {user_id} tried to heal full Mana.")
            await callback.answer("Ваша мана уже полная!", show_alert=True)
            return # Остаемся в меню лекаря

        # Рассчитываем количество маны к восстановлению от МАКСИМАЛЬНОЙ маны
        amount_to_restore_calc = math.ceil(player['max_mana'] * (percent_to_heal / 100.0))
        # Целевое значение - текущее + восстановление, но не больше максимума
        target_value = min(player['max_mana'], current_value + amount_to_restore_calc)
        # Применяем изменение через set_mana
        await update_player_vitals(user_id, set_mana=target_value)
    else:
        # Если тип ресурса некорректен
        logging.error(f"Invalid resource type '{resource_type}' in healer logic for user {user_id}")
        await callback.message.edit_text("Произошла ошибка типа ресурса.")
        await state.clear()
        return

    # --- Списание золота ---
    # Используем функцию update_player_xp с отрицательным золотом
    _, _ = await update_player_xp(user_id, gained_gold=-actual_cost)

    # Сколько единиц ресурса было реально восстановлено
    actual_healed_amount = target_value - current_value

    logging.info(f"User {user_id} healed {resource_name} by {actual_healed_amount} for {actual_cost} gold. New value: {target_value}")

    # Отправляем сообщение об успехе и редактируем исходное сообщение лекаря
    await callback.message.edit_text(
        f"Вы успешно восстановили {resource_name} на <b>{actual_healed_amount}</b> ед. за {actual_cost}💰!\n"
        f"<i>(Теперь у вас {target_value} {resource_name})</i>",
        parse_mode="HTML"
    )
    # Сбрасываем состояние, так как взаимодействие с лекарем завершено
    await state.clear()


# --- Обработчик нажатий на кнопки Лекаря ВНЕ состояния ---
@router.callback_query(F.data.startswith("heal:"))
async def handle_healer_action_outside_state(callback: types.CallbackQuery):
    """
    Перехватывает нажатия на кнопки лекаря, если пользователь уже не находится
    в состоянии HealerStates.choosing_heal_option.
    """
    logging.warning(f"User {callback.from_user.id} pressed healer button outside of state. Callback: {callback.data}")
    # Сообщаем пользователю, что меню неактивно
    await callback.answer("Это меню лекаря больше неактивно.", show_alert=True)
    # Пытаемся убрать инлайн-клавиатуру из старого сообщения
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        # Ошибки редактирования старых сообщений ожидаемы, просто логируем
        logging.warning(f"Could not edit old healer message markup for user {callback.from_user.id}: {e}")
