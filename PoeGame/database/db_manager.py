# database/db_manager.py
import aiosqlite
import logging
import time
import math
from config import DB_NAME
# Добавляем импорт данных, включая BOSSES и эффекты
from game_data import (
    BASE_STATS, ALL_ITEMS, ALL_SLOTS, ITEM_SLOTS, ITEM_TYPE_RING,
    BOSSES, SPELLS,
    # Добавляем новые константы
    SHOP_WEAPON_ITEMS, SHOP_ARMOR_ITEMS, SHOP_REFRESH_INTERVAL,
    ITEM_TYPE_WEAPON, ITEM_TYPE_HELMET, ITEM_TYPE_CHEST, ITEM_TYPE_GLOVES, ITEM_TYPE_BOOTS,
    BLACKSMITH_ITEMS_COUNT, BLACKSMITH_REFRESH_INTERVAL, BLACKSMITH_CRAFT_COST,
    ITEM_TYPE_FRAGMENT # Нужен для кузнеца
)
import json # Для хранения списков ID в БД

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - [%(filename)s:%(lineno)d] - %(message)s")

# --- Инициализация/Обновление БД ---
async def init_db():
    """Инициализирует БД, создает/обновляет все таблицы."""
    # Отступ 0 - Начало функции
    # Отступ 4 - Начало блока async with
    async with aiosqlite.connect(DB_NAME) as db:
        # Отступ 8 - Начало работы с таблицей players
        # --- Таблица players ---
        cursor = await db.execute("PRAGMA table_info(players)")
        player_columns = {col[1]: col[2] for col in await cursor.fetchall()}

        if 'user_id' not in player_columns:
             # Отступ 12 - Создание таблицы players
             await db.execute('''
                 CREATE TABLE players (
                     user_id INTEGER PRIMARY KEY, username TEXT, class TEXT,
                     level INTEGER DEFAULT 1, xp INTEGER DEFAULT 0, xp_to_next_level INTEGER DEFAULT 100,
                     max_hp INTEGER, current_hp INTEGER, max_mana INTEGER, current_mana INTEGER,
                     strength INTEGER, dexterity INTEGER, intelligence INTEGER, gold INTEGER DEFAULT 0,
                     armor INTEGER DEFAULT 0, max_energy_shield INTEGER DEFAULT 0, energy_shield INTEGER DEFAULT 0,
                     crit_chance REAL DEFAULT 5.0, crit_damage REAL DEFAULT 150.0,
                     last_daily_reward_time INTEGER DEFAULT 0,
                     quest_monster_key TEXT DEFAULT NULL, quest_target_count INTEGER DEFAULT 0,
                     quest_current_count INTEGER DEFAULT 0, quest_gold_reward INTEGER DEFAULT 0,
                     quest_xp_reward INTEGER DEFAULT 0, last_quest_time INTEGER DEFAULT 0,
                     stat_points INTEGER DEFAULT 0,
                     last_hp_regen_time INTEGER DEFAULT 0,
                     last_mana_regen_time INTEGER DEFAULT 0,
                     highest_unlocked_boss_index INTEGER DEFAULT 0
                 )
             ''')
             logging.info("Created 'players' table.")
             cursor = await db.execute("PRAGMA table_info(players)")
             player_columns = {col[1]: col[2] for col in await cursor.fetchall()}

        # Отступ 8 - Вложенная функция для players
        async def add_player_column_if_not_exists(col_name, col_type_with_default):
             # Отступ 12
             if col_name not in player_columns:
                 # Отступ 16
                 try:
                     await db.execute(f"ALTER TABLE players ADD COLUMN {col_name} {col_type_with_default}")
                     logging.info(f"Added column '{col_name}' to 'players' table.")
                 except aiosqlite.OperationalError as e:
                     if "duplicate column name" not in str(e).lower(): logging.warning(f"Could not add column '{col_name}' to players: {e}")
                     else: logging.debug(f"Column '{col_name}' already exists in players.")

        # Отступ 8 - Проверка/добавление колонок players
        await add_player_column_if_not_exists('armor', 'INTEGER DEFAULT 0')
        await add_player_column_if_not_exists('max_energy_shield', 'INTEGER DEFAULT 0')
        # ... (все остальные проверки для players) ...
        await add_player_column_if_not_exists('highest_unlocked_boss_index', 'INTEGER DEFAULT 0')

        # --- !!! ВСЕ ОСТАЛЬНЫЕ ТАБЛИЦЫ ИДУТ ДАЛЬШЕ, ВНУТРИ async with !!! ---

        # Отступ 8 - Начало работы с таблицей player_spells
        # --- Таблица player_spells ---
        cursor = await db.execute("PRAGMA table_info(player_spells)")
        spell_columns = {col[1]: col[2] for col in await cursor.fetchall()}
        if 'learned_id' not in spell_columns:
            # Отступ 12
            await db.execute('''
                CREATE TABLE player_spells (
                    learned_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id INTEGER NOT NULL,
                    spell_id TEXT NOT NULL,
                    FOREIGN KEY (player_id) REFERENCES players (user_id) ON DELETE CASCADE,
                    UNIQUE (player_id, spell_id)
                )
            ''')
            await db.execute("CREATE INDEX IF NOT EXISTS idx_spells_player ON player_spells (player_id)")
            logging.info("Created 'player_spells' table and index.")
        # else: можно добавить проверки колонок

        # Отступ 8 - Начало работы с таблицей inventory
        # --- Таблица inventory ---
        cursor = await db.execute("PRAGMA table_info(inventory)") # <-- Строка с ошибкой теперь здесь
        inventory_columns = {col[1]: col[2] for col in await cursor.fetchall()}

        # Отступ 8
        if 'inventory_id' not in inventory_columns:
            # Отступ 12
            await db.execute('''
                CREATE TABLE inventory (
                    inventory_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id INTEGER NOT NULL,
                    item_id TEXT NOT NULL,
                    is_equipped BOOLEAN DEFAULT FALSE,
                    equipped_slot TEXT DEFAULT NULL,
                    FOREIGN KEY (player_id) REFERENCES players (user_id) ON DELETE CASCADE
                )
            ''')
            await db.execute("CREATE INDEX IF NOT EXISTS idx_inventory_player ON inventory (player_id)")
            logging.info("Created 'inventory' table and index.")
            cursor = await db.execute("PRAGMA table_info(inventory)")
            inventory_columns = {col[1]: col[2] for col in await cursor.fetchall()}

        # Отступ 8 - Вложенная функция для inventory
        async def add_inventory_column_if_not_exists(col_name, col_type_with_default):
             # Отступ 12
             if col_name not in inventory_columns:
                 # Отступ 16
                 try:
                     await db.execute(f"ALTER TABLE inventory ADD COLUMN {col_name} {col_type_with_default}")
                     logging.info(f"Added column '{col_name}' to 'inventory' table.")
                 except aiosqlite.OperationalError as e:
                      if "duplicate column name" not in str(e).lower(): logging.warning(f"Could not add column '{col_name}' to inventory: {e}")
                      else: logging.debug(f"Column '{col_name}' already exists in inventory.")

        # Отступ 8 - Вызовы для inventory
        await add_inventory_column_if_not_exists('is_equipped', 'BOOLEAN DEFAULT FALSE')
        await add_inventory_column_if_not_exists('equipped_slot', 'TEXT DEFAULT NULL')

        # Отступ 8 - Начало работы с таблицей shop_state
        # --- Таблица shop_state ---
        cursor = await db.execute("PRAGMA table_info(shop_state)")
        shop_columns = {col[1]: col[2] for col in await cursor.fetchall()}
        if 'shop_type' not in shop_columns:
            # Отступ 12
            await db.execute('''
                CREATE TABLE shop_state (
                    shop_type TEXT PRIMARY KEY,
                    last_refresh_time INTEGER DEFAULT 0,
                    item_ids TEXT DEFAULT '[]'
                )
            ''')
            await db.execute("INSERT OR IGNORE INTO shop_state (shop_type) VALUES (?)", ('weapon_shop',))
            await db.execute("INSERT OR IGNORE INTO shop_state (shop_type) VALUES (?)", ('armor_shop',))
            logging.info("Created 'shop_state' table and initial records.")
        # else: можно добавить проверки колонок

        # Отступ 8 - Начало работы с таблицей blacksmith_state
        # --- Таблица blacksmith_state ---
        cursor = await db.execute("PRAGMA table_info(blacksmith_state)")
        blacksmith_columns = {col[1]: col[2] for col in await cursor.fetchall()}
        if 'state_id' not in blacksmith_columns:
            # Отступ 12
            await db.execute('''
                CREATE TABLE blacksmith_state (
                    state_id INTEGER PRIMARY KEY DEFAULT 1,
                    last_refresh_time INTEGER DEFAULT 0,
                    legendary_ids TEXT DEFAULT '[]'
                )
            ''')
            await db.execute("INSERT OR IGNORE INTO blacksmith_state (state_id) VALUES (1)")
            logging.info("Created 'blacksmith_state' table and initial record.")
        # else: можно добавить проверки колонок

        # Отступ 8 - Начало работы с таблицей boss_cooldowns
        # --- Таблица boss_cooldowns ---
        cursor = await db.execute("PRAGMA table_info(boss_cooldowns)")
        cooldown_columns = {col[1]: col[2] for col in await cursor.fetchall()}

        # Отступ 8
        if 'cooldown_id' not in cooldown_columns:
            # Отступ 12
            await db.execute('''
                    CREATE TABLE boss_cooldowns (
                    cooldown_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id INTEGER NOT NULL,
                    boss_id TEXT NOT NULL,
                    last_kill_time INTEGER DEFAULT 0,
                    FOREIGN KEY (player_id) REFERENCES players (user_id) ON DELETE CASCADE,
                    UNIQUE (player_id, boss_id)
                )
            ''')
            await db.execute("CREATE INDEX IF NOT EXISTS idx_cooldown_player_boss ON boss_cooldowns (player_id, boss_id)")
            logging.info("Created 'boss_cooldowns' table and index.")
        # else: можно добавить проверки колонок

        # --- !!! ЕДИНСТВЕННЫЙ COMMIT В КОНЦЕ БЛОКА 'async with' !!! ---
        # Отступ 8
        await db.commit()

    # --- !!! ЕДИНСТВЕННЫЙ ЛОГ ПОСЛЕ ЗАВЕРШЕНИЯ РАБОТЫ С БД !!! ---
    # Отступ 4 - СНАРУЖИ блока async with
    logging.info("Database initialized/updated (players, player_spells, inventory, shop_state, blacksmith_state, boss_cooldowns).")

# --- Получение Базовых Данных Игрока ---
async def get_player(user_id: int):
    """Получает RAW данные игрока из таблицы players."""
    # ... (это начало следующей функции, дальше код как был) ...
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM players WHERE user_id = ?", (user_id,)) as cursor:
            player_data = await cursor.fetchone()
            return player_data

async def delete_item_from_inventory(inventory_id: int) -> bool:
    """Удаляет предмет из инвентаря по его inventory_id."""
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            cursor = await db.execute("DELETE FROM inventory WHERE inventory_id = ?", (inventory_id,))
            # Проверяем, была ли удалена ровно одна строка
            if cursor.rowcount == 1:
                await db.commit()
                logging.info(f"Successfully deleted item with inventory_id: {inventory_id}")
                return True
            else:
                # Если удалено 0 строк (предмет не найден) или >1 (что невозможно с PK)
                logging.warning(f"Attempted to delete item inv_id:{inventory_id}, but rowcount was {cursor.rowcount}.")
                # Откатывать нечего, т.к. ничего не удалено
                return False
        except Exception as e:
            logging.error(f"Failed to delete item inv_id:{inventory_id} from inventory: {e}", exc_info=True)
            return False
# --- Инвентарь и Экипировка ---
async def add_item_to_inventory(player_id: int, item_id: str):
    """Добавляет предмет в инвентарь игрока."""
    if item_id not in ALL_ITEMS:
        logging.error(f"Attempted to add non-existent item_id '{item_id}' to inventory for player {player_id}.")
        return False
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            await db.execute(
                "INSERT INTO inventory (player_id, item_id) VALUES (?, ?)",
                (player_id, item_id)
            )
            await db.commit()
            logging.info(f"Added item '{item_id}' ({ALL_ITEMS[item_id]['name']}) to inventory for player {player_id}.")
            return True
        except Exception as e:
            logging.error(f"Failed to add item to inventory for player {player_id}, item {item_id}: {e}", exc_info=True)
            return False

async def get_inventory_items(player_id: int, equipped: bool | None = None) -> list[dict]:
    """
    Получает список предметов в инвентаре игрока.
    Можно фильтровать по equipped (True - только надетые, False - только не надетые, None - все).
    Возвращает список словарей, где каждый словарь - данные из inventory + данные из ALL_ITEMS.
    """
    items = []
    sql = "SELECT * FROM inventory WHERE player_id = ?"
    params = [player_id]
    if equipped is not None:
        sql += " AND is_equipped = ?"
        params.append(equipped)

    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row # Получаем как объекты Row
        async with db.execute(sql, params) as cursor:
            inventory_rows = await cursor.fetchall()
            for row in inventory_rows:
                item_details = ALL_ITEMS.get(row['item_id'])
                if item_details:
                    # Собираем полный словарь
                    item_data = dict(row) # Преобразуем Row в dict
                    item_data.update(item_details) # Добавляем данные из ALL_ITEMS
                    items.append(item_data)
                else:
                    logging.warning(f"Item with id '{row['item_id']}' found in inventory for player {player_id}, but not in ALL_ITEMS.")
    return items

async def get_item_from_inventory(inventory_id: int) -> dict | None:
     """Получает данные одного конкретного предмета из инвентаря по его inventory_id."""
     async with aiosqlite.connect(DB_NAME) as db:
         db.row_factory = aiosqlite.Row
         async with db.execute("SELECT * FROM inventory WHERE inventory_id = ?", (inventory_id,)) as cursor:
             row = await cursor.fetchone()
             if row:
                 item_details = ALL_ITEMS.get(row['item_id'])
                 if item_details:
                     item_data = dict(row)
                     item_data.update(item_details)
                     return item_data
                 else:
                     logging.warning(f"Item details for item_id '{row['item_id']}' (inventory_id {inventory_id}) not found in ALL_ITEMS.")
             return None # Если запись inventory_id не найдена


async def equip_item(player_id: int, inventory_id: int, target_slot: str) -> tuple[bool, str]:
    """
    Надевает предмет из инвентаря в указанный слот.
    Снимает предмет, который был в этом слоте ранее.
    Возвращает (True, "Сообщение об успехе") или (False, "Сообщение об ошибке").
    """
    item_to_equip = await get_item_from_inventory(inventory_id)

    # Проверки
    if not item_to_equip:
        return False, "Предмет не найден в вашем инвентаре."
    if item_to_equip['player_id'] != player_id:
        return False, "Это не ваш предмет!"
    if item_to_equip['is_equipped']:
        return False, f"Предмет '{item_to_equip['name']}' уже надет (в слоте {item_to_equip['equipped_slot']})."

    item_type = item_to_equip['type']
    allowed_slots = ITEM_SLOTS.get(item_type, [])

    if target_slot not in allowed_slots:
        return False, f"Предмет '{item_to_equip['name']}' ({item_type}) нельзя надеть в слот '{target_slot}'."

    async with aiosqlite.connect(DB_NAME) as db:
        try:
            # --- Сначала снимаем предмет, который УЖЕ в целевом слоте ---
            cursor = await db.execute(
                "UPDATE inventory SET is_equipped = FALSE, equipped_slot = NULL WHERE player_id = ? AND equipped_slot = ?",
                (player_id, target_slot)
            )
            unquipped_count = cursor.rowcount
            if unquipped_count > 0:
                 logging.info(f"Player {player_id} unequipped item(s) from slot {target_slot} before equipping new one.")
            # Если это слот кольца, а мы надеваем кольцо, нужно проверить и второй слот кольца, если целевой был занят другим кольцом
            # (Простая логика: снимаем все из слота, потом надеваем новое)

            # --- Теперь надеваем новый предмет ---
            await db.execute(
                "UPDATE inventory SET is_equipped = TRUE, equipped_slot = ? WHERE inventory_id = ?",
                (target_slot, inventory_id)
            )
            await db.commit()
            logging.info(f"Player {player_id} equipped item inv_id:{inventory_id} ('{item_to_equip['name']}') into slot '{target_slot}'.")
            return True, f"Предмет '{item_to_equip['name']}' успешно надет в слот {target_slot}."

        except Exception as e:
            logging.error(f"Failed to equip item for player {player_id}, inv_id {inventory_id}, slot {target_slot}: {e}", exc_info=True)
            return False, "Произошла ошибка при надевании предмета."


async def unequip_item(player_id: int, inventory_id: int) -> tuple[bool, str]:
     """Снимает надетый предмет."""
     item_to_unequip = await get_item_from_inventory(inventory_id)

     if not item_to_unequip:
        return False, "Предмет не найден в вашем инвентаре."
     if item_to_unequip['player_id'] != player_id:
        return False, "Это не ваш предмет!"
     if not item_to_unequip['is_equipped']:
        return False, f"Предмет '{item_to_unequip['name']}' не надет."

     slot = item_to_unequip['equipped_slot']

     async with aiosqlite.connect(DB_NAME) as db:
         try:
             await db.execute(
                 "UPDATE inventory SET is_equipped = FALSE, equipped_slot = NULL WHERE inventory_id = ?",
                 (inventory_id,)
             )
             await db.commit()
             logging.info(f"Player {player_id} unequipped item inv_id:{inventory_id} ('{item_to_unequip['name']}') from slot '{slot}'.")
             return True, f"Предмет '{item_to_unequip['name']}' снят со слота {slot}."
         except Exception as e:
            logging.error(f"Failed to unequip item for player {player_id}, inv_id {inventory_id}: {e}", exc_info=True)
            return False, "Произошла ошибка при снятии предмета."


# --- Расчет Эффективных Статов ---
async def get_player_effective_stats(user_id: int) -> dict | None:
    """
    Рассчитывает и возвращает ПОЛНЫЕ статы игрока и активные эффекты,
    учитывая базу, уровень, прокачку статов и НАДЕТЫЕ предметы (включая легендарки).
    """
    player_base = await get_player(user_id)
    if not player_base: return None

    effective_stats = dict(player_base)
    active_effects = {}

    # Шаг 1: База + Уровень + Прокачка
    base_class_stats = BASE_STATS.get(player_base['class'], BASE_STATS['Scion'])
    level = player_base['level']
    hp_gain_per_level = 10
    mana_gain_per_level = 5
    effective_stats['max_hp'] = base_class_stats['hp'] + int(effective_stats['strength'] * 0.5) + (level * hp_gain_per_level)
    effective_stats['max_mana'] = base_class_stats['mana'] + effective_stats['intelligence'] + (level * mana_gain_per_level)
    effective_stats['armor'] = 0
    effective_stats['max_energy_shield'] = 0
    # Сбрасываем криты до базовых перед добавлением бонусов
    effective_stats['crit_chance'] = 5.0
    effective_stats['crit_damage'] = 150.0

    # Шаг 2: Добавляем статы и ЭФФЕКТЫ от экипированных предметов
    equipped_items = await get_inventory_items(user_id, equipped=True)
    logging.debug(f"Calculating effective stats for {user_id}. Found {len(equipped_items)} items.")

    for item in equipped_items:
        item_data = ALL_ITEMS.get(item['item_id'], {})
        item_stats = item_data.get('stats', {})
        for stat_name, value in item_stats.items():
            if stat_name in effective_stats:
                # Проверяем, что стат числовой перед сложением
                if isinstance(effective_stats[stat_name], (int, float)) and isinstance(value, (int, float)):
                    effective_stats[stat_name] += value
                    logging.debug(f"  + {value} {stat_name} from '{item_data.get('name', 'Unknown Item')}'")
                else:
                    logging.warning(f"Non-numeric stat addition skipped: {stat_name} (item: {item_data.get('name', '?')})")
            # else: игнорируем неизвестные статы

        item_effect = item_data.get('effect')
        if item_effect and isinstance(item_effect, dict):
            effect_type = item_effect.get('type')
            effect_value = item_effect.get('value')
            if effect_type:
                # TODO: Продумать стакание (суммировать? брать макс/мин?) Пока перезапись.
                if effect_type in active_effects:
                     logging.warning(f"Effect '{effect_type}' overwritten by item '{item_data.get('name', '?')}'. Stacking logic needed.")
                active_effects[effect_type] = effect_value
                logging.debug(f"  + EFFECT {effect_type}={effect_value} from '{item_data.get('name', 'Unknown Item')}'")

    # Шаг 3: Применение некоторых эффектов к статам
    logging.debug(f"Applying effects to stats for {user_id}. Active effects: {active_effects}")

    # Конвертация маны в ES ('mana_to_es')
    if 'mana_to_es' in active_effects:
        try:
            conversion_rate = float(active_effects['mana_to_es'])
            # Конвертируем от МАКСИМАЛЬНОЙ маны, рассчитанной на Шаге 1
            mana_for_conversion = base_class_stats['mana'] + effective_stats['intelligence'] + (level * mana_gain_per_level)
            mana_converted_to_es = int(mana_for_conversion * conversion_rate)
            # Добавляем к ES, рассчитанному от шмота
            effective_stats['max_energy_shield'] += mana_converted_to_es
            logging.info(f"  Applied 'mana_to_es' ({conversion_rate * 100}%): +{mana_converted_to_es} MaxES. New MaxES: {effective_stats['max_energy_shield']}")
            # Решаем, уменьшать ли ману. Допустим, НЕТ, это просто бонус ES на основе маны.
            # effective_stats['max_mana'] = max(0, effective_stats['max_mana'] - mana_converted_to_es)
        except (ValueError, TypeError) as e:
             logging.error(f"Error applying 'mana_to_es' effect: {e}")

    # Бонус к множителю крита ('crit_multiplier_bonus')
    if 'crit_multiplier_bonus' in active_effects:
         try:
             bonus = float(active_effects['crit_multiplier_bonus'])
             # Добавляем к базовому множителю крита
             effective_stats['crit_damage'] += bonus
             logging.info(f"  Applied 'crit_multiplier_bonus': +{bonus}%. New CritDamage: {effective_stats['crit_damage']}%")
         except (ValueError, TypeError) as e:
              logging.error(f"Error applying 'crit_multiplier_bonus' effect: {e}")

    # --- Другие эффекты, модифицирующие статы напрямую ---
    # (Добавлять сюда по мере необходимости)

    # Шаг 4: Коррекция текущих значений
    effective_stats['current_hp'] = min(effective_stats['current_hp'], effective_stats['max_hp'])
    effective_stats['current_mana'] = min(effective_stats['current_mana'], effective_stats['max_mana'])
    effective_stats['energy_shield'] = min(effective_stats['energy_shield'], effective_stats['max_energy_shield'])

    # Добавляем активные эффекты (которые не были применены напрямую к статам) в словарь
    effective_stats['active_effects'] = active_effects

    logging.info(f"Effective stats calculated for {user_id}. Final MaxHP: {effective_stats['max_hp']}, Final MaxES: {effective_stats['max_energy_shield']}, Effects dictionary: {active_effects}")
    return effective_stats



# --- Рейтинги ---
async def get_top_players(by: str = 'level_xp', limit: int = 10) -> list[dict]:
    """Получает топ игроков по уровню/опыту или золоту."""
    players = []
    order_by_clause = ""

    if by == 'gold':
        order_by_clause = "ORDER BY gold DESC"
    elif by == 'level_xp':
        # Сортируем сначала по уровню (убывание), потом по опыту на уровне (убывание)
        order_by_clause = "ORDER BY level DESC, xp DESC"
    else: # По умолчанию сортируем по уровню/опыту
        order_by_clause = "ORDER BY level DESC, xp DESC"

    sql = f"SELECT user_id, username, level, xp, gold FROM players {order_by_clause} LIMIT ?"

    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, (limit,)) as cursor:
            rows = await cursor.fetchall()
            players = [dict(row) for row in rows] # Преобразуем в список словарей

    return players

# --- Логика Боссов ---
async def get_player_boss_progression(user_id: int) -> int:
    """Возвращает индекс самого высокого доступного босса (0-based)."""
    player = await get_player(user_id)
    return player['highest_unlocked_boss_index'] if player else 0

async def update_player_boss_progression(user_id: int, defeated_boss_index: int):
    """Обновляет прогресс игрока, если убит самый высокий доступный босс."""
    current_max_boss = await get_player_boss_progression(user_id)
    num_bosses = len(BOSSES)

    # Обновляем, только если игрок убил босса с текущим максимальным индексом
    # и если это не последний босс
    if defeated_boss_index == current_max_boss and current_max_boss < num_bosses - 1:
        next_boss_index = current_max_boss + 1
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE players SET highest_unlocked_boss_index = ? WHERE user_id = ?", (next_boss_index, user_id))
            await db.commit()
        logging.info(f"Player {user_id} unlocked next boss (index: {next_boss_index}).")
        return next_boss_index # Возвращаем индекс нового доступного босса
    return current_max_boss # Возвращаем текущий, если прогресса не было


async def get_boss_cooldown(player_id: int, boss_id: str) -> int:
    """Возвращает время ПОСЛЕДНЕГО УБИЙСТВА босса (timestamp) или 0, если не убивал/нет записи."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT last_kill_time FROM boss_cooldowns WHERE player_id = ? AND boss_id = ?",
            (player_id, boss_id)
        ) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0

async def set_boss_cooldown(player_id: int, boss_id: str):
    """Записывает ТЕКУЩЕЕ время как время последнего убийства босса."""
    current_time = int(time.time())
    async with aiosqlite.connect(DB_NAME) as db:
        # INSERT OR REPLACE обновит запись, если она есть, или вставит новую
        await db.execute(
            """INSERT OR REPLACE INTO boss_cooldowns (player_id, boss_id, last_kill_time)
               VALUES (?, ?, ?)""",
            (player_id, boss_id, current_time)
        )
        await db.commit()
    logging.info(f"Boss cooldown set for player {player_id}, boss '{boss_id}' at {current_time}.")

# --- Получение/Добавление Игрока ---
async def get_player(user_id: int):
    """Получает данные игрока по его user_id."""
    async with aiosqlite.connect(DB_NAME) as db:
        # Устанавливаем row_factory для получения результата в виде объекта sqlite3.Row
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM players WHERE user_id = ?", (user_id,)) as cursor:
            player_data = await cursor.fetchone()
            return player_data # Возвращает объект Row или None

async def add_player(user_id: int, username: str, chosen_class: str = 'Scion'):
    """Добавляет нового игрока в базу данных и выдает стартовый спелл."""
    if chosen_class not in BASE_STATS:
        logging.warning(f"Unknown class '{chosen_class}'. Defaulting to Scion.")
        chosen_class = 'Scion'

    base = BASE_STATS[chosen_class]
    start_hp = base['hp'] + int(base['str'] * 0.5)
    start_mana = base['mana'] + base['int']
    start_crit_chance = 5.0
    start_crit_damage = 150.0
    current_time = int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:
        # Используем явную транзакцию с try/except/finally
        transaction_successful = False
        try:
            await db.execute("BEGIN") # Начинаем транзакцию

            # Вставляем нового игрока
            await db.execute('''
                INSERT INTO players (
                    user_id, username, class, level, xp, xp_to_next_level,
                    max_hp, current_hp, max_mana, current_mana, strength, dexterity,
                    intelligence, gold, armor, max_energy_shield, energy_shield,
                    crit_chance, crit_damage, last_daily_reward_time, last_quest_time,
                    stat_points, last_hp_regen_time, last_mana_regen_time,
                    highest_unlocked_boss_index
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id, username, chosen_class, 1, 0, 100, start_hp, start_hp, start_mana, start_mana,
                base['str'], base['dex'], base['int'], 0, 0, 0, 0, start_crit_chance, start_crit_damage,
                0, 0, 0, current_time, current_time, 0
            ))
            logging.info(f"Player {username} (ID: {user_id}) record inserted (in transaction).")

            # Добавляем стартовый спелл
            start_spell_id = "spell001"
            if start_spell_id in SPELLS:
                 await db.execute(
                     "INSERT OR IGNORE INTO player_spells (player_id, spell_id) VALUES (?, ?)",
                     (user_id, start_spell_id)
                 )
                 logging.info(f"Granted starting spell '{start_spell_id}' to new player {user_id} (in transaction).")
            else:
                 logging.warning(f"Starting spell '{start_spell_id}' not found in SPELLS.")

            # --- !!! ВОЗВРАЩАЕМ ЯВНЫЙ COMMIT ВНУТРИ TRY !!! ---
            await db.commit()
            transaction_successful = True # Ставим флаг, что коммит прошел
            # --- КОНЕЦ ИЗМЕНЕНИЯ ---
            logging.info(f"Transaction committed for player {user_id}.")
            return True # Возвращаем успех

        except aiosqlite.IntegrityError:
            # await db.execute("ROLLBACK") # Откат не нужен, т.к. коммита не было
            logging.info(f"Player {username} (ID: {user_id}) already exists (IntegrityError).")
            return False # Игрок уже есть
        except Exception as e:
            # await db.execute("ROLLBACK") # Откат не нужен, т.к. коммита не было
            logging.error(f"Failed to add player {user_id} during transaction: {e}", exc_info=True)
            return False # Ошибка добавления

# --- Функции для Заклинаний ---
async def get_learned_spells(player_id: int) -> list[dict]:
    """Получает список ID и данных изученных заклинаний игрока."""
    learned = []
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT spell_id FROM player_spells WHERE player_id = ?", (player_id,)) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                spell_id = row['spell_id']
                spell_data = SPELLS.get(spell_id)
                if spell_data:
                    # Добавляем ID в данные спелла для удобства
                    data_copy = spell_data.copy()
                    data_copy['id'] = spell_id
                    learned.append(data_copy)
                else:
                    logging.warning(f"Learned spell '{spell_id}' for player {player_id} not found in SPELLS data.")
    # Сортируем по уровню требования
    learned.sort(key=lambda s: s.get('level_req', 999))
    return learned

async def learn_spell(player_id: int, spell_id: str) -> bool:
    """Добавляет заклинание в список изученных игроком."""
    if spell_id not in SPELLS:
        logging.error(f"Attempted to learn non-existent spell_id '{spell_id}' for player {player_id}.")
        return False
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            await db.execute(
                "INSERT INTO player_spells (player_id, spell_id) VALUES (?, ?)",
                (player_id, spell_id)
            )
            await db.commit()
            logging.info(f"Player {player_id} learned spell '{spell_id}' ({SPELLS[spell_id]['name']}).")
            return True
        except aiosqlite.IntegrityError: # Если уже изучено (UNIQUE constraint)
             logging.warning(f"Player {player_id} tried to learn already known spell '{spell_id}'.")
             return False # Не ошибка, но и не учили заново
        except Exception as e:
            logging.error(f"Failed to learn spell for player {player_id}, spell {spell_id}: {e}", exc_info=True)
            return False
# --- Обновление Основных Ресурсов (HP/Mana/ES) ---
async def update_player_vitals(user_id: int, hp_change: int = 0, mana_change: int = 0, es_change: int = 0, set_hp: int = None, set_mana: int = None, set_es: int = None):
    """
    Обновляет ТЕКУЩЕЕ HP, Ману и Энергощит игрока в базе данных.
    Применяет изменения (hp_change и т.д.) ИЛИ устанавливает точные значения (set_hp и т.д.).
    Урон (hp_change<0) сначала вычитается из текущего ES.
    !!! НЕ ПРОВЕРЯЕТ ВЕРХНИЕ ГРАНИЦЫ (MaxHP/MaxMana/MaxES) - это должен делать вызывающий код !!!
    Проверяет только нижнюю границу (0).
    Возвращает кортеж фактических записанных в БД значений (current_hp, current_mana, current_es) или None.
    """
    player = await get_player(user_id)
    if not player:
        logging.warning(f"Attempted to update vitals for non-existent player {user_id}")
        return None

    # Получаем текущие значения из БД
    current_hp = player['current_hp']
    current_mana = player['current_mana']
    current_es = player['energy_shield']

    # Значения, которые будут записаны в БД
    final_hp = current_hp
    final_mana = current_mana
    final_es = current_es

    # --- Обработка set_* (имеет приоритет) ---
    hp_was_set = False; mana_was_set = False; es_was_set = False
    if set_hp is not None: final_hp = set_hp; hp_was_set = True; logging.info(f"[update_vitals SET_HP] Setting HP to {set_hp}")
    if set_mana is not None: final_mana = set_mana; mana_was_set = True; logging.info(f"[update_vitals SET_MANA] Setting Mana to {set_mana}")
    if set_es is not None: final_es = set_es; es_was_set = True; logging.info(f"[update_vitals SET_ES] Setting ES to {set_es}")

    # --- Обработка *_change (только если set_* не использовался для этого ресурса) ---
    # Обработка урона
    if hp_change < 0 and not hp_was_set and not es_was_set: # Не применяем урон, если HP или ES были установлены явно
        damage_taken = abs(hp_change)
        es_damage = min(final_es, damage_taken) # Вычитаем из ТЕКУЩЕГО (final_es)
        hp_damage = damage_taken - es_damage

        logging.info(f"[update_vitals DAMAGE] Taken={damage_taken}, CurrentES={final_es}, ES_absorb={es_damage}, HP_dmg={hp_damage}")
        final_es -= es_damage
        final_hp -= hp_damage
        logging.info(f"[update_vitals AFTER_DMG] NewES={final_es}, NewHP={final_hp}")
    elif hp_change > 0 and not hp_was_set: # Исцеление HP
        logging.info(f"[update_vitals HEAL_HP] Adding {hp_change} HP. Initial HP: {current_hp}")
        final_hp += hp_change

    # Изменение маны
    if mana_change != 0 and not mana_was_set:
        logging.info(f"[update_vitals MANA_CHG] Change: {mana_change}. Initial Mana: {current_mana}")
        final_mana += mana_change

    # Изменение ES (если не урон и не было set_es)
    if hp_change >= 0 and es_change != 0 and not es_was_set:
        logging.info(f"[update_vitals ES_CHG] Change: {es_change}. Initial ES: {current_es}")
        final_es += es_change

    # --- Ограничение СНИЗУ (0) ---
    final_hp = max(0, final_hp)
    final_mana = max(0, final_mana)
    final_es = max(0, final_es)
    # --- ВЕРХНЕЕ ОГРАНИЧЕНИЕ УБРАНО ---

    # --- Логируем финальные значения ПЕРЕД записью ---
    logging.info(f"[update_vitals FINAL_VALS to write] HP={final_hp}, Mana={final_mana}, ES={final_es}")

    # Обновляем данные в БД
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "UPDATE players SET current_hp = ?, current_mana = ?, energy_shield = ? WHERE user_id = ?",
                (final_hp, final_mana, final_es, user_id)
            )
            await db.commit()
        logging.info(f"[update_vitals END] DB updated successfully. Returning: HP={final_hp}, Mana={final_mana}, ES={final_es}")
        return final_hp, final_mana, final_es
    except Exception as e:
         logging.error(f"Failed to update vitals in DB for user {user_id}: {e}", exc_info=True)
         return None # Возвращаем None при ошибке записи


    # Обновляем данные в БД
    # Обновляем данные в БД
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE players SET current_hp = ?, current_mana = ?, energy_shield = ? WHERE user_id = ?",
            (final_hp, final_mana, final_es, user_id) # Используем final_ переменные
        )
        await db.commit()

    logging.info(f"[update_vitals END] DB updated. Returning: HP={final_hp}, Mana={final_mana}, ES={final_es}")
    return final_hp, final_mana, final_es


# --- Обновление Опыта, Золота, Уровня ---
async def update_player_xp(user_id: int, gained_xp: int = 0, gained_gold: int = 0):
    """
    Обновляет опыт и золото игрока, проверяет повышение уровня.
    Применяет штрафы, если gained_xp или gained_gold отрицательные.
    Начисляет очки характеристик при левел-апе и обновляет Max HP/Mana.
    Возвращает кортеж: (словарь_с_изменениями_при_левел_апе_или_None, флаг_leveled_up)
    """
    player = await get_player(user_id)
    if not player:
        logging.warning(f"Attempted to update XP/Gold for non-existent player {user_id}")
        return None, False # Возвращаем None и False (не апнулся)

    MAX_LEVEL = 100 # Определяем максимальный уровень

    # --- Обработка Штрафов (отрицательные значения) ---
    if gained_xp < 0 or gained_gold < 0:
        # Не позволяем опыту/золоту уйти ниже 0
        new_xp = max(0, player['xp'] + gained_xp)
        new_gold = max(0, player['gold'] + gained_gold)
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE players SET xp = ?, gold = ? WHERE user_id = ?", (new_xp, new_gold, user_id))
            await db.commit()
        logging.info(f"Player {user_id} penalized: XP change {gained_xp} -> {new_xp}, Gold change {gained_gold} -> {new_gold}")
        # При штрафе левел-апа быть не может
        return None, False

    # --- Обработка Начисления Опыта ---
    # Не начисляем опыт, если игрок уже достиг максимального уровня
    if player['level'] >= MAX_LEVEL:
        gained_xp = 0

    # Если нет прибавки к опыту или золоту, выходим
    if gained_xp <= 0 and gained_gold <= 0:
        return None, False

    # Получаем текущие значения для расчета
    new_xp = player['xp'] + gained_xp
    xp_needed = player['xp_to_next_level']
    current_level = player['level']
    new_level = current_level
    leveled_up = False
    gained_stat_points = 0 # Очки, полученные за этот вызов функции

    # Базовые статы класса для пересчета HP/Mana
    base_class_stats = BASE_STATS.get(player['class'], BASE_STATS['Scion'])
    # Текущие статы (они НЕ меняются при левел-апе здесь, только очки даются)
    current_strength = player['strength']
    current_dexterity = player['dexterity']
    current_intelligence = player['intelligence']
    # Текущие Max HP/Mana (будут пересчитаны, если уровень повысится)
    current_max_hp = player['max_hp']
    current_max_mana = player['max_mana']

    # --- Цикл Повышения Уровня ---
    # Повышаем уровень, пока хватает опыта и не достигнут максимум
    while new_xp >= xp_needed and new_level < MAX_LEVEL:
        new_xp -= xp_needed       # Вычитаем опыт, потраченный на уровень
        new_level += 1            # Увеличиваем уровень
        leveled_up = True         # Ставим флаг, что уровень был повышен
        gained_stat_points += 2   # Начисляем +2 очка характеристик
        xp_needed = int(xp_needed * 1.5) # Увеличиваем требуемый опыт для СЛЕДУЮЩЕГО уровня (примерная формула)

        logging.info(f"Player {user_id} leveled up to {new_level}! Gained {gained_stat_points} stat points (total in this update).")

        # --- Пересчет Макс. HP/Mana при повышении уровня ---
        hp_gain_per_level = 10 # Фиксированный бонус HP за уровень
        mana_gain_per_level = 5 # Фиксированный бонус Mana за уровень

        # Пересчитываем на основе БАЗЫ класса, ТЕКУЩИХ статов и НОВОГО уровня
        current_max_hp = base_class_stats['hp'] + int(current_strength * 0.5) + (new_level * hp_gain_per_level)
        current_max_mana = base_class_stats['mana'] + current_intelligence + (new_level * mana_gain_per_level)

    # --- Обновление Базы Данных ---
    new_gold = player['gold'] + gained_gold

    async with aiosqlite.connect(DB_NAME) as db:
        # Обновляем уровень, опыт, золото, ОЧКИ СТАТОВ, макс. HP/Mana
        await db.execute(
            """UPDATE players SET
               level = ?,
               xp = ?,
               xp_to_next_level = ?,
               gold = ?,
               stat_points = stat_points + ?,  -- Добавляем накопленные очки
               max_hp = ?,
               max_mana = ?
               WHERE user_id = ?""",
            (
               new_level, new_xp, xp_needed, new_gold,
               gained_stat_points, # Передаем накопленные очки для добавления
               current_max_hp, current_max_mana,
               user_id
            )
        )

        # Если был левел-ап, восстанавливаем HP и Mana до новых максимумов
        if leveled_up:
             await db.execute(
                 "UPDATE players SET current_hp = max_hp, current_mana = max_mana WHERE user_id = ?",
                 (user_id,)
             )
             logging.info(f"Player {user_id} HP/Mana restored after level up.")

        # Применяем изменения
        await db.commit()

    # Формируем словарь с результатами, если был левел-ап
    level_up_results = None
    if leveled_up:
        level_up_results = {
            'level': new_level,
            'xp': new_xp,
            'xp_to_next_level': xp_needed,
            'gold': new_gold,
            'gained_stat_points': gained_stat_points, # Сколько очков получено именно за этот апдейт
            'new_max_hp': current_max_hp,
            'new_max_mana': current_max_mana
        }

    # Возвращаем результаты и флаг левел-апа
    return level_up_results, leveled_up


# --- Штраф за Смерть ---
async def apply_death_penalty(user_id: int):
    """Применяет штраф к опыту и золоту при смерти."""
    player = await get_player(user_id)
    if not player or player['level'] <= 1: # Не штрафуем на 1 уровне
        return 0, 0 # Возвращаем нулевой штраф

    # Штраф опыта: 10% от ТЕКУЩЕГО накопленного опыта на уровне
    xp_penalty = math.floor(player['xp'] * 0.10)

    # Штраф золота: 5% от текущего золота
    gold_penalty = math.floor(player['gold'] * 0.05)

    logging.info(f"Applying death penalty to player {user_id} (Level {player['level']}): -{xp_penalty} XP, -{gold_penalty} Gold")

    # Используем update_player_xp с отрицательными значениями
    # Эта функция сама позаботится, чтобы xp/gold не ушли ниже 0
    await update_player_xp(user_id, gained_xp=-xp_penalty, gained_gold=-gold_penalty)

    # Возвращаем значения штрафа для сообщения игроку
    return xp_penalty, gold_penalty


# --- Регенерация ---
async def record_regen_time(user_id: int, regen_type: str):
    """Обновляет время последней регенерации (hp или mana)."""
    current_time = int(time.time())
    # Определяем поле для обновления в зависимости от типа регенерации
    field_to_update = "last_hp_regen_time" if regen_type == "hp" else "last_mana_regen_time"

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(f"UPDATE players SET {field_to_update} = ? WHERE user_id = ?", (current_time, user_id))
        await db.commit()

async def check_and_apply_regen(user_id: int, current_state_str: str | None):
    """
    Проверяет и применяет пассивную регенерацию HP/Mana, если игрок не в бою.
    Учитывает эффекты 'regen_multiplier' и 'cannot_regen_mana'.
    Возвращает кортеж (hp_regened, mana_regened).
    """
    # Проверяем состояния боя
    is_fighting = (current_state_str == CombatStates.fighting.state or
                   (current_state_str and current_state_str.startswith("BossCombatStates:")))

    if is_fighting:
         logging.debug(f"Player {user_id} is fighting, skipping passive regen check.")
         return 0, 0

    # Получаем ЭФФЕКТИВНЫЕ статы, чтобы иметь доступ к active_effects
    player = await get_player_effective_stats(user_id)
    if not player:
        logging.warning(f"Regen check failed: Player {user_id} not found.")
        return 0, 0

    current_time = int(time.time())
    hp_regen_interval = 30
    mana_regen_interval = 60
    hp_regened = 0
    mana_regened = 0

    # Получаем активные эффекты
    active_effects = player.get('active_effects', {})

    # Получаем множитель регенерации
    try:
        regen_multiplier = float(active_effects.get('regen_multiplier', 1.0))
        if regen_multiplier <= 0: # Предохранитель от отрицательного/нулевого регена
            regen_multiplier = 0
            logging.warning(f"Regen multiplier is <= 0 ({regen_multiplier}) for user {user_id}. Disabling regen.")
    except (ValueError, TypeError):
        regen_multiplier = 1.0
        logging.error(f"Invalid 'regen_multiplier' value: {active_effects.get('regen_multiplier')}. Using 1.0.")

    if regen_multiplier != 1.0 and regen_multiplier > 0:
         logging.info(f"Applying regen multiplier {regen_multiplier} for user {user_id}")

    # --- Регенерация HP ---
    if regen_multiplier > 0 and player['current_hp'] < player['max_hp']:
        hp_time_passed = current_time - player['last_hp_regen_time']
        # Применяем множитель к расчетному количеству регена
        hp_to_regen = math.floor(hp_time_passed / hp_regen_interval * regen_multiplier)

        if hp_to_regen > 0:
            new_hp = min(player['max_hp'], player['current_hp'] + hp_to_regen)
            hp_regened = new_hp - player['current_hp']
            if hp_regened > 0:
                 await update_player_vitals(user_id, set_hp=new_hp)
                 await record_regen_time(user_id, 'hp')
                 logging.info(f"Player {user_id} regenerated {hp_regened} HP (multiplier: {regen_multiplier}).")

    # --- Регенерация Mana ---
    # Проверяем эффект 'cannot_regen_mana'
    can_regen_mana = 'cannot_regen_mana' not in active_effects

    if regen_multiplier > 0 and can_regen_mana and player['current_mana'] < player['max_mana']:
        mana_time_passed = current_time - player['last_mana_regen_time']
        # Применяем множитель
        mana_to_regen = math.floor(mana_time_passed / mana_regen_interval * regen_multiplier)

        if mana_to_regen > 0:
            new_mana = min(player['max_mana'], player['current_mana'] + mana_to_regen)
            mana_regened = new_mana - player['current_mana']
            if mana_regened > 0:
                await update_player_vitals(user_id, set_mana=new_mana)
                await record_regen_time(user_id, 'mana')
                logging.info(f"Player {user_id} regenerated {mana_regened} Mana (multiplier: {regen_multiplier}).")
    elif not can_regen_mana:
        logging.debug(f"Mana regeneration skipped for user {user_id} due to 'cannot_regen_mana' effect.")
        # Можно принудительно обновить время регена маны, чтобы счетчик не накапливался
        await record_regen_time(user_id, 'mana')

    return hp_regened, mana_regened


# --- Прокачка Статов ---
async def update_stat_points(user_id: int, points_change: int):
    """Изменяет количество свободных очков характеристик (может быть отрицательным для возврата)."""
    async with aiosqlite.connect(DB_NAME) as db:
        # Используем `stat_points = stat_points + ?` для атомарного изменения
        # и `max(0, ...)` чтобы не уйти в отрицательные очки при возврате
        await db.execute("UPDATE players SET stat_points = max(0, stat_points + ?) WHERE user_id = ?", (points_change, user_id))
        await db.commit()
    logging.debug(f"Player {user_id} stat points changed by {points_change}.")


async def increase_attribute(user_id: int, attribute: str, amount: int = 1):
    """
    Увеличивает указанную характеристику (strength, dexterity, intelligence) на amount.
    Пересчитывает и обновляет зависящие параметры (MaxHP/MaxMana).
    Возвращает True в случае успеха, False в случае ошибки.
    """
    # Проверяем корректность имени атрибута
    if attribute not in ['strength', 'dexterity', 'intelligence']:
        logging.error(f"Invalid attribute '{attribute}' requested for increase for user {user_id}.")
        return False

    player = await get_player(user_id)
    if not player:
        logging.warning(f"Attempted to increase attribute for non-existent player {user_id}")
        return False

    # Получаем текущие значения статов и уровня
    new_strength = player['strength']
    new_dexterity = player['dexterity']
    new_intelligence = player['intelligence']
    level = player['level']
    # Получаем базовые статы класса
    base_class_stats = BASE_STATS.get(player['class'], BASE_STATS['Scion'])
    hp_gain_per_level = 10
    mana_gain_per_level = 5

    # Применяем изменение к нужному атрибуту
    value_to_set = 0 # Переменная для хранения нового значения стата
    if attribute == 'strength':
        new_strength += amount
        value_to_set = new_strength # Запоминаем значение для SQL
    elif attribute == 'dexterity':
        new_dexterity += amount
        value_to_set = new_dexterity # Запоминаем значение для SQL
    elif attribute == 'intelligence':
        new_intelligence += amount
        value_to_set = new_intelligence # Запоминаем значение для SQL

    # --- Пересчитываем Max HP/Mana на основе НОВЫХ статов и ТЕКУЩЕГО уровня ---
    # Используем обновленные new_strength и new_intelligence для пересчета
    new_max_hp = base_class_stats['hp'] + int(new_strength * 0.5) + (level * hp_gain_per_level)
    new_max_mana = base_class_stats['mana'] + new_intelligence + (level * mana_gain_per_level)

    # Обновляем атрибут и Max HP/Mana в базе данных
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            # f-строка для имени столбца здесь безопасна, так как 'attribute' проверяется выше
            # Вместо getattr используем переменную value_to_set
            sql_query = f"UPDATE players SET {attribute} = ?, max_hp = ?, max_mana = ? WHERE user_id = ?"
            params = (value_to_set, new_max_hp, new_max_mana, user_id)
            logging.debug(f"Executing SQL: {sql_query} with params {params}") # Логируем запрос
            await db.execute(sql_query, params)

            await db.commit()
            logging.info(f"Player {user_id} increased {attribute} by {amount}. New value: {value_to_set}. New MaxHP: {new_max_hp}, New MaxMana: {new_max_mana}")
            return True # Успех
        except Exception as e:
             # Логируем ошибку выполнения SQL
             logging.error(f"Failed to execute attribute increase SQL for user {user_id}: {e}", exc_info=True)
             return False # Неудача


# --- Функции для наград и квестов (перенесены из daily.py для централизации работы с БД) ---
async def set_daily_reward_time(user_id: int):
    """Устанавливает время получения ежедневной награды на текущее."""
    current_time = int(time.time())
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE players SET last_daily_reward_time = ? WHERE user_id = ?", (current_time, user_id))
        await db.commit()

async def assign_daily_quest(user_id: int, monster_key: str, target_count: int, gold_reward: int, xp_reward: int):
    """Назначает игроку ежедневный квест."""
    current_time = int(time.time())
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            UPDATE players SET
            quest_monster_key = ?, quest_target_count = ?, quest_current_count = 0,
            quest_gold_reward = ?, quest_xp_reward = ?, last_quest_time = ?
            WHERE user_id = ?
        """, (monster_key, target_count, gold_reward, xp_reward, current_time, user_id))
        await db.commit()
    logging.info(f"Assigned daily quest to {user_id}: Kill {target_count} '{monster_key}'")


async def update_quest_progress(user_id: int, killed_monster_key: str):
    """
    Обновляет прогресс квеста при убийстве монстра.
    Возвращает словарь с результатом или None, если нет активного квеста на этого монстра.
    """
    player = await get_player(user_id)
    # Проверяем, есть ли активный квест и совпадает ли убитый монстр с целью
    if (not player
            or not player['quest_monster_key']
            or player['quest_monster_key'] != killed_monster_key
            or player['quest_current_count'] >= player['quest_target_count']):
        return None # Нет активного/подходящего квеста или он уже выполнен

    # Увеличиваем счетчик убитых монстров
    new_count = player['quest_current_count'] + 1
    # Проверяем, выполнен ли квест
    quest_complete = new_count >= player['quest_target_count']

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE players SET quest_current_count = ? WHERE user_id = ?", (new_count, user_id))
        await db.commit()

    if quest_complete:
        logging.info(f"Player {user_id} completed quest: Kill {player['quest_target_count']} '{player['quest_monster_key']}'")
        # Возвращаем информацию о завершении и награде
        return {
            'completed': True,
            'gold_reward': player['quest_gold_reward'],
            'xp_reward': player['quest_xp_reward']
        }
    else:
        # Возвращаем информацию о прогрессе
        logging.debug(f"Player {user_id} quest progress: {new_count}/{player['quest_target_count']} '{player['quest_monster_key']}' killed.")
        return {'completed': False, 'current_count': new_count, 'target_count': player['quest_target_count']}

async def clear_daily_quest(user_id: int):
    """Сбрасывает данные квеста (после выполнения или провала)."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            UPDATE players SET
            quest_monster_key = NULL, quest_target_count = 0, quest_current_count = 0,
            quest_gold_reward = 0, quest_xp_reward = 0
            WHERE user_id = ? """, (user_id,))
        await db.commit()
    logging.info(f"Cleared daily quest data for player {user_id}.")

# --- Функции для Магазинов ---

async def get_shop_items(shop_type: str) -> tuple[list[str], int]:
    """Получает список ID предметов и время последнего обновления для магазина."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT item_ids, last_refresh_time FROM shop_state WHERE shop_type = ?",
            (shop_type,)
        ) as cursor:
            result = await cursor.fetchone()
            if result:
                try:
                    item_ids = json.loads(result[0]) # Декодируем JSON
                    last_refresh = result[1]
                    return item_ids, last_refresh
                except json.JSONDecodeError:
                    logging.error(f"Failed to decode JSON item_ids for shop '{shop_type}'.")
                    return [], 0
            else:
                logging.error(f"Shop state not found for type '{shop_type}'.")
                return [], 0 # Возвращаем пустой список и 0 время

async def update_shop_items(shop_type: str, new_item_ids: list[str]):
    """Обновляет список предметов и время обновления для магазина."""
    current_time = int(time.time())
    item_ids_json = json.dumps(new_item_ids) # Кодируем список в JSON
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE shop_state SET item_ids = ?, last_refresh_time = ? WHERE shop_type = ?",
            (item_ids_json, current_time, shop_type)
        )
        await db.commit()
    logging.info(f"Shop '{shop_type}' refreshed. New items: {new_item_ids}")

# --- Функции для Кузнеца ---

async def get_blacksmith_items() -> tuple[list[str], int]:
    """Получает список ID легендарок и время последнего обновления у кузнеца."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            # state_id=1, так как запись всегда одна
            "SELECT legendary_ids, last_refresh_time FROM blacksmith_state WHERE state_id = 1"
        ) as cursor:
            result = await cursor.fetchone()
            if result:
                try:
                    item_ids = json.loads(result[0])
                    last_refresh = result[1]
                    return item_ids, last_refresh
                except json.JSONDecodeError:
                     logging.error("Failed to decode JSON legendary_ids for blacksmith.")
                     return [], 0
            else:
                 # Этого не должно случиться, если init_db сработал
                 logging.error("Blacksmith state not found (state_id=1).")
                 return [], 0

async def update_blacksmith_items(new_legendary_ids: list[str]):
    """Обновляет список легендарок и время у кузнеца."""
    current_time = int(time.time())
    ids_json = json.dumps(new_legendary_ids)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE blacksmith_state SET legendary_ids = ?, last_refresh_time = ? WHERE state_id = 1",
            (ids_json, current_time)
        )
        await db.commit()
    logging.info(f"Blacksmith items refreshed. New legendaries: {new_legendary_ids}")

async def count_player_fragments(player_id: int, fragment_item_id: str) -> int:
     """Считает количество КОНКРЕТНЫХ фрагментов у игрока."""
     async with aiosqlite.connect(DB_NAME) as db:
         async with db.execute(
             "SELECT COUNT(*) FROM inventory WHERE player_id = ? AND item_id = ? AND is_equipped = FALSE", # Считаем только не надетые
             (player_id, fragment_item_id)
         ) as cursor:
             result = await cursor.fetchone()
             return result[0] if result else 0

async def remove_player_fragments(player_id: int, fragment_item_id: str, count: int) -> bool:
    """Удаляет указанное количество фрагментов из инвентаря игрока."""
    if count <= 0: return True # Нечего удалять

    # Получаем ID записей инвентаря для удаления (с LIMIT)
    rows_to_delete_ids = []
    async with aiosqlite.connect(DB_NAME) as db:
         async with db.execute(
             "SELECT inventory_id FROM inventory WHERE player_id = ? AND item_id = ? AND is_equipped = FALSE LIMIT ?",
             (player_id, fragment_item_id, count)
         ) as cursor:
              rows = await cursor.fetchall()
              rows_to_delete_ids = [row[0] for row in rows]

    if len(rows_to_delete_ids) < count:
         logging.warning(f"Player {player_id} has less than {count} fragments of '{fragment_item_id}' to remove.")
         return False # Недостаточно фрагментов

    # Удаляем найденные записи
    async with aiosqlite.connect(DB_NAME) as db:
         try:
             # Создаем плейсхолдеры для запроса ('?, ?, ?')
             placeholders = ', '.join('?' * len(rows_to_delete_ids))
             await db.execute(f"DELETE FROM inventory WHERE inventory_id IN ({placeholders})", rows_to_delete_ids)
             await db.commit()
             logging.info(f"Removed {count} fragments ('{fragment_item_id}') for player {player_id}.")
             return True
         except Exception as e:
             logging.error(f"Failed to remove fragments for player {player_id}, fragment {fragment_item_id}: {e}", exc_info=True)
             return False

# Добавляем импорт CombatStates для функции check_and_apply_regen
# Это не очень хорошо с точки зрения архитектуры (db_manager зависит от handlers),
# но для простоты MVP приемлемо. В идеале состояние боя нужно передавать параметром.
try:
    from handlers.combat import CombatStates
except ImportError:
    class CombatStates:
        fighting = type("State", (), {"state": "CombatStates:fighting"})()
    logging.debug("Using placeholder CombatStates in db_manager.")
