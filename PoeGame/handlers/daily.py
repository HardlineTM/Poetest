# handlers/daily.py
import time
import math
import random
import logging
from aiogram import Router, F, types
from aiogram.filters import Command # Оставляем Command, если вдруг понадобится
from aiogram.fsm.context import FSMContext # Импортируем FSMContext
from datetime import datetime, timedelta # Не используется, но может пригодиться
from aiogram.utils.text_decorations import html_decoration as hd # Для экранирования имен монстров

# Импортируем нужные функции из db_manager
from database.db_manager import (
    get_player, set_daily_reward_time, assign_daily_quest, clear_daily_quest,
    update_player_xp, check_and_apply_regen # Добавляем check_and_apply_regen
)
# Импортируем данные о монстрах для квестов
from game_data import MONSTERS

# Настройка логирования
# logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")

router = Router()

# Константы кулдаунов и наград
DAILY_REWARD_COOLDOWN = 24 * 60 * 60 # 24 часа в секундах
DAILY_QUEST_COOLDOWN = 24 * 60 * 60  # 24 часа в секундах
DAILY_REWARD_GOLD = 50 # Базовая награда

async def trigger_regen_check(user_id: int, state: FSMContext):
     """Вспомогательная функция для вызова регенерации."""
     current_state_str = await state.get_state()
     await check_and_apply_regen(user_id, current_state_str)

# Обработчик кнопки "Ежедневная награда"
@router.message(F.text.lower() == "🎁 ежедневная награда")
async def handle_daily_reward(message: types.Message, state: FSMContext): # Добавляем state
    user_id = message.from_user.id
    logging.debug(f"User {user_id} requested daily reward.")

    # --- Вызов регенерации ---
    await trigger_regen_check(user_id, state)

    # Получаем данные игрока ПОСЛЕ регена
    player = await get_player(user_id)

    if not player:
        logging.warning(f"Non-player {user_id} tried to get daily reward.")
        await message.answer("Сначала создайте персонажа: /start")
        return

    current_time = int(time.time())
    last_reward_time = player['last_daily_reward_time']
    time_passed = current_time - last_reward_time

    if time_passed >= DAILY_REWARD_COOLDOWN:
        # Начисляем награду (только золото)
        _, _ = await update_player_xp(user_id, gained_gold=DAILY_REWARD_GOLD) # Функция вернет None, False
        # Обновляем время последней награды
        await set_daily_reward_time(user_id)
        await message.answer(f"🎉 Вы получили ежедневную награду: {DAILY_REWARD_GOLD} золота!")
        logging.info(f"Player {user_id} claimed daily reward ({DAILY_REWARD_GOLD} gold).")
    else:
        time_left = DAILY_REWARD_COOLDOWN - time_passed
        hours, remainder = divmod(time_left, 3600)
        minutes, seconds = divmod(remainder, 60)
        # Формируем строку с оставшимся временем
        time_left_str = ""
        if hours > 0:
            time_left_str += f"{int(hours)} ч "
        if minutes > 0:
            time_left_str += f"{int(minutes)} мин "
        # Добавим секунды для наглядности, если осталось мало времени
        if hours == 0 and minutes < 5:
            time_left_str += f"{int(seconds)} сек"

        await message.answer(
            f"Вы уже получали награду сегодня.\n"
            f"Следующая награда будет доступна через: {time_left_str.strip()}."
        )
        logging.debug(f"User {user_id} daily reward is on cooldown. Time left: {time_left}")

# Обработчик кнопки "Задания"
@router.message(F.text.lower() == "🗺️ задания")
async def handle_daily_quest_menu(message: types.Message, state: FSMContext): # Добавляем state
    user_id = message.from_user.id
    logging.debug(f"User {user_id} requested daily quests menu.")

    # --- Вызов регенерации ---
    await trigger_regen_check(user_id, state)

    # Получаем данные игрока ПОСЛЕ регена
    player = await get_player(user_id)

    if not player:
        logging.warning(f"Non-player {user_id} tried to access quests.")
        await message.answer("Сначала создайте персонажа: /start")
        return

    # Показываем текущий квест или предлагаем взять новый
    if player['quest_monster_key']:
         # Экранируем имя монстра для безопасности
         quest_monster_key_escaped = hd.quote(player['quest_monster_key'])
         await message.answer(
             f"📜 <b>Ваше текущее задание:</b>\n"
             f"   Цель: Убить {quest_monster_key_escaped} ({player['quest_current_count']}/{player['quest_target_count']})\n"
             f"   Награда: {player['quest_gold_reward']} золота, {player['quest_xp_reward']} XP\n\n"
             f"<i>Убивайте нужных монстров в бою (кнопка '⚔️ Бой с монстром'), чтобы выполнить задание.</i>",
             parse_mode="HTML"
         )
         logging.debug(f"User {user_id} viewed active quest: Kill {player['quest_target_count']} {player['quest_monster_key']}")
    else:
        # Проверяем кулдаун на взятие квеста
        current_time = int(time.time())
        last_quest_time = player['last_quest_time']
        time_passed = current_time - last_quest_time

        if last_quest_time == 0 or time_passed >= DAILY_QUEST_COOLDOWN:
            # Генерируем новый квест
            # Можно добавить логику выбора монстров в зависимости от уровня игрока
            possible_monsters = list(MONSTERS.keys())
            if not possible_monsters:
                 logging.error("Cannot generate quest: MONSTERS list is empty in game_data.py")
                 await message.answer("Не удалось сгенерировать квест (ошибка конфигурации монстров).")
                 return

            target_monster = random.choice(possible_monsters)
            target_count = random.randint(3, 10) # Количество монстров
            monster_data = MONSTERS.get(target_monster)
            if not monster_data:
                 logging.error(f"Cannot generate quest: Monster data for '{target_monster}' not found.")
                 await message.answer("Не удалось сгенерировать квест (ошибка данных монстра).")
                 return

            # Рассчитываем награду (простая формула на основе опыта монстра и количества)
            # Множитель для баланса награды
            reward_multiplier = 1.2
            gold_reward = math.ceil(target_count * (monster_data['xp_reward'] // 2 + 2) * reward_multiplier)
            xp_reward = math.ceil(target_count * monster_data['xp_reward'] * reward_multiplier + 10)

            # Назначаем квест
            await assign_daily_quest(user_id, target_monster, target_count, gold_reward, xp_reward)

            # Экранируем имя для вывода
            target_monster_escaped = hd.quote(target_monster)
            await message.answer(
                f"📜 <b>Новое ежедневное задание получено!</b>\n"
                f"   Цель: Убить {target_monster_escaped} ({target_count} шт.)\n"
                f"   Награда: {gold_reward} золота, {xp_reward} XP\n\n"
                f"<i>Отправляйтесь на охоту! (кнопка '⚔️ Бой с монстром')</i>",
                parse_mode="HTML"
            )
            logging.info(f"User {user_id} received new quest: Kill {target_count} {target_monster}.")

        else:
            # Квест на кулдауне
            time_left = DAILY_QUEST_COOLDOWN - time_passed
            hours, remainder = divmod(time_left, 3600)
            minutes, seconds = divmod(remainder, 60)
            # Формируем строку
            time_left_str = ""
            if hours > 0: time_left_str += f"{int(hours)} ч "
            if minutes > 0: time_left_str += f"{int(minutes)} мин "
            if hours == 0 and minutes < 5: time_left_str += f"{int(seconds)} сек"

            await message.answer(
                f"Вы уже брали задание сегодня.\n"
                f"Новое задание будет доступно через: {time_left_str.strip()}."
            )
            logging.debug(f"User {user_id} quest generation is on cooldown. Time left: {time_left}")
