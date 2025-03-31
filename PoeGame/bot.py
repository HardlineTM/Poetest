# bot.py
import asyncio
import logging # Импортируем модуль логирования

# Импортируем компоненты aiogram
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
# Импортируем DefaultBotProperties для настроек бота по умолчанию
from aiogram.client.default import DefaultBotProperties

# Импортируем токен из конфига и функцию инициализации БД
from config import BOT_TOKEN
from database.db_manager import init_db

# Импортируем все роутеры из папки handlers
# Убедись, что все эти файлы существуют в папке handlers
from handlers import common, profile, combat, daily, city, stats, inventory, ranking, boss, shop, gambler, blacksmith, magic_school

# --- Основная асинхронная функция ---
async def main():
    # --- Настройка логирования ---
    # Устанавливаем уровень INFO. Для более детальной отладки можно поставить logging.DEBUG
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - [%(filename)s:%(lineno)d] - %(message)s", # Добавили имя файла и строку
        # filename='bot.log', # Раскомментируй для записи логов в файл
        # filemode='a' # 'a' - дописывать в файл, 'w' - перезаписывать
    )
    logging.info("Initializing bot...")

    # Инициализируем базу данных (создаем/обновляем таблицы)
    try:
        await init_db()
        logging.info("Database initialization complete.")
    except Exception as e:
        logging.critical(f"CRITICAL: Failed to initialize database: {e}", exc_info=True)
        return # Завершаем работу, если БД не готова

    # Используем MemoryStorage для хранения состояний FSM
    storage = MemoryStorage()

    # Создаем объект с настройками по умолчанию для бота (ParseMode=HTML)
    default_properties = DefaultBotProperties(parse_mode="HTML")

    # Инициализируем объект бота
    bot = Bot(token=BOT_TOKEN, default=default_properties)

    # Инициализируем диспетчер
    dp = Dispatcher(storage=storage)

    # --- Регистрация роутеров ---
    logging.info("Registering handlers (routers)...")
    try:
        # Порядок регистрации может иметь значение, если фильтры пересекаются.
        # Обычно сначала регистрируют более специфичные роутеры.
        dp.include_router(common.router)    # Общие команды, меню
        dp.include_router(profile.router)   # Профиль
        dp.include_router(inventory.router) # Инвентарь (новый)
        dp.include_router(daily.router)
        dp.include_router(stats.router)     # Прокачка статов
        dp.include_router(city.router)      # Городские активности (Лекарь)
        dp.include_router(combat.router)
        dp.include_router(shop.router)      # Магазины (оружие, броня)
        dp.include_router(ranking.router)
        dp.include_router(magic_school.router)
        dp.include_router(gambler.router)   # Гемблер
        dp.include_router(blacksmith.router) # Кузнец
        dp.include_router(boss.router)    # Боевая система
        logging.info("All handlers registered successfully.")
    except Exception as e:
        logging.critical(f"CRITICAL: Failed to register handlers: {e}", exc_info=True)
        return # Завершаем работу, если хендлеры не подключены

    # Определяем типы обновлений, которые будет обрабатывать бот
    used_update_types = dp.resolve_used_update_types()
    logging.info(f"Bot will process update types: {used_update_types}")

    # Удаляем вебхук перед запуском поллинга
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("Webhook deleted (if existed). Starting polling.")
    except Exception as e:
        logging.error(f"Error deleting webhook: {e}. Continuing...", exc_info=False)

    # --- Запуск бота ---
    logging.info("Starting bot polling...")
    try:
        # Запускаем поллинг
        await dp.start_polling(bot, allowed_updates=used_update_types)
    except Exception as e:
        logging.critical(f"CRITICAL: Polling failed with error: {e}", exc_info=True)
    finally:
        # Корректное завершение сессии бота при остановке
        logging.info("Stopping bot...")
        await bot.session.close()
        logging.info("Bot session closed.")


# --- Точка входа в приложение ---
if __name__ == "__main__":
    # Устанавливаем политику цикла событий для Windows (если нужно)
    # if sys.platform == "win32":
    #     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped manually.")
    except Exception as e:
        # Логируем любые другие критические ошибки при запуске
        logging.critical(f"CRITICAL: Unhandled exception during script execution: {e}", exc_info=True)
