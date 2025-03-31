# handlers/boss.py
import logging
import time
import random
import math
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.text_decorations import html_decoration as hd
from aiogram.exceptions import TelegramBadRequest # Для обработки ошибок API

# Импортируем все необходимое из БД
from database.db_manager import (
    get_player_effective_stats, update_player_vitals, update_player_xp,
    # update_quest_progress, clear_daily_quest, # Убрал, т.к. квесты не влияют на боссов
    apply_death_penalty,
    check_and_apply_regen, add_item_to_inventory,
    get_player_boss_progression, update_player_boss_progression,
    get_boss_cooldown, set_boss_cooldown,
    get_learned_spells # Добавляем для получения спеллов
)
# Импортируем данные игры
from game_data import (
    BOSSES, SPELLS, ALL_ITEMS, ITEM_TYPE_FRAGMENT, ITEM_TYPE_LEGENDARY,
    get_random_legendary_item_id,
    calculate_final_spell_damage, # Используем новую функцию для урона спеллов
    calculate_damage_with_crit # Используем новую функцию для крита
)
# Импортируем остальные функции расчета (лучше вынести в utils)
try:
    from handlers.combat import (
        calculate_player_attack_damage, # Используем обновленную функцию
        # calculate_spell_damage, # Старая не нужна
        calculate_dodge_chance,
        calculate_damage_reduction
    )
    # Импортируем CombatStates для проверки регена
    from handlers.combat import CombatStates
except ImportError as e:
    logging.error(f"Could not import helpers from handlers.combat in boss.py: {e}")
    # Заглушки
    def calculate_player_attack_damage(s, cc, cd): return calculate_damage_with_crit(max(1,s//2), cc, cd) # Используем новую крит функцию
    # def calculate_spell_damage(d, cc, cd): return calculate_damage_with_crit(d.get('damage', 1), cc, cd) # Старая не нужна
    def calculate_dodge_chance(d): return 0
    def calculate_damage_reduction(a): return 0
    class CombatStates: fighting = type("State", (), {"state": "CombatStates:fighting"})()

# Настройка логгера
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - [%(filename)s:%(lineno)d] - %(message)s")
router = Router()

# Константы
BOSS_COOLDOWN_SECONDS = 60 * 60 # 1 час
LEGENDARY_DROP_CHANCE = 0.02 # 2%

# --- Состояния для Боя с Боссом ---
class BossCombatStates(StatesGroup):
    fighting = State()
    selecting_boss = State()

# --- Клавиатуры ---
def get_boss_selection_keyboard(unlocked_index: int) -> InlineKeyboardMarkup:
    """Генерирует кнопки для выбора доступных боссов."""
    buttons = []
    num_bosses = len(BOSSES)
    for i in range(num_bosses):
        boss_data = BOSSES[i]
        boss_id_str = str(i) # Используем индекс как ID для callback
        if i <= unlocked_index:
            buttons.append([InlineKeyboardButton(text=f"💀 {boss_data['name']} (Ур. {i+1})", callback_data=f"boss_select:{boss_id_str}")])
        else:
            buttons.append([InlineKeyboardButton(text=f"🔒 ??? (Ур. {i+1})", callback_data="boss_locked")])
    buttons.append([InlineKeyboardButton(text="Закрыть", callback_data="boss_select:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- ИСПРАВЛЕНО: async def ---
async def get_boss_combat_action_keyboard(user_id: int, boss_id: str, player_mana: int, active_effects: dict) -> InlineKeyboardMarkup:
    """Генерирует кнопки действий в бою с боссом, включая изученные спеллы."""
    buttons = [
        [InlineKeyboardButton(text="🗡️ Атаковать", callback_data=f"boss_action:attack:{boss_id}")],
    ]
    learned_spells = await get_learned_spells(user_id) # Получаем изученные спеллы
    try: # Безопасно получаем множитель маны
         mana_multiplier = float(active_effects.get('mana_cost_multiplier', 1.0))
         if mana_multiplier <= 0: mana_multiplier = 1.0 # Защита от неверных значений
    except (ValueError, TypeError): mana_multiplier = 1.0

    for spell_data in learned_spells:
        spell_id = spell_data['id']
        spell_name = spell_data['name']
        try: # Безопасно получаем стоимость
             base_mana_cost = int(spell_data['mana_cost'])
             actual_mana_cost = math.ceil(base_mana_cost * mana_multiplier)
        except (ValueError, TypeError, KeyError):
             logging.warning(f"Invalid mana cost for spell {spell_id}. Skipping.")
             continue # Пропускаем спелл с неверной стоимостью

        cost_text = f" ({actual_mana_cost} Маны)"

        if player_mana >= actual_mana_cost:
            buttons.append([
                InlineKeyboardButton(
                    text=f"✨ {hd.quote(spell_name)}{cost_text}",
                    callback_data=f"boss_action:{spell_id}:{boss_id}" # Используем ID спелла
                )
            ])
        else:
             buttons.append([
                InlineKeyboardButton(
                    text=f"❌ {hd.quote(spell_name)}{cost_text}",
                    callback_data=f"boss_action:no_mana"
                )
            ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- Обработчики ---

# Обработчик кнопки/команды Босс
@router.message(F.text.lower() == "💀 бой с боссом")
async def select_boss_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    logging.info(f"User {user_id} requested boss fight selection.")
    try: await check_and_apply_regen(user_id, await state.get_state())
    except Exception as e: logging.error(f"Regen check error for boss selection {user_id}: {e}")

    unlocked_index = await get_player_boss_progression(user_id)
    keyboard = get_boss_selection_keyboard(unlocked_index)
    await message.answer("Выберите босса для сражения:", reply_markup=keyboard)
    await state.set_state(BossCombatStates.selecting_boss)


# Обработчик нажатия на заблокированного босса
@router.callback_query(BossCombatStates.selecting_boss, F.data == "boss_locked")
async def handle_locked_boss(callback: types.CallbackQuery):
    await callback.answer("Вы еще не открыли этого босса! Победите предыдущих.", show_alert=True)

# Обработчик отмены выбора босса
@router.callback_query(BossCombatStates.selecting_boss, F.data == "boss_select:cancel")
async def handle_cancel_boss_selection(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Выбор босса отменен.")
    await state.clear()
    # --- ИСПРАВЛЕНИЕ: try с новой строки и отступом ---
    try:
        await callback.message.delete()
    except Exception:
        pass

# Обработчик выбора КОНКРЕТНОГО босса
@router.callback_query(BossCombatStates.selecting_boss, F.data.startswith("boss_select:"))
async def start_boss_fight(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    try:
        boss_index = int(callback.data.split(":")[1])
        if not (0 <= boss_index < len(BOSSES)): raise ValueError("Invalid boss index")
        boss_id_str = str(boss_index)
        boss_data = BOSSES[boss_index]
        boss_name = boss_data['name']
    except (IndexError, ValueError) as e:
        logging.error(f"Invalid boss selection callback data: {callback.data} - {e}")
        await callback.answer("Ошибка выбора босса.", show_alert=True)
        await state.clear()
        try: await callback.message.delete()
        except Exception: pass
        return

    logging.info(f"User {user_id} selected boss {boss_id_str} ('{boss_name}')")

    # 1. Проверка кулдауна
    last_kill_time = await get_boss_cooldown(user_id, boss_id_str)
    current_time = int(time.time())
    time_since_kill = current_time - last_kill_time
    if 0 < time_since_kill < BOSS_COOLDOWN_SECONDS:
        time_left = BOSS_COOLDOWN_SECONDS - time_since_kill
        minutes, seconds = divmod(time_left, 60)
        time_left_str = f"{int(minutes)} мин {int(seconds)} сек" if minutes > 0 else f"{int(seconds)} сек"
        await callback.answer(f"Босс '{boss_name}' на кулдауне! Осталось: {time_left_str}.", show_alert=True)
        logging.info(f"User {user_id} tried to fight boss {boss_id_str} on cooldown.")
        return # Не сбрасываем состояние

    # 2. Проверка HP и восстановление ES
    player = await get_player_effective_stats(user_id)
    if not player:
        await callback.answer("Ошибка получения данных игрока.", show_alert=True)
        await state.clear();
        try:
            await callback.message.delete()
        except Exception:
            pass
        return
    if player['current_hp'] <= 0:
        await callback.answer("Вы без сознания! Сначала исцелитесь.", show_alert=True)
        return

    if player['energy_shield'] < player['max_energy_shield']:
        logging.info(f"Restoring ES for player {user_id} before boss fight.")
        await update_player_vitals(user_id, set_es=player['max_energy_shield'])
        player = await get_player_effective_stats(user_id)
        if not player: await callback.answer("Ошибка восстановления энергощита.", show_alert=True); return

    # 3. Скалирование босса
    scale_factor = 2 ** boss_index
    scaled_hp = math.ceil(boss_data['base_hp'] * scale_factor)
    scaled_damage = math.ceil(boss_data['base_damage'] * scale_factor)
    scaled_xp = math.ceil(100 * (scale_factor * 1.5))
    scaled_gold = math.ceil(50 * scale_factor)

    logging.info(f"Player {user_id} starting fight with BOSS {boss_id_str} ('{boss_name}'). Scaled HP: {scaled_hp}, Dmg: {scaled_damage}, XP: {scaled_xp}, Gold: {scaled_gold}")

    # 4. Установка состояния боя
    await state.set_state(BossCombatStates.fighting)
    await state.update_data(
        boss_id=boss_id_str,
        boss_name=boss_name,
        boss_hp=scaled_hp,
        boss_max_hp=scaled_hp,
        boss_damage=scaled_damage,
        boss_xp_reward=scaled_xp,
        boss_gold_reward=scaled_gold,
        fragment_item_id=boss_data['fragment_item_id'],
        player_buffs={} # Инициализация баффов
    )

    # 5. Отправка сообщения о начале боя
    keyboard = await get_boss_combat_action_keyboard(user_id, boss_id_str, player['current_mana'], player.get('active_effects',{}))
    try:
        await callback.message.edit_text( # Редактируем сообщение выбора босса
            f"Вы вступаете в бой с <b>{hd.quote(boss_name)}</b>!\n"
            f"❤️ HP: {scaled_hp} | ⚔️ Урон: {scaled_damage}\n\n"
            f"Ваши статы:\n"
            f"❤️ HP: {player['current_hp']}/{player['max_hp']} | 🛡️ ES: {player['energy_shield']}/{player['max_energy_shield']} | 💧 Mana: {player['current_mana']}/{player['max_mana']}\n\n"
            f"Выберите действие:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
         logging.error(f"Failed to edit message for boss fight start: {e}")
         await callback.message.answer( # Отправить новым сообщением
             f"Вы вступаете в бой с <b>{hd.quote(boss_name)}</b>!\n"
             f"❤️ HP: {scaled_hp} | ⚔️ Урон: {scaled_damage}\n\n"
             f"Ваши статы:\n"
             f"❤️ HP: {player['current_hp']}/{player['max_hp']} | 🛡️ ES: {player['energy_shield']}/{player['max_energy_shield']} | 💧 Mana: {player['current_mana']}/{player['max_mana']}\n\n"
             f"Выберите действие:",
             reply_markup=keyboard, parse_mode="HTML"
         )


# Обработчик действий в бою с боссом
@router.callback_query(BossCombatStates.fighting, F.data.startswith("boss_action:"))
async def handle_boss_combat_action(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id

    player = await get_player_effective_stats(user_id)
    state_data = await state.get_data()

    # Получение данных боя из состояния
    boss_id = state_data.get("boss_id")
    boss_name = state_data.get("boss_name")
    current_boss_hp = state_data.get("boss_hp")
    boss_max_hp = state_data.get("boss_max_hp")
    boss_damage = state_data.get("boss_damage")
    boss_xp_reward = state_data.get("boss_xp_reward")
    boss_gold_reward = state_data.get("boss_gold_reward")
    fragment_item_id = state_data.get("fragment_item_id")
    current_buffs = state_data.get("player_buffs", {}) # Баффы с прошлого хода

    if (not player or boss_id is None or boss_name is None or current_boss_hp is None or
            boss_max_hp is None or boss_damage is None or boss_xp_reward is None or
            boss_gold_reward is None or fragment_item_id is None):
        logging.error(f"Incomplete boss combat state for user {user_id}. Data: {state_data}")
        try: await callback.message.edit_text("Ошибка состояния боя с боссом. Бой прерван.")
        except Exception: pass
        await state.clear(); return

    action_data = callback.data.split(":")
    action_type = action_data[1]

    if action_type == "no_mana": return

    # --- Переменные для хода игрока ---
    player_damage_dealt = 0; mana_cost = 0; action_log = ""; is_crit = False; healed_amount = 0; applied_buffs = {}

    # --- Эффекты и Баффы ---
    active_effects = player.get('active_effects', {});
    try: mana_multiplier = float(active_effects.get('mana_cost_multiplier', 1.0)); mana_multiplier = max(0, mana_multiplier)
    except (ValueError, TypeError): mana_multiplier = 1.0
    try: crit_mult_bonus = float(active_effects.get('crit_multiplier_bonus', 0))
    except (ValueError, TypeError): crit_mult_bonus = 0

    # --- Логика действия игрока ---
    if action_type == "attack":
        attack_multiplier = current_buffs.get("buff_next_attack", 1.0)
        # Используем функцию из combat (или utils)
        player_damage_dealt, is_crit = calculate_player_attack_damage(player['strength'], player['crit_chance'], player['crit_damage'] + crit_mult_bonus)
        player_damage_dealt = math.ceil(player_damage_dealt * attack_multiplier) # Применяем бафф
        crit_text = "💥<b>КРИТ!</b> " if is_crit else ""; buff_text = f"(x{attack_multiplier:.1f}!) " if attack_multiplier > 1.0 else ""
        action_log = f"Вы атаковали 🗡️ {buff_text}{crit_text}и нанесли {player_damage_dealt} урона."
        if "buff_next_attack" in current_buffs: del current_buffs["buff_next_attack"] # Удаляем бафф

    else: # Заклинание
        spell_id = action_type
        spell_data = SPELLS.get(spell_id)
        if not spell_data: await callback.answer("Ошибка: заклинание не найдено.", show_alert=True); return

        try: base_mana_cost = int(spell_data['mana_cost']); actual_mana_cost = math.ceil(base_mana_cost * mana_multiplier)
        except Exception: actual_mana_cost = 99999

        if player['current_mana'] >= actual_mana_cost:
            mana_cost = actual_mana_cost; spell_name = spell_data['name']; cost_text = f" ({mana_cost} М)"
            effect_type = spell_data.get('effect_type'); effect_value = spell_data.get('effect_value'); duration = spell_data.get('duration', 0)
            action_log = f"Вы использовали ✨ {hd.quote(spell_name)}{cost_text}"

            if effect_type == "damage":
                base_damage = effect_value; final_base_damage = calculate_final_spell_damage(base_damage, player['intelligence'])
                # Используем calculate_damage_with_crit для крита
                player_damage_dealt, is_crit = calculate_damage_with_crit(final_base_damage, player['crit_chance'], player['crit_damage'] + crit_mult_bonus)
                crit_text = "💥<b>КРИТ!</b> " if is_crit else ""; action_log += f", {crit_text}нанеся {player_damage_dealt} урона."
            elif effect_type == "heal_percent":
                percent = effect_value; heal_calc = math.ceil(player['max_hp'] * (percent / 100.0))
                heal_actual = min(heal_calc, player['max_hp'] - player['current_hp']); healed_amount = heal_actual
                action_log += f", восстановив {healed_amount} здоровья."
            elif effect_type == "buff_next_attack":
                applied_buffs["buff_next_attack"] = effect_value; action_log += f", усилив след. атаку (x{effect_value:.1f})."
            elif effect_type == "temp_buff":
                if isinstance(effect_value, dict) and duration > 0:
                     buff_log_parts = []
                     for stat_name, buff_val in effect_value.items():
                         applied_buffs[f"temp_{stat_name}"] = {'value': buff_val, 'duration': duration}
                         buff_log_parts.append(f"+{buff_val} {stat_name}")
                     if buff_log_parts: action_log += f", усилив {', '.join(buff_log_parts)} на {duration} хода."
                     else: action_log += ", но бафф не сработал (ошибка данных)."
                else: action_log += ", но бафф не сработал (неверные данные)."
            else: action_log += ", но ничего не произошло (неизвестный эффект)."
        else: await callback.answer("Недостаточно маны!", show_alert=True); return

    # --- Применяем изменения HP/Mana игрока ---
    await update_player_vitals(user_id, hp_change=healed_amount, mana_change=-mana_cost)

    # --- Обновляем баффы в состоянии FSM ---
    next_turn_buffs = {} # Баффы для СЛЕДУЮЩЕГО хода
    buffs_expired_log = []
    for buff_key, buff_data in current_buffs.items(): # Обходим баффы с ПРОШЛОГО хода
        if isinstance(buff_data, dict) and 'duration' in buff_data:
            remaining_duration = buff_data['duration'] - 1
            if remaining_duration > 0: next_turn_buffs[buff_key] = {'value': buff_data['value'], 'duration': remaining_duration}
            else: buffs_expired_log.append(buff_key.replace('temp_', ''))
    if buffs_expired_log: logging.info(f"Buffs expired for user {user_id}: {', '.join(buffs_expired_log)}")
    next_turn_buffs.update(applied_buffs) # Добавляем/обновляем новыми баффами
    await state.update_data(player_buffs=next_turn_buffs) # Сохраняем для следующего хода
    logging.debug(f"Player {user_id} buffs for next turn: {next_turn_buffs}")

    # --- Обновление HP босса и проверка победы ---
    new_boss_hp = current_boss_hp
    if player_damage_dealt > 0:
        new_boss_hp = max(0, current_boss_hp - player_damage_dealt)
        await state.update_data(boss_hp=new_boss_hp)

    if new_boss_hp <= 0: # Победа
        logging.info(f"Player {user_id} DEFEATED BOSS {boss_id} ('{boss_name}')!")
        xp_gain = boss_xp_reward; gold_gain = boss_gold_reward
        # Эффект золота
        try: triple_gold_chance = float(active_effects.get('triple_gold_chance', 0))
        except (ValueError, TypeError): triple_gold_chance = 0
        if random.uniform(0, 100) < triple_gold_chance: gold_gain *= 3; loot_log = f"💰 <b>УТРОЕННОЕ</b> золото: {gold_gain}!\n"
        else: loot_log = f"💰 Получено {gold_gain} золота.\n"
        # Дроп фрагмента
        fragment_info = ALL_ITEMS.get(fragment_item_id); fragment_log = ""
        if fragment_info:
            if await add_item_to_inventory(user_id, fragment_item_id): fragment_log = f"💎 Фрагмент: <b>{hd.quote(fragment_info['name'])}</b>!\n"
        # Шанс на легендарку
        legendary_log = ""
        if random.random() < LEGENDARY_DROP_CHANCE:
            legendary_id = get_random_legendary_item_id()
            if legendary_id:
                 legendary_info = ALL_ITEMS.get(legendary_id)
                 if legendary_info and await add_item_to_inventory(user_id, legendary_id):
                     legendary_log = f"✨✨ <b>ЛЕГЕНДАРКА: {hd.quote(legendary_info['name'])}</b>!!! ✨✨\n"
        # Обновление XP/Золота, прогресса, кулдауна
        xp_update_result, leveled_up = await update_player_xp(user_id, gained_xp=xp_gain, gained_gold=gold_gain)
        boss_index = int(boss_id); await update_player_boss_progression(user_id, boss_index); await set_boss_cooldown(user_id, boss_id)
        # Восстановление ES
        player_after_boss = await get_player_effective_stats(user_id)
        if player_after_boss and player_after_boss['energy_shield'] < player_after_boss['max_energy_shield']:
             await update_player_vitals(user_id, set_es=player_after_boss['max_energy_shield'])
        # Завершаем бой и реген
        await state.clear(); await check_and_apply_regen(user_id, None)
        # Сообщение
        level_up_log = ""
        if leveled_up and xp_update_result: level_up_log = (f"🎉<b>УРОВЕНЬ {xp_update_result['level']}!</b> (+{xp_update_result['gained_stat_points']} очка)🎉\n")
        result_text = (f"{action_log}\n\n"
                       f"🔥🔥🔥 <b>ПОБЕДА: {hd.quote(boss_name)}!</b> 🔥🔥🔥\n\n"
                       f"✨ +{xp_gain} опыта.\n{loot_log}{fragment_log}{legendary_log}{level_up_log}"
                       f"\n<i>Босс будет доступен через {BOSS_COOLDOWN_SECONDS // 60} мин.</i>")
        try: await callback.message.edit_text(result_text, parse_mode="HTML")
        except Exception as e: await callback.message.answer(result_text, parse_mode="HTML")
        return

    # --- Ход Босса ---
    boss_raw_damage = boss_damage; dodge_chance = calculate_dodge_chance(player['dexterity'])
    # Учитываем временные баффы брони игрока, сохраненные для этого хода
    current_turn_buffs = next_turn_buffs
    player_armor = player['armor'] + current_turn_buffs.get('temp_armor', {}).get('value', 0)
    player_damage_reduction = calculate_damage_reduction(player_armor)
    player_hp_loss = 0; boss_action_log = ""
    if random.uniform(0, 100) < dodge_chance:
        boss_action_log = f"<b>{hd.quote(boss_name)}</b> атаковал, но вы увернулись! 💨"
    else:
        actual_damage = max(1, boss_raw_damage - player_damage_reduction)
        player_hp_loss = actual_damage
        reduction_text = f" (-{player_damage_reduction} броня{'🛡️' if current_turn_buffs.get('temp_armor') else ''})" if player_damage_reduction > 0 else ""
        boss_action_log = f"<b>{hd.quote(boss_name)}</b> атаковал 👹 и нанес вам <b>{actual_damage}</b> урона{reduction_text}."

    # --- Обновляем виталы игрока ПОСЛЕ хода босса ---
    logging.info(f"[handle_boss_combat_action CALLING_VITALS for boss attack] User {user_id}: hp_change={-player_hp_loss}")
    new_hp, new_mana, new_es = await update_player_vitals(user_id, hp_change=-player_hp_loss)
    logging.info(f"[handle_boss_combat_action VITALS_RETURNED after boss] User {user_id}: NewHP={new_hp}, NewMana={new_mana}, NewES={new_es}")

    # --- Проверка поражения игрока ---
    if new_hp <= 0: # Поражение
        logging.info(f"Player {user_id} was defeated by BOSS {boss_id} ('{boss_name}').")
        xp_penalty, gold_penalty = await apply_death_penalty(user_id); penalty_log = f"☠️ Потеряно: {xp_penalty} XP, {gold_penalty} 💰."
        # Восстанавливаем ES
        player_after_death_b = await get_player_effective_stats(user_id)
        if player_after_death_b: await update_player_vitals(user_id, set_es=player_after_death_b['max_energy_shield'])
        # Завершаем бой и реген
        await state.clear(); await check_and_apply_regen(user_id, None)
        # Сообщение
        result_text = (f"{action_log}\n{boss_action_log}\n\n"
                       f"<b>Вы повержены: {hd.quote(boss_name)}...</b> 💀\n{penalty_log}")
        try: await callback.message.edit_text(result_text, parse_mode="HTML")
        except Exception as e: await callback.message.answer(result_text, parse_mode="HTML")
        return

    # --- Бой продолжается ---
    updated_player = await get_player_effective_stats(user_id)
    if not updated_player: await callback.message.edit_text("Ошибка данных. Бой прерван."); await state.clear(); return
    keyboard = await get_boss_combat_action_keyboard(user_id, boss_id, updated_player['current_mana'], updated_player.get('active_effects', {}))
    # Отображение баффов
    active_buff_texts = []
    for buff_key, buff_data in next_turn_buffs.items():
         if isinstance(buff_data, dict) and 'duration' in buff_data: active_buff_texts.append(f"{buff_key.replace('temp_', '').capitalize()} (+{buff_data['value']}) [{buff_data['duration']} х.]")
         elif buff_key == "buff_next_attack": active_buff_texts.append(f"Усиление атаки (x{buff_data:.1f})")
    buff_display = " / ".join(active_buff_texts); buff_line = f"\n<i>Эффекты: {buff_display}</i>" if buff_display else ""
    # Сообщение
    result_text = (f"{action_log}\n{boss_action_log}\n\n"
                   f"<b>{hd.quote(boss_name)}</b>\n❤️ HP: {new_boss_hp}/{boss_max_hp}\n\n"
                   f"<b>Ваши статы:</b>\n❤️ HP: {updated_player['current_hp']}/{updated_player['max_hp']} | 🛡️ ES: {updated_player['energy_shield']}/{updated_player['max_energy_shield']} | 💧 Mana: {updated_player['current_mana']}/{updated_player['max_mana']}"
                   f"{buff_line}\n\nВыберите действие:")
    try:
        await callback.message.edit_text(result_text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Error editing boss combat message: {e}")
        await callback.message.answer("Ошибка отображения боя. Бой прерван."); await state.clear()


# --- Обработчики нажатий кнопок босса ВНЕ состояния ---
@router.callback_query(F.data.startswith("boss_action:"))
async def handle_boss_action_outside_state(callback: types.CallbackQuery, state: FSMContext):
    logging.warning(f"User {callback.from_user.id} pressed boss_action button outside of state '{await state.get_state()}'. CB: {callback.data}")
    await callback.answer("Этот бой с боссом уже завершен или неактивен.", show_alert=True)
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except Exception: pass

@router.callback_query(F.data.startswith("boss_select:"))
async def handle_boss_select_outside_state(callback: types.CallbackQuery, state: FSMContext):
     logging.warning(f"User {callback.from_user.id} pressed boss_select button outside of state '{await state.get_state()}'. CB: {callback.data}")
     await callback.answer("Выбор босса больше не актуален.", show_alert=True)
     try: await callback.message.edit_reply_markup(reply_markup=None)
     except Exception: pass

# --- Конец файла handlers/boss.py ---
