# handlers/common.py
import logging
import time
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton # Нужные типы для клавиатуры
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext # Нужен для получения состояния во всех хендлерах

# Импортируем данные и функции БД
from game_data import BASE_STATS
from database.db_manager import add_player, get_player, check_and_apply_regen

# Настройка логирования (можно удалить, если настроено глобально в bot.py)
# logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")

router = Router()

# --- Вспомогательная функция для вызова регенерации ---
# Вынесена для удобства повторного использования
async def trigger_regen_check(user_id: int, state: FSMContext):
     """Проверяет и применяет регенерацию, если игрок не в бою."""
     try:
        current_state_str = await state.get_state()
        await check_and_apply_regen(user_id, current_state_str)
     except Exception as e:
         # Логируем ошибку, но не прерываем основной процесс
         logging.error(f"Error during regen check for user {user_id}: {e}", exc_info=False) # exc_info=False, чтобы не засорять лог трейсбеком регена


# --- Клавиатуры Меню ---
def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Создает и возвращает клавиатуру главного меню."""
    buttons = [
        # Первый ряд
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🎒 Инвентарь")], # Добавлена кнопка Инвентарь
        # Второй ряд
        [KeyboardButton(text="🗺️ Задания"), KeyboardButton(text="💪 Прокачка")],
        # Третий ряд
        [KeyboardButton(text="⚔️ Бой"), KeyboardButton(text="🏘️ Город")],
        # Четвертый ряд
        [KeyboardButton(text="🎁 Ежедневная награда"), KeyboardButton(text="🏆 Рейтинг")],
    ]
    # resize_keyboard=True - подгоняет размер кнопок
    # one_time_keyboard=False - клавиатура не будет скрываться после нажатия
    keyboard = ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        one_time_keyboard=False # Делаем клавиатуру постоянной
    )
    return keyboard

def get_fight_menu_keyboard() -> ReplyKeyboardMarkup:
    """Создает и возвращает клавиатуру подменю 'Бой'."""
    buttons = [
        [KeyboardButton(text="⚔️ Бой с монстром"), KeyboardButton(text="💀 Бой с боссом")],
        [KeyboardButton(text="🤺 Бой с игроком (скоро)")],
        # Кнопка для возврата в главное меню
        [KeyboardButton(text="⬅️ Назад в меню")]
    ]
    keyboard = ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard

def get_city_menu_keyboard() -> ReplyKeyboardMarkup:
    """Создает и возвращает клавиатуру подменю 'Город'."""
    buttons = [
        # Убираем (скоро)
        [KeyboardButton(text="🛒 Магазин оружия"), KeyboardButton(text="🛡️ Магазин брони")],
        [KeyboardButton(text="⚕️ Лекарь"), KeyboardButton(text="🎲 Гемблер")],
        [KeyboardButton(text="🔨 Кузнец")],
        [KeyboardButton(text="🔮 Школа Магов")],
        [KeyboardButton(text="⬅️ Назад в меню")]
    ]
    keyboard = ReplyKeyboardMarkup(
        keyboard=buttons, resize_keyboard=True, one_time_keyboard=False
    )
    return keyboard


# --- Обработчики Команд и Кнопок ---

@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext): # Добавляем state
    """
    Обрабатывает команду /start.
    Регистрирует нового игрока (если его нет) и показывает главное меню.
    Вызывает проверку регенерации.
    """
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    logging.info(f"User {user_id} ({username}) initiated /start.")

    # Проверяем реген ДО получения данных игрока
    await trigger_regen_check(user_id, state)
    player = await get_player(user_id) # Получаем базовые данные

    if player:
        logging.info(f"Existing player {user_id} found. Sending main menu.")
        await message.answer(
            f"С возвращением в Рэкласт, {username}! 👋",
            reply_markup=get_main_menu_keyboard() # Показываем клавиатуру
        )
    else:
        logging.info(f"New player {user_id}. Proceeding with character creation.")
        # Используем класс по умолчанию 'Scion'
        chosen_class = 'Scion'
        # Берем отображаемое имя из BASE_STATS
        class_display_name = BASE_STATS.get(chosen_class, {}).get('name', chosen_class)

        success = await add_player(user_id, username, chosen_class)
        if success:
            logging.info(f"Character created successfully for {user_id} as {chosen_class}.")
            await message.answer(
                f"Добро пожаловать в Рэкласт, Изгнанник {username}! ✨\n"
                f"Ты начинаешь свой путь как {class_display_name}.\n"
                f"Используй кнопки ниже для навигации по миру игры.",
                reply_markup=get_main_menu_keyboard() # Показываем клавиатуру
            )
        else:
            logging.error(f"Failed to create character for {user_id} (DB error or already exists).")
            await message.answer(
                "Произошла ошибка при создании вашего персонажа. 😥\n"
                "Если вы уже начинали игру, просто пользуйтесь кнопками. Если нет, попробуйте /start позже."
            )

# Обработчик для кнопки "Назад в меню"
@router.message(F.text.lower() == "⬅️ назад в меню")
async def handle_back_to_main_menu(message: Message, state: FSMContext): # Добавляем state
    """Обрабатывает нажатие кнопки 'Назад в меню', возвращая основную клавиатуру."""
    logging.debug(f"User {message.from_user.id} pressed 'Back to menu'.")
    await trigger_regen_check(message.from_user.id, state) # Проверяем реген при возврате
    await message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())

# Обработчики для кнопок, открывающих подменю
@router.message(F.text.lower() == "⚔️ бой")
async def handle_fight_menu(message: Message, state: FSMContext): # Добавляем state
    """Обрабатывает нажатие кнопки 'Бой', показывая подменю боя."""
    logging.debug(f"User {message.from_user.id} pressed 'Fight' button.")
    await trigger_regen_check(message.from_user.id, state) # Реген перед входом в меню боя
    await message.answer("Выберите тип боя:", reply_markup=get_fight_menu_keyboard())

@router.message(F.text.lower() == "🏘️ город")
async def handle_city_menu(message: Message, state: FSMContext): # Добавляем state
    """Обрабатывает нажатие кнопки 'Город', показывая подменю города."""
    logging.debug(f"User {message.from_user.id} pressed 'City' button.")
    await trigger_regen_check(message.from_user.id, state) # Реген перед входом в город
    await message.answer("Добро пожаловать в город! Что вас интересует?", reply_markup=get_city_menu_keyboard())

# Обработчик для всех кнопок с текстом "(скоро)"
@router.message(F.text.lower().contains("(скоро)"))
async def handle_coming_soon(message: Message, state: FSMContext): # Добавляем state
    """Обрабатывает нажатия на любые кнопки, содержащие '(скоро)'."""
    logging.debug(f"User {message.from_user.id} clicked a 'coming soon' button: {message.text}")
    await trigger_regen_check(message.from_user.id, state) # Реген даже при нажатии на неактивные
    await message.answer("Этот раздел еще находится в разработке! 🚧 Скоро здесь что-то появится.")

# Оставляем команду /menu как запасной вариант для вызова главного меню
@router.message(Command("menu"))
async def handle_menu_command(message: Message, state: FSMContext): # Добавляем state
    """Обрабатывает команду /menu для отображения главного меню."""
    logging.debug(f"User {message.from_user.id} used /menu command.")
    user_id = message.from_user.id
    # Проверяем реген перед показом меню
    await trigger_regen_check(user_id, state)
    player = await get_player(user_id) # Достаточно базовых данных для проверки существования
    if player:
        await message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())
    else:
        await message.answer("Сначала начните игру командой /start")

# Команда /help
@router.message(Command("help"))
async def handle_help_command(message: Message, state: FSMContext): # Добавляем state
     """Обрабатывает команду /help, выводя базовую информацию."""
     logging.debug(f"User {message.from_user.id} used /help command.")
     await trigger_regen_check(message.from_user.id, state) # Реген при запросе помощи
     await message.answer(
         "👋 <b>Добро пожаловать в ПоЕ-Бот!</b>\n\n"
         "Это текстовая игра по мотивам Path of Exile прямо в Telegram.\n\n"
         "Используйте <b>кнопки внизу экрана</b> для взаимодействия с игрой:\n"
         "👤 <b>Профиль:</b> Ваши статы, уровень, квесты.\n"
         "🎒 <b>Инвентарь:</b> Просмотр и управление предметами.\n" # Добавили инвентарь
         "🗺️ <b>Задания:</b> Получить ежедневный квест.\n"
         "💪 <b>Прокачка:</b> Распределить очки характеристик.\n"
         "⚔️ <b>Бой:</b> Сразиться с монстрами.\n"
         "🏘️ <b>Город:</b> Посетить Лекаря и будущие магазины.\n"
         "🎁 <b>Ежедневная награда:</b> Получить бонус раз в день.\n"
         "🏆 <b>Рейтинг:</b> Таблицы лидеров (в разработке).\n\n"
         "Если кнопки исчезли, введите команду /menu.\n"
         "Удачи в Рэкласте, изгнанник!",
         parse_mode="HTML" # Используем HTML для форматирования
     )

# --- Обработчик для любых других текстовых сообщений ---
# Полезно для отладки или для ответа на случайные сообщения
# Важно: этот обработчик должен быть ПОСЛЕДНИМ среди message-хендлеров,
# чтобы не перехватывать нажатия кнопок, обрабатываемые через F.text
# @router.message()
# async def handle_unknown_text(message: Message, state: FSMContext):
#     logging.debug(f"Received unhandled text from {message.from_user.id}: {message.text}")
#     await trigger_regen_check(message.from_user.id, state)
#     await message.reply("Не совсем понимаю, что ты имеешь в виду 🤔\n"
#                         "Попробуй использовать кнопки меню или команду /help.")
