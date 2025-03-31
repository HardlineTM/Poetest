# handlers/combat.py
import random
import logging
import time
import math
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.text_decorations import html_decoration as hd

from database.db_manager import (
    get_player_effective_stats, update_player_vitals, update_player_xp,
    update_quest_progress, clear_daily_quest, apply_death_penalty,
    check_and_apply_regen, add_item_to_inventory, get_learned_spells
)
from game_data import (
    MONSTERS, SPELLS, ALL_ITEMS, get_random_loot_item_id,
    calculate_final_spell_damage, # Импорт функции скейлинга от инты
    calculate_damage_with_crit # <-- НОВЫЙ ИМПОРТ для крита
)
# Убедись, что эта строка удалена или закомментирована:
# from handlers.combat import ...

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - [%(filename)s:%(lineno)d] - %(message)s")

router = Router()

class CombatStates(StatesGroup):
    fighting = State()

# --- Вспомогательные функции ---

# --- ИСПРАВЛЕНИЕ: Убираем лишний else ---
def calculate_player_attack_damage(strength: int, crit_chance: float, crit_damage: float) -> tuple[int, bool]:
    """Рассчитывает базовый урон атаки, а затем применяет крит."""
    base_damage = max(1, strength // 2)
    # Вызываем общую функцию для крита
    final_damage, is_crit = calculate_damage_with_crit(base_damage, crit_chance, crit_damage)
    return final_damage, is_crit

def calculate_dodge_chance(dexterity: int) -> float:
    return min(75.0, dexterity / 5.0)
def calculate_damage_reduction(armor: int) -> int:
    return armor // 20


# --- Клавиатура действий (Обновленная) ---
async def get_combat_action_keyboard(user_id: int, monster_key: str, player_mana: int, active_effects: dict) -> InlineKeyboardMarkup:
    """Создает клавиатуру с действиями в бою, включая изученные спеллы."""
    buttons = [
        [InlineKeyboardButton(text="🗡️ Атаковать", callback_data=f"fight_action:attack:{monster_key}")],
    ]
    # Получаем изученные спеллы
    learned_spells = await get_learned_spells(user_id)
    mana_multiplier = float(active_effects.get('mana_cost_multiplier', 1.0))

    for spell_data in learned_spells:
        spell_id = spell_data['id']
        spell_name = spell_data['name']
        base_mana_cost = spell_data['mana_cost']
        actual_mana_cost = math.ceil(base_mana_cost * mana_multiplier)

        # Показываем актуальную стоимость маны
        cost_text = f" ({actual_mana_cost} М)"

        if player_mana >= actual_mana_cost:
            buttons.append([
                InlineKeyboardButton(
                    text=f"✨ {hd.quote(spell_name)}{cost_text}",
                    callback_data=f"fight_action:{spell_id}:{monster_key}" # Используем ID спелла
                )
            ])
        else:
             buttons.append([
                InlineKeyboardButton(
                    text=f"❌ {hd.quote(spell_name)}{cost_text}",
                    callback_data=f"fight_action:no_mana"
                )
            ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)



# --- Обработчики ---
@router.message(F.text.lower() == "⚔️ бой с монстром")
async def start_fight_button(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    current_state_str = await state.get_state()
    await check_and_apply_regen(user_id, current_state_str)

    player = await get_player_effective_stats(user_id)

    # --- ИСПРАВЛЕНИЕ: Убираем псевдокомментарии ---
    if not player:
        await message.answer("Сначала создайте персонажа командой /start")
        return
    if player['current_hp'] <= 0:
        await message.answer("Вы без сознания! Найдите способ исцелиться (⚕️ Лекарь).")
        return
    if current_state_str == CombatStates.fighting.state:
        state_data = await state.get_data()
        monster_key = state_data.get("monster_key")
        monster_hp = state_data.get("monster_hp")
        if monster_key and monster_hp is not None:
             base_monster_hp = MONSTERS.get(monster_key, {}).get('hp', '?') # Получаем базовое ХП для показа
             # --- ИСПРАВЛЕНИЕ: Передаем все 4 аргумента при повторном показе клавиатуры ---
             keyboard = await get_combat_action_keyboard(user_id, monster_key, player['current_mana'], player.get('active_effects',{}))
             await message.answer(
                 f"Вы уже сражаетесь с <b>{hd.quote(monster_key)}</b>!\n"
                 f"❤️ HP Монстра: {monster_hp}/{base_monster_hp}\n\n" # Можно показывать текущее/макс. скейленное, если сохраняли
                 f"Ваши статы:\n"
                 f"❤️ HP: {player['current_hp']}/{player['max_hp']} | 🛡️ ES: {player['energy_shield']}/{player['max_energy_shield']} | 💧 Mana: {player['current_mana']}/{player['max_mana']}\n\n"
                 f"Выберите действие:",
                 reply_markup=keyboard,
                 parse_mode="HTML"
             )
        else:
            await message.answer("Вы уже в бою, но произошла ошибка состояния. Сбрасываем бой.")
            await state.clear()
        return
        # --- Восстановление ES перед боем ---
    if player['energy_shield'] < player['max_energy_shield']:
        logging.info(f"Restoring ES for player {user_id} before combat.")
        await update_player_vitals(user_id, set_es=player['max_energy_shield'])
        player = await get_player_effective_stats(user_id)
        if not player:
            await message.answer("Ошибка восстановления энергощита.")
            return
        

     # --- Выбор и Скалирование Монстра ---
    monster_key = random.choice(list(MONSTERS.keys()))
    base_monster = MONSTERS[monster_key]
    player_level = player['level']

    # Формулы скалирования (можно настраивать)
    hp_multiplier = 1 + (player_level - 1) * 0.15
    damage_multiplier = 1 + (player_level - 1) * 0.10
    xp_multiplier = 1 + (player_level - 1) * 0.08
    gold_multiplier = 1 + (player_level - 1) * 0.05
    scaled_hp = math.ceil(base_monster['hp'] * hp_multiplier)
    scaled_damage = math.ceil(base_monster['damage'] * damage_multiplier)
    scaled_xp = math.ceil(base_monster['xp_reward'] * xp_multiplier)
    base_gold_drop = random.randint(1, 5) + (base_monster['xp_reward'] // 3)
    scaled_gold = math.ceil(base_gold_drop * gold_multiplier)

    logging.info(f"Player {user_id} (Lvl {player_level}) starting fight with {monster_key}. Scaled HP:{scaled_hp}, Dmg:{scaled_damage}, XP:{scaled_xp}, Gold:{scaled_gold}")

    await state.update_data(
        monster_key=monster_key,
        monster_hp=scaled_hp,
        monster_max_hp=scaled_hp, # Сохраняем макс ХП для отображения
        monster_damage=scaled_damage,
        monster_xp_reward=scaled_xp,
        monster_gold_reward=scaled_gold,
        player_buffs={} # Инициализируем пустой словарь баффов в начале боя
    )
    await state.set_state(CombatStates.fighting)


    keyboard = await get_combat_action_keyboard(user_id, monster_key, player['current_mana'], player.get('active_effects',{}))
    await message.answer(
        f"На вашем пути встает <b>{hd.quote(monster_key)}</b> (Ур. {player['level']})!\n"
        f"❤️ HP: {scaled_hp} | ⚔️ Урон: {scaled_damage}\n\n"
        f"Ваши статы:\n"
        f"❤️ HP: {player['current_hp']}/{player['max_hp']} | 🛡️ ES: {player['energy_shield']}/{player['max_energy_shield']} | 💧 Mana: {player['current_mana']}/{player['max_mana']}\n\n" # ES должен быть полным
        f"Выберите действие:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# --- Боевой цикл (handle_combat_action) ---
@router.callback_query(CombatStates.fighting, F.data.startswith("fight_action:"))
async def handle_combat_action(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer() # Сразу отвечаем на коллбэк
    user_id = callback.from_user.id

    # Получаем эффективные статы и состояние боя
    player = await get_player_effective_stats(user_id)
    state_data = await state.get_data()

    # Получаем данные монстра ИЗ СОСТОЯНИЯ (скейленные)
    monster_key = state_data.get("monster_key")
    current_monster_hp = state_data.get("monster_hp")
    monster_max_hp = state_data.get("monster_max_hp")
    monster_damage = state_data.get("monster_damage")
    monster_xp_reward = state_data.get("monster_xp_reward")
    monster_gold_reward = state_data.get("monster_gold_reward")

    # Проверка полноты данных из состояния
    if (not player or not monster_key or current_monster_hp is None or
            monster_max_hp is None or monster_damage is None or
            monster_xp_reward is None or monster_gold_reward is None):
        logging.error(f"Incomplete combat state for user {user_id}. Data: {state_data}")
        try:
            await callback.message.edit_text("Ошибка состояния боя. Бой прерван.")
        except Exception: pass # Игнорируем ошибки редактирования старого сообщения
        await state.clear()
        return

    # Разбираем действие игрока из callback_data
    action_data = callback.data.split(":")
    action_type = action_data[1]

    if action_type == "no_mana":
        # Можно ничего не делать или дать короткий ответ без алерта
        # await callback.answer("Недостаточно маны!")
        return

    # --- Переменные для хода игрока ---
    player_damage_dealt = 0
    mana_cost = 0
    action_log = ""
    is_crit = False
    healed_amount = 0
    applied_buffs = {} # Баффы, примененные В ЭТОМ ХОДЕ

    # Получаем активные эффекты от предметов
    active_effects = player.get('active_effects', {})
    try: mana_multiplier = float(active_effects.get('mana_cost_multiplier', 1.0)); mana_multiplier = max(0, mana_multiplier)
    except (ValueError, TypeError): mana_multiplier = 1.0
    try: crit_mult_bonus = float(active_effects.get('crit_multiplier_bonus', 0))
    except (ValueError, TypeError): crit_mult_bonus = 0

    # --- Логика действия игрока ---
    if action_type == "attack":
        # Получаем бафф атаки из состояния FSM (если он есть)
        current_buffs = state_data.get("player_buffs", {}) # Получаем баффы С ПРОШЛОГО ХОДА
        attack_multiplier = current_buffs.get("buff_next_attack", 1.0)
        # Считаем урон атаки
        base_attack_damage, is_crit = calculate_player_attack_damage(
            player['strength'], player['crit_chance'], player['crit_damage'] + crit_mult_bonus
        )
        player_damage_dealt, is_crit = calculate_player_attack_damage(
            player['strength'], player['crit_chance'], player['crit_damage'] + crit_mult_bonus
        )
        # Формируем лог
        crit_text = "💥 <b>КРИТ!</b> " if is_crit else ""
        buff_text = f"(x{attack_multiplier:.1f}!) " if attack_multiplier > 1.0 else ""
        action_log = f"Вы атаковали 🗡️ {buff_text}{crit_text}и нанесли {player_damage_dealt} урона."
        # Сбрасываем бафф атаки, так как он использован
        if "buff_next_attack" in current_buffs:
             del current_buffs["buff_next_attack"]
             # Сразу обновляем баффы в состоянии, чтобы бафф не применился снова, если бой закончится на этом ходу
             await state.update_data(player_buffs=current_buffs)
             logging.debug(f"Buff 'buff_next_attack' consumed for user {user_id}")


    else: # Заклинание (action_type = spell_id)
        spell_id = action_type
        spell_data = SPELLS.get(spell_id)

        if not spell_data:
             logging.warning(f"Spell NOT FOUND for action '{action_type}' by user {user_id}.")
             await callback.answer("Ошибка: заклинание не найдено.", show_alert=True)
             return

        # Расчет стоимости маны
        try:
            base_mana_cost = int(spell_data['mana_cost'])
            actual_mana_cost = math.ceil(base_mana_cost * mana_multiplier)
        except Exception as e:
            logging.error(f"Error calculating mana cost for spell '{spell_name}': {e}")
            actual_mana_cost = 99999

        # Проверка маны
        if player['current_mana'] >= actual_mana_cost:
            mana_cost = actual_mana_cost # Запоминаем затраты маны
            spell_name = spell_data['name']
            spell_target = spell_data.get('target', 'enemy')
            effect_type = spell_data.get('effect_type')
            effect_value = spell_data.get('effect_value')
            duration = spell_data.get('duration', 0)
            cost_text = f" ({mana_cost} М)"
            action_log = f"Вы использовали ✨ {hd.quote(spell_name)}{cost_text}"
            
        if spell_data and player['current_mana'] >= actual_mana_cost:
            # Обработка эффектов заклинания
            if effect_type == "damage":
                base_damage = effect_value
                final_base_damage = calculate_final_spell_damage(base_damage, player['intelligence'])
                # Расчет крита для спелла (используем заглушку calculate_spell_damage, так как она берет словарь)
                damage_dict_for_calc = {'damage': final_base_damage} # Оборачиваем в словарь
                player_damage_dealt, is_crit = calculate_damage_with_crit(
                    final_base_damage, # Передаем урон С УЧЕТОМ ИНТЕЛЛЕКТА
                    player['crit_chance'],
                    player['crit_damage'] + crit_mult_bonus
                )# Передаем множитель крита С УЧЕТОМ БОНУСОВ
                crit_text = "💥 <b>КРИТ!</b> " if is_crit else ""
                action_log += f", {crit_text}нанеся {player_damage_dealt} урона {spell_target}."

            elif effect_type == "heal_percent":
                percent = effect_value
                heal_calc = math.ceil(player['max_hp'] * (percent / 100.0))
                heal_actual = min(heal_calc, player['max_hp'] - player['current_hp'])
                healed_amount = heal_actual
                action_log += f", восстановив {healed_amount} здоровья."

            elif effect_type == "buff_next_attack":
                # Сохраняем бафф для СЛЕДУЮЩЕГО хода
                applied_buffs["buff_next_attack"] = effect_value
                action_log += f", усилив следующую атаку (x{effect_value:.1f})."

            elif effect_type == "temp_buff":
                 if isinstance(effect_value, dict) and duration > 0:
                     buff_log_parts = []
                     for stat_name, buff_val in effect_value.items():
                         # Добавляем временный бафф в словарь applied_buffs
                         applied_buffs[f"temp_{stat_name}"] = {'value': buff_val, 'duration': duration}
                         buff_log_parts.append(f"+{buff_val} {stat_name}")
                     if buff_log_parts:
                          action_log += f", временно усилив {', '.join(buff_log_parts)} на {duration} хода."
                          logging.info(f"Applied temp_buff for {duration} turns: {effect_value}")
                     else:
                          action_log += ", но бафф не сработал (ошибка данных)."
                 else:
                      action_log += ", но бафф не сработал (неверные данные)."

            # TODO: Добавить обработку "heal_over_time", "summon"
            else:
                 logging.warning(f"Unknown spell effect type: {effect_type} for spell {spell_id}")
                 action_log += ", но ничего не произошло (неизвестный эффект)."

        else: # Не хватает маны
            await callback.answer("Недостаточно маны!", show_alert=True)
            return # Выход из обработчика, ход не состоялся

    # --- Применяем изменения HP/Mana игрока (включая хил) ---
    logging.debug(f"[handle_combat_action] Before player vitals update: HP change={healed_amount}, Mana change={-mana_cost}")
    # Вызываем update_player_vitals ТОЛЬКО для изменения маны/хила игрока, НЕ для урона монстра
    # Урон монстра будет применен позже отдельным вызовом
    await update_player_vitals(user_id, hp_change=healed_amount, mana_change=-mana_cost)
    logging.debug(f"[handle_combat_action] After player vitals update.")

    # --- Обновляем баффы в состоянии FSM ---
    current_buffs = state_data.get("player_buffs", {}) # Получаем баффы с прошлого хода (могли измениться после атаки)
    next_turn_buffs = {}
    buffs_expired_log = []
    # Уменьшаем длительность старых баффов
    for buff_key, buff_data in current_buffs.items():
        if isinstance(buff_data, dict) and 'duration' in buff_data:
            remaining_duration = buff_data['duration'] - 1
            if remaining_duration > 0:
                next_turn_buffs[buff_key] = {'value': buff_data['value'], 'duration': remaining_duration}
            else:
                buffs_expired_log.append(buff_key.replace('temp_', ''))
        # else: баффы без длительности (например, buff_next_attack, если не был потрачен) переносим как есть? Или он уже удален? Лучше не переносить то, что не имеет duration.

    if buffs_expired_log:
         logging.info(f"Buffs expired for user {user_id}: {', '.join(buffs_expired_log)}")
         # action_log += f"\n<i>(Истек срок: {', '.join(buffs_expired_log)})</i>" # Можно добавить в лог боя

    # Добавляем/обновляем баффы, примененные В ЭТОМ ХОДЕ
    next_turn_buffs.update(applied_buffs)
    await state.update_data(player_buffs=next_turn_buffs) # Сохраняем баффы для следующего хода
    logging.debug(f"Player {user_id} buffs updated in state for next turn: {next_turn_buffs}")


    # --- Обновление HP монстра (если был урон) ---
    new_monster_hp = current_monster_hp
    if player_damage_dealt > 0:
        new_monster_hp = max(0, current_monster_hp - player_damage_dealt) # Не уходим в минус
        await state.update_data(monster_hp=new_monster_hp)
        logging.debug(f"Monster HP updated: {new_monster_hp}/{monster_max_hp}")

    # --- Проверка победы игрока ---
    # Проверяем ПОСЛЕ обновления баффов, но ДО хода монстра
    if new_monster_hp <= 0:
        logging.info(f"Player {user_id} defeated monster {monster_key}.")
        xp_gain = monster_xp_reward
        gold_gain = monster_gold_reward
        # Применяем эффект утроения золота
        try: triple_gold_chance = float(active_effects.get('triple_gold_chance', 0))
        except (ValueError, TypeError): triple_gold_chance = 0
        if random.uniform(0, 100) < triple_gold_chance:
             gold_gain *= 3
             logging.info(f"Triple gold proc! Gold: {gold_gain}")
             loot_log = f"💰 Вы получаете <b>УТРОЕННОЕ</b> золото: {gold_gain}!\n"
        else:
             loot_log = f"💰 Получено {gold_gain} золота.\n"

        # Дроп предмета
        dropped_item_id = get_random_loot_item_id()
        item_drop_log = ""
        if dropped_item_id:
             item_info = ALL_ITEMS.get(dropped_item_id)
             if item_info:
                 added_to_inv = await add_item_to_inventory(user_id, dropped_item_id)
                 item_drop_log = f"🎁 Вы нашли: <b>{hd.quote(item_info['name'])}</b>!\n" if added_to_inv else "🎁 Ошибка добавления лута!\n"
             else: logging.error(f"Loot function returned non-existent item_id: {dropped_item_id}")

        # Обновление XP/Золота
        xp_update_result, leveled_up = await update_player_xp(user_id, gained_xp=xp_gain, gained_gold=gold_gain)

        # Обновление квеста
        quest_update = await update_quest_progress(user_id, monster_key)
        quest_log = ""
        if quest_update:
            if quest_update['completed']:
                quest_log = (f"📜 <b>Задание выполнено!</b> (+{quest_update['gold_reward']}💰, +{quest_update['xp_reward']} XP)\n")
                await update_player_xp(user_id, gained_xp=quest_update['xp_reward'], gained_gold=quest_update['gold_reward'])
                await clear_daily_quest(user_id)
            else:
                 quest_log = f"📜 Прогресс: {quest_update['current_count']}/{quest_update['target_count']} {hd.quote(monster_key)}.\n"

        # Сообщение о левел-апе
        level_up_log = ""
        if leveled_up and xp_update_result:
             level_up_log = (f"🎉 <b>УРОВЕНЬ {xp_update_result['level']}!</b> (+{xp_update_result['gained_stat_points']} очка) 🎉\n")

        # Восстановление ES после победы
        player_after_fight = await get_player_effective_stats(user_id)
        if player_after_fight and player_after_fight['energy_shield'] < player_after_fight['max_energy_shield']:
             await update_player_vitals(user_id, set_es=player_after_fight['max_energy_shield'])
             logging.info(f"Player {user_id} ES restored after victory.")

        # Завершаем бой и регеним HP/Mana
        await state.clear()
        await check_and_apply_regen(user_id, None)

        result_text = (f"{action_log}\n\n"
                       f"<b>Победа над {hd.quote(monster_key)}!</b> 💪\n"
                       f"✨ +{xp_gain} опыта.\n"
                       f"{loot_log}{item_drop_log}{quest_log}{level_up_log}")
        try: await callback.message.edit_text(result_text, parse_mode="HTML")
        except Exception as e: await callback.message.answer(result_text, parse_mode="HTML")
        return # <<< ВАЖНО: Выход после победы

    # --- Логика хода монстра ---
    monster_raw_damage = monster_damage
    dodge_chance = calculate_dodge_chance(player['dexterity'])
    # Получаем баффы для ЭТОГО хода (которые действуют СЕЙЧАС)
    current_turn_buffs = next_turn_buffs # Баффы, сохраненные после хода игрока
    player_armor = player['armor'] + current_turn_buffs.get('temp_armor', {}).get('value', 0)
    player_damage_reduction = calculate_damage_reduction(player_armor)

    # !!! ИНИЦИАЛИЗИРУЕМ player_hp_loss ЗДЕСЬ !!!
    player_hp_loss = 0
    monster_action_log = ""

    if random.uniform(0, 100) < dodge_chance:
        monster_action_log = f"{hd.quote(monster_key)} атаковал, но вы увернулись! 💨"
    else:
        actual_damage = max(1, monster_raw_damage - player_damage_reduction)
        player_hp_loss = actual_damage # Устанавливаем урон, который получит игрок
        reduction_text = f" (-{player_damage_reduction} броня{'🛡️' if current_turn_buffs.get('temp_armor') else ''})" if player_damage_reduction > 0 else "" # Эмодзи, если есть бафф брони
        monster_action_log = f"{hd.quote(monster_key)} атаковал 👹 и нанес вам <b>{actual_damage}</b> урона{reduction_text}."

    # --- Обновляем виталы игрока ПОСЛЕ хода монстра ---
    # Передаем только урон от монстра (hp_change будет < 0)
    logging.info(f"[handle_combat_action CALLING_VITALS for monster attack] User {user_id}: hp_change={-player_hp_loss}")
    new_hp, new_mana, new_es = await update_player_vitals(user_id, hp_change=-player_hp_loss) # Ману и ES не меняем здесь
    logging.info(f"[handle_combat_action VITALS_RETURNED after monster] User {user_id}: NewHP={new_hp}, NewMana={new_mana}, NewES={new_es}")

    # --- Проверка поражения игрока ---
    if new_hp <= 0:
        logging.info(f"Player {user_id} was defeated by {monster_key}.")
        xp_penalty, gold_penalty = await apply_death_penalty(user_id)
        penalty_log = f"☠️ Вы теряете {xp_penalty} опыта и {gold_penalty} золота."
        # Восстанавливаем ES после поражения
        player_after_death = await get_player_effective_stats(user_id)
        if player_after_death:
             await update_player_vitals(user_id, set_es=player_after_death['max_energy_shield'])
             logging.info(f"Player {user_id} ES restored after defeat.")

        await state.clear()
        await check_and_apply_regen(user_id, None)

        result_text = (f"{action_log}\n{monster_action_log}\n\n"
                       f"<b>Вы были повержены {hd.quote(monster_key)}...</b> 💀\n"
                       f"{penalty_log}\nВы потеряли сознание.")
        try: await callback.message.edit_text(result_text, parse_mode="HTML")
        except Exception as e: await callback.message.answer(result_text, parse_mode="HTML")
        return # <<< ВАЖНО: Выход после поражения

    # --- Бой продолжается ---
    updated_player = await get_player_effective_stats(user_id) # Получаем актуальные статы
    if not updated_player: # Проверка
         await callback.message.edit_text("Ошибка получения данных игрока. Бой прерван.")
         await state.clear()
         return

    # Генерируем клавиатуру для СЛЕДУЮЩЕГО хода игрока
    keyboard = await get_combat_action_keyboard(user_id, monster_key, updated_player['current_mana'], updated_player.get('active_effects', {}))

    # Собираем информацию о действующих баффах для отображения
    active_buff_texts = []
    for buff_key, buff_data in next_turn_buffs.items(): # Используем баффы, сохраненные для следующего хода
         if isinstance(buff_data, dict) and 'duration' in buff_data:
              stat_name = buff_key.replace('temp_', '')
              active_buff_texts.append(f"{stat_name.capitalize()} (+{buff_data['value']}) [{buff_data['duration']} ход]")
         elif buff_key == "buff_next_attack":
              active_buff_texts.append(f"Усиление атаки (x{buff_data:.1f})")
    buff_display = " / ".join(active_buff_texts)
    buff_line = f"\n<i>Активные эффекты: {buff_display}</i>" if buff_display else ""


    result_text = (
        f"{action_log}\n{monster_action_log}\n\n"
        f"<b>{hd.quote(monster_key)}</b> все еще жив!\n"
        f"❤️ HP Монстра: {new_monster_hp}/{monster_max_hp}\n\n"
        f"Ваши статы:\n"
        f"❤️ HP: {updated_player['current_hp']}/{updated_player['max_hp']} | 🛡️ ES: {updated_player['energy_shield']}/{updated_player['max_energy_shield']} | 💧 Mana: {updated_player['current_mana']}/{updated_player['max_mana']}"
        f"{buff_line}\n\n" # Добавляем строку с баффами
        f"Выберите следующее действие:"
    )
    try:
        await callback.message.edit_text(result_text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest as e:
         if "message is not modified" in str(e): logging.debug("Combat message not modified.")
         else:
             logging.error(f"Error editing combat message: {e}")
             await callback.message.answer("Произошла ошибка отображения боя. Бой прерван.")
             await state.clear()
    except Exception as e:
        logging.error(f"Error editing combat message: {e}")
        await callback.message.answer("Произошла ошибка отображения боя. Бой прерван.")
        await state.clear()
        
# Обработчик для случая, если игрок нажал кнопку действия вне состояния боя
@router.callback_query(F.data.startswith("fight_action:"))
async def handle_combat_action_outside_state(callback: types.CallbackQuery):
    await callback.answer("Этот бой уже завершен или неактивен.", show_alert=True)
    try:
        # Просто убираем кнопки, не меняя текст сильно
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        logging.warning(f"Could not edit old combat message markup: {e}")
