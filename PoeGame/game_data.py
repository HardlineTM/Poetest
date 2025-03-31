# game_data.py
import random
import time
import math
import logging
# --- КОНСТАНТЫ ТИПОВ ПРЕДМЕТОВ / СЛОТОВ ---
ITEM_TYPE_HELMET = "helmet"
ITEM_TYPE_CHEST = "chest"
ITEM_TYPE_GLOVES = "gloves"
ITEM_TYPE_BOOTS = "boots"
ITEM_TYPE_RING = "ring"
ITEM_TYPE_AMULET = "amulet"
ITEM_TYPE_BELT = "belt"
ITEM_TYPE_FRAGMENT = "fragment" # <-- Новый тип
ITEM_TYPE_LEGENDARY = "legendary" # <-- Тип для легендарок (или использовать 'unique'?)
ITEM_TYPE_WEAPON = "weapon" # <-- Новый тип Оружие
ITEM_TYPE_SHIELD = "shield" # <-- Новый тип Щит (пока не используется)

SLOT_HELMET = "helmet"
SLOT_CHEST = "chest"
SLOT_GLOVES = "gloves"
SLOT_BOOTS = "boots"
SLOT_RING1 = "ring1"
SLOT_RING2 = "ring2"
SLOT_AMULET = "amulet"
SLOT_BELT = "belt"
SLOT_MAIN_HAND = "main_hand" # <-- Слот для основного оружия
SLOT_OFF_HAND = "off_hand"   # <-- Слот для щита или второго оружия (пока щит)

ALL_SLOTS = [
    SLOT_HELMET, SLOT_CHEST, SLOT_GLOVES, SLOT_BOOTS,
    SLOT_RING1, SLOT_RING2, SLOT_AMULET, SLOT_BELT,
    SLOT_MAIN_HAND, SLOT_OFF_HAND
]

ITEM_SLOTS = {
    ITEM_TYPE_HELMET: [SLOT_HELMET],
    ITEM_TYPE_CHEST: [SLOT_CHEST],
    ITEM_TYPE_GLOVES: [SLOT_GLOVES],
    ITEM_TYPE_BOOTS: [SLOT_BOOTS],
    ITEM_TYPE_RING: [SLOT_RING1, SLOT_RING2],
    ITEM_TYPE_AMULET: [SLOT_AMULET],
    ITEM_TYPE_BELT: [SLOT_BELT],
    ITEM_TYPE_WEAPON: [SLOT_MAIN_HAND], # Оружие пока только в одну руку
    ITEM_TYPE_SHIELD: [SLOT_OFF_HAND], # Щиты (если добавим)
    ITEM_TYPE_FRAGMENT: [],
    ITEM_TYPE_LEGENDARY: [], # Определим слоты ниже
}

# Дополним ITEM_SLOTS ниже, когда определим легендарки

# --- Базовые статы для классов ---
BASE_STATS = {
    # ... (как было) ...
    'Marauder': {'name': 'Дикарь', 'hp': 60, 'mana': 40, 'str': 32, 'dex': 14, 'int': 14},
    'Ranger': {'name': 'Охотница', 'hp': 55, 'mana': 45, 'str': 14, 'dex': 32, 'int': 14},
    'Witch': {'name': 'Ведьма', 'hp': 45, 'mana': 55, 'str': 14, 'dex': 14, 'int': 32},
    'Duelist': {'name': 'Дуэлянт', 'hp': 58, 'mana': 42, 'str': 23, 'dex': 23, 'int': 14},
    'Templar': {'name': 'Жрец', 'hp': 50, 'mana': 50, 'str': 23, 'dex': 14, 'int': 23},
    'Shadow': {'name': 'Бандит', 'hp': 52, 'mana': 48, 'str': 14, 'dex': 23, 'int': 23},
    'Scion': {'name': 'Дворянка', 'hp': 50, 'mana': 50, 'str': 20, 'dex': 20, 'int': 20},
}

# --- Словарик монстров ---
MONSTERS = {
    # ... (как было) ...
    "Гниющий Зомби":    {'hp': 20, 'damage': 3, 'xp_reward': 5},
    "Скелет-лучник":    {'hp': 18, 'damage': 4, 'xp_reward': 6},
    "Карманный Паучок": {'hp': 15, 'damage': 5, 'xp_reward': 7},
    "Береговой Краб":   {'hp': 35, 'damage': 4, 'xp_reward': 10},
    "Пещерный Ползун":  {'hp': 40, 'damage': 6, 'xp_reward': 12},
    "Падший Шаман":     {'hp': 40, 'damage': 8, 'xp_reward': 15},
    "Каменный Голем":   {'hp': 60, 'damage': 6, 'xp_reward': 20},
    "Неупокоенный Дух": {'hp': 50, 'damage': 10, 'xp_reward': 25},
    "Костяной Охотник": {'hp': 55, 'damage': 9, 'xp_reward': 22},
    "Разъяренный Козел":{'hp': 70, 'damage': 7, 'xp_reward': 28},
}

# --- Словарик заклинаний игрока ---
SPELLS = {
    # Стартовый спелл (Уровень 1)
    "spell001": {"name": "Малая вспышка", "level_req": 1, "mana_cost": 5, "target": "enemy", "effect_type": "damage", "effect_value": 8, "description": "Слабая атака огнем."},

    # Новые спеллы по уровням
    "spell002": {
        "name": "Укрепление",
        "level_req": 2,
        "mana_cost": 15, # Оставляем ту же стоимость?
        "target": "self",
        "effect_type": "temp_buff",
        # --- ИЗМЕНЕНИЕ: Убираем ES, увеличиваем броню ---
        "effect_value": {"armor": 40}, # Теперь даем +40 брони
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---
        "duration": 3,
        "description": "Временно повышает броню (+40) на 3 хода." # Обновляем описание
     },
    "spell003": {"name": "Ледяная стрела", "level_req": 3, "mana_cost": 10, "target": "enemy", "effect_type": "damage", "effect_value": 15, "description": "Атака холодом."},
    "spell004": {"name": "Малое исцеление", "level_req": 4, "mana_cost": 25, "target": "self", "effect_type": "heal_percent", "effect_value": 15, "description": "Восстанавливает 15% макс. здоровья."}, # Хил
    "spell005": {"name": "Шоковый импульс", "level_req": 5, "mana_cost": 18, "target": "enemy", "effect_type": "damage", "effect_value": 22, "description": "Разряд молнии."},
    "spell006": {"name": "Боевой клич", "level_req": 6, "mana_cost": 20, "target": "self", "effect_type": "buff_next_attack", "effect_value": 2.0, "duration": 1, "description": "Следующая атака (не заклинание!) нанесет двойной урон."}, # Бафф атаки
    "spell007": {"name": "Ядовитое облако", "level_req": 7, "mana_cost": 22, "target": "enemy", "effect_type": "damage", "effect_value": 28, "description": "Урон ядом."}, # Позже можно добавить урон со временем
    "spell008": {"name": "Регенерация", "level_req": 8, "mana_cost": 40, "target": "self", "effect_type": "heal_over_time", "effect_value": {"hp_per_turn": 5, "duration": 5}, "description": "Восстанавливает 5 HP в ход (5 ходов)."}, # Хил со временем (сложнее)
    "spell009": {"name": "Цепная молния", "level_req": 9, "mana_cost": 30, "target": "enemy", "effect_type": "damage", "effect_value": 35, "description": "Мощный удар молнии."}, # Позже - урон по нескольким целям
    "spell010": {"name": "Призыв голема", "level_req": 10, "mana_cost": 50, "target": "self", "effect_type": "summon", "effect_value": "stone_golem", "description": "Призывает каменного голема-помощника."}, # Саммоны (очень сложно)
    "spell011": {"name": "Огненный шар", "level_req": 1, "mana_cost": 12, "target": "enemy", "effect_type": "damage", "effect_value": 18, "description": "Классический огненный шар."}, # Перебалансируем старый
    # У старых спеллов тоже добавляем level_req, target, effect_type, effect_value, description
    # "Разряд молнии": ...
    # "Ледяной шип": ...
    # "Стрела хаоса": ...
}
SPELL_DAMAGE_INTELLIGENCE_SCALING = 0.01 # +1% урона за 1 интеллект (или 10% за 10 инт)
# --- БОССЫ ---
# Список боссов по порядку. Индекс в списке = ID босса (0-9)
# fragment_item_id - ID гарантированного дропа фрагмента
BOSSES = [
    {"id": 0, "name": "Мервейл, Сирена", "base_hp": 150, "base_damage": 15, "fragment_item_id": "frag_0"},
    {"id": 1, "name": "Ваал, Надзиратель", "base_hp": 300, "base_damage": 30, "fragment_item_id": "frag_1"},
    {"id": 2, "name": "Пити, Истязательница", "base_hp": 600, "base_damage": 60, "fragment_item_id": "frag_2"},
    {"id": 3, "name": "Доминус, Владыка", "base_hp": 1200, "base_damage": 120, "fragment_item_id": "frag_3"},
    {"id": 4, "name": "Малахай, Бессмертный", "base_hp": 2400, "base_damage": 240, "fragment_item_id": "frag_4"},
    {"id": 5, "name": "Китава, Отец Горя", "base_hp": 4800, "base_damage": 480, "fragment_item_id": "frag_5"},
    {"id": 6, "name": "Аракаали, Мать Пауков", "base_hp": 9600, "base_damage": 960, "fragment_item_id": "frag_6"},
    {"id": 7, "name": "Создатель", "base_hp": 19200, "base_damage": 1920, "fragment_item_id": "frag_7"},
    {"id": 8, "name": "Древний", "base_hp": 38400, "base_damage": 3840, "fragment_item_id": "frag_8"},
    {"id": 9, "name": "Сирус, Пробудитель Миров", "base_hp": 76800, "base_damage": 7680, "fragment_item_id": "frag_9"},
]

# --- БАЗА ДАННЫХ ПРЕДМЕТОВ (MVP) ---
# Ключ - Уникальный ID предмета (строка)
# Значения:
#   name: Отображаемое имя
#   type: Тип предмета (из констант ITEM_TYPE_*)
#   rarity: 'common', 'magic', 'rare' (пока для цвета/фильтрации, не для модов)
#   drop_chance: Шанс выпадения в % (относительно других предметов, если дроп вообще произошел)
#   stats: Словарь со статами { 'stat_name': value, ... }
#       Возможные stat_name: max_hp, max_mana, strength, dexterity, intelligence, armor, max_energy_shield
ALL_ITEMS = {
    # --- Фрагменты Боссов ---
    # --- Легендарные Предметы (2% шанс с боссов) ---
# Добавляем cost и equipable=True, тип соответствует слоту
# Перчатки
    "leg_glv_001": {"name": "Хватка Алчности", "type": ITEM_TYPE_GLOVES, "rarity": "legendary", "drop_chance": 0, "stats": {"armor": 10, "dexterity": 5}, "effect": {"type": "triple_gold_chance", "value": 5}, "cost": 15000, "equipable": True},
    "leg_glv_002": {"name": "Длань Мудрости и Действия", "type": ITEM_TYPE_GLOVES, "rarity": "legendary", "drop_chance": 0, "stats": {"strength": 8, "intelligence": 8}, "description": "Атаки получают бонус к урону от Интеллекта", "cost": 18000, "equipable": True},
    "leg_glv_003": {"name": "Прикосновение Горечи", "type": ITEM_TYPE_GLOVES, "rarity": "legendary", "drop_chance": 0, "stats": {"max_hp": 20, "max_energy_shield": 15}, "effect": {"type": "leech_es_on_hit", "value": 1}, "cost": 16000, "equipable": True},
    # Нагрудники
    "leg_chs_001": {"name": "Покров Духа", "type": ITEM_TYPE_CHEST, "rarity": "legendary", "drop_chance": 0, "stats": {"max_mana": 50}, "effect": {"type": "mana_to_es", "value": 0.5}, "cost": 20000, "equipable": True},
    "leg_chs_002": {"name": "Сердце Каома", "type": ITEM_TYPE_CHEST, "rarity": "legendary", "drop_chance": 0, "stats": {"max_hp": 150, "strength": 10}, "description": "Нет гнезд для камней, много ХП", "cost": 25000, "equipable": True},
    "leg_chs_003": {"name": "Завет Ваал", "type": ITEM_TYPE_CHEST, "rarity": "legendary", "drop_chance": 0, "stats": {"max_energy_shield": 80, "intelligence": 10}, "effect": {"type": "spend_es_for_mana", "value": 0.2}, "cost": 22000, "equipable": True},
    "leg_chs_004": {"name": "Грозовая Туча", "type": ITEM_TYPE_CHEST, "rarity": "legendary", "drop_chance": 0, "stats": {"armor": 30, "max_energy_shield": 30}, "effect": {"type": "shock_nearby_on_hit", "value": 10}, "cost": 19000, "equipable": True},
    # Шлемы
    "leg_hlm_001": {"name": "Лик Безмолвия", "type": ITEM_TYPE_HELMET, "rarity": "legendary", "drop_chance": 0, "stats": {"max_mana": 40, "intelligence": 8}, "effect": {"type": "cannot_regen_mana", "value": 0}, "cost": 14000, "equipable": True},
    "leg_hlm_002": {"name": "Бездна", "type": ITEM_TYPE_HELMET, "rarity": "legendary", "drop_chance": 0, "stats": {"strength": 5, "dexterity": 5}, "description": "Добавляет урон хаосом к атакам", "cost": 17000, "equipable": True},
    "leg_hlm_003": {"name": "Неусыпный Взор", "type": ITEM_TYPE_HELMET, "rarity": "legendary", "drop_chance": 0, "stats": {"armor": 20, "max_energy_shield": 20}, "effect": {"type": "always_crit_low_life", "value": 0}, "cost": 20000, "equipable": True},
    # Ботинки
    "leg_bts_001": {"name": "След Пепла", "type": ITEM_TYPE_BOOTS, "rarity": "legendary", "drop_chance": 0, "stats": {"armor": 10, "max_hp": 25}, "description": "Оставляет горящую землю", "cost": 15000, "equipable": True},
    "leg_bts_002": {"name": "Поступь Азири", "type": ITEM_TYPE_BOOTS, "rarity": "legendary", "drop_chance": 0, "stats": {"max_energy_shield": 30, "dexterity": 8}, "description": "Шанс уворота от заклинаний", "cost": 18000, "equipable": True},
    # Пояса
    "leg_blt_001": {"name": "Пояс Обманщика", "type": ITEM_TYPE_BELT, "rarity": "legendary", "drop_chance": 0, "stats": {"strength": 6, "dexterity": 6}, "effect": {"type": "mana_cost_multiplier", "value": 0.5}, "cost": 25000, "equipable": True},
    "leg_blt_002": {"name": "Охотник за Головами", "type": ITEM_TYPE_BELT, "rarity": "legendary", "drop_chance": 0, "stats": {"strength": 10, "max_hp": 40}, "description": "Крадет моды редких монстров", "cost": 50000, "equipable": True}, # Очень дорогой
    # Амулеты
    "leg_amu_001": {"name": "Око Чайюлы", "type": ITEM_TYPE_AMULET, "rarity": "legendary", "drop_chance": 0, "stats": {"max_energy_shield": 50}, "description": "Иммунитет к оглушению, ES защищает ману", "cost": 30000, "equipable": True},
    "leg_amu_002": {"name": "Талисман Предателя", "type": ITEM_TYPE_AMULET, "rarity": "legendary", "drop_chance": 0, "stats": {"strength": 5, "dexterity": 5, "intelligence": 5}, "effect": {"type": "crit_multiplier_bonus", "value": 50}, "cost": 28000, "equipable": True},
    "leg_amu_003": {"name": "Эхо Предков", "type": ITEM_TYPE_AMULET, "rarity": "legendary", "drop_chance": 0, "stats": {"max_hp": 30, "max_mana": 30}, "description": "Умения Тотемов", "cost": 20000, "equipable": True},
    # Кольца
    "leg_rng_001": {"name": "Зов Братства", "type": ITEM_TYPE_RING, "rarity": "legendary", "drop_chance": 0, "stats": {"intelligence": 8, "max_mana": 20}, "description": "Урон молнии может замораживать", "cost": 22000, "equipable": True},
    "leg_rng_002": {"name": "Кольцо Кикадзару", "type": ITEM_TYPE_RING, "rarity": "legendary", "drop_chance": 0, "stats": {"max_hp": 15, "max_mana": 15}, "effect": {"type": "regen_multiplier", "value": 1.5}, "cost": 26000, "equipable": True},
    "leg_rng_003": {"name": "Печать Феникса", "type": ITEM_TYPE_RING, "rarity": "legendary", "drop_chance": 0, "stats": {"strength": 8, "armor": 15}, "description": "Иммунитет к поджогу", "cost": 23000, "equipable": True},
    "leg_rng_004": {"name": "Метка Древнего", "type": ITEM_TYPE_RING, "rarity": "legendary", "drop_chance": 0, "stats": {"strength": 4, "dexterity": 4, "intelligence": 4}, "description": "Урон против врагов под действием Древнего", "cost": 25000, "equipable": True},
    # Шлемы
    "hlm001": {"name": "Ржавый Шлем", "type": ITEM_TYPE_HELMET, "rarity": "common", "drop_chance": 15.0, "stats": {"armor": 5}, "cost": 30, "equipable": True},
    "hlm002": {"name": "Кожаная Шапка", "type": ITEM_TYPE_HELMET, "rarity": "common", "drop_chance": 15.0, "stats": {"max_energy_shield": 3}, "cost": 30, "equipable": True},
    "hlm003": {"name": "Укрепленный Бацинет", "type": ITEM_TYPE_HELMET, "rarity": "common", "drop_chance": 10.0, "stats": {"armor": 8, "strength": 1}, "cost": 50, "equipable": True},
    "hlm004": {"name": "Капюшон Тени", "type": ITEM_TYPE_HELMET, "rarity": "magic", "drop_chance": 8.0, "stats": {"dexterity": 2, "max_energy_shield": 5}, "cost": 100, "equipable": True},
    "hlm005": {"name": "Шлем с Пером", "type": ITEM_TYPE_HELMET, "rarity": "magic", "drop_chance": 7.0, "stats": {"max_hp": 10, "armor": 6}, "cost": 120, "equipable": True},
    "hlm006": {"name": "Диадема Провидца", "type": ITEM_TYPE_HELMET, "rarity": "magic", "drop_chance": 6.0, "stats": {"intelligence": 3, "max_mana": 8}, "cost": 110, "equipable": True},
    "hlm007": {"name": "Тяжелый Стальной Шлем", "type": ITEM_TYPE_HELMET, "rarity": "rare", "drop_chance": 4.0, "stats": {"armor": 15, "strength": 3, "max_hp": 5}, "cost": 300, "equipable": True},
    "hlm008": {"name": "Шлем Гладиатора", "type": ITEM_TYPE_HELMET, "rarity": "rare", "drop_chance": 3.0, "stats": {"armor": 10, "dexterity": 2, "max_hp": 15}, "cost": 350, "equipable": True},
    "hlm009": {"name": "Корона Мудрости", "type": ITEM_TYPE_HELMET, "rarity": "rare", "drop_chance": 2.0, "stats": {"intelligence": 5, "max_mana": 15, "max_energy_shield": 10}, "cost": 400, "equipable": True},
    "hlm010": {"name": "Древний Шлем Предков", "type": ITEM_TYPE_HELMET, "rarity": "rare", "drop_chance": 1.0, "stats": {"strength": 3, "dexterity": 3, "intelligence": 3, "armor": 12, "max_hp": 10}, "cost": 750, "equipable": True},
     # --- Оружие (Новое) ---
    # Добавляем cost и equipable=True
    "wpn001": {"name": "Ржавый Меч", "type": ITEM_TYPE_WEAPON, "rarity": "common", "drop_chance": 15.0, "stats": {"strength": 1}, "cost": 50, "equipable": True}, # Урон оружия пока не реализован
    "wpn002": {"name": "Кривой Нож", "type": ITEM_TYPE_WEAPON, "rarity": "common", "drop_chance": 15.0, "stats": {"dexterity": 1}, "cost": 50, "equipable": True},
    "wpn003": {"name": "Посох Ученика", "type": ITEM_TYPE_WEAPON, "rarity": "common", "drop_chance": 12.0, "stats": {"intelligence": 1, "max_mana": 5}, "cost": 60, "equipable": True},
    "wpn004": {"name": "Боевой Топор", "type": ITEM_TYPE_WEAPON, "rarity": "magic", "drop_chance": 10.0, "stats": {"strength": 3, "max_hp": 5}, "cost": 150, "equipable": True},
    "wpn005": {"name": "Элегантная Рапира", "type": ITEM_TYPE_WEAPON, "rarity": "magic", "drop_chance": 9.0, "stats": {"dexterity": 3, "crit_chance": 0.5}, "cost": 160, "equipable": True}, # Добавим статы, которых нет у игрока
    "wpn006": {"name": "Скипетр Жреца", "type": ITEM_TYPE_WEAPON, "rarity": "magic", "drop_chance": 8.0, "stats": {"intelligence": 3, "max_energy_shield": 10}, "cost": 170, "equipable": True},
    "wpn007": {"name": "Зазубренный Клинок", "type": ITEM_TYPE_WEAPON, "rarity": "rare", "drop_chance": 5.0, "stats": {"strength": 2, "dexterity": 2, "max_hp": 10}, "cost": 400, "equipable": True},
    "wpn008": {"name": "Великий Посох Мага", "type": ITEM_TYPE_WEAPON, "rarity": "rare", "drop_chance": 4.0, "stats": {"intelligence": 6, "max_mana": 20, "crit_damage": 10.0}, "cost": 500, "equipable": True},
    "wpn009": {"name": "Молот Титана", "type": ITEM_TYPE_WEAPON, "rarity": "rare", "drop_chance": 3.0, "stats": {"strength": 8, "armor": 5, "max_hp": 15}, "cost": 600, "equipable": True},
    "wpn010": {"name": "Лук Соколиный Глаз", "type": ITEM_TYPE_WEAPON, "rarity": "rare", "drop_chance": 1.0, "stats": {"dexterity": 10, "crit_chance": 1.0}, "cost": 1000, "equipable": True}, # Редкий

    # Нагрудники
    "chs001": {"name": "Лохмотья", "type": ITEM_TYPE_CHEST, "rarity": "common", "drop_chance": 15.0, "stats": {"armor": 3}, "cost": 20, "equipable": True},
    "chs002": {"name": "Простая Туника", "type": ITEM_TYPE_CHEST, "rarity": "common", "drop_chance": 15.0, "stats": {"max_energy_shield": 5}, "cost": 20, "equipable": True},
    "chs003": {"name": "Кольчужная Рубаха", "type": ITEM_TYPE_CHEST, "rarity": "common", "drop_chance": 10.0, "stats": {"armor": 10}, "cost": 60, "equipable": True},
    "chs004": {"name": "Кожаный Доспех", "type": ITEM_TYPE_CHEST, "rarity": "magic", "drop_chance": 8.0, "stats": {"armor": 5, "dexterity": 2}, "cost": 130, "equipable": True},
    "chs005": {"name": "Одеяние Ученика", "type": ITEM_TYPE_CHEST, "rarity": "magic", "drop_chance": 7.0, "stats": {"max_energy_shield": 15, "intelligence": 2}, "cost": 140, "equipable": True},
    "chs006": {"name": "Медный Нагрудник", "type": ITEM_TYPE_CHEST, "rarity": "magic", "drop_chance": 6.0, "stats": {"armor": 18, "strength": 2}, "cost": 150, "equipable": True},
    "chs007": {"name": "Доспех Наемника", "type": ITEM_TYPE_CHEST, "rarity": "rare", "drop_chance": 4.0, "stats": {"armor": 25, "max_hp": 15, "strength": 1}, "cost": 450, "equipable": True},
    "chs008": {"name": "Мантия Колдуна", "type": ITEM_TYPE_CHEST, "rarity": "rare", "drop_chance": 3.0, "stats": {"max_energy_shield": 30, "max_mana": 20, "intelligence": 3}, "cost": 500, "equipable": True},
    "chs009": {"name": "Ламеллярный Доспех", "type": ITEM_TYPE_CHEST, "rarity": "rare", "drop_chance": 2.0, "stats": {"armor": 20, "max_hp": 10, "dexterity": 3}, "cost": 480, "equipable": True},
    "chs010": {"name": "Сияющий Латный Доспех", "type": ITEM_TYPE_CHEST, "rarity": "rare", "drop_chance": 1.0, "stats": {"armor": 40, "strength": 5, "max_hp": 25}, "cost": 900, "equipable": True},
# Перчатки
    "glv001": {"name": "Тряпичные Обмотки", "type": ITEM_TYPE_GLOVES, "rarity": "common", "drop_chance": 15.0, "stats": {"armor": 1}, "cost": 10, "equipable": True},
    "glv002": {"name": "Кожаные Перчатки", "type": ITEM_TYPE_GLOVES, "rarity": "common", "drop_chance": 15.0, "stats": {"armor": 2}, "cost": 15, "equipable": True},
    "glv003": {"name": "Шерстяные Перчатки", "type": ITEM_TYPE_GLOVES, "rarity": "common", "drop_chance": 10.0, "stats": {"max_energy_shield": 3}, "cost": 15, "equipable": True},
    "glv004": {"name": "Заклепанные Перчатки", "type": ITEM_TYPE_GLOVES, "rarity": "magic", "drop_chance": 8.0, "stats": {"armor": 4, "strength": 1}, "cost": 70, "equipable": True},
    "glv005": {"name": "Перчатки Ловчего", "type": ITEM_TYPE_GLOVES, "rarity": "magic", "drop_chance": 7.0, "stats": {"armor": 3, "dexterity": 2}, "cost": 80, "equipable": True},
    "glv006": {"name": "Шелковые Перчатки", "type": ITEM_TYPE_GLOVES, "rarity": "magic", "drop_chance": 6.0, "stats": {"max_energy_shield": 6, "intelligence": 1}, "cost": 75, "equipable": True},
    "glv007": {"name": "Латные Рукавицы", "type": ITEM_TYPE_GLOVES, "rarity": "rare", "drop_chance": 4.0, "stats": {"armor": 8, "strength": 3}, "cost": 250, "equipable": True},
    "glv008": {"name": "Драконьи Перчатки", "type": ITEM_TYPE_GLOVES, "rarity": "rare", "drop_chance": 3.0, "stats": {"armor": 5, "max_hp": 10}, "cost": 280, "equipable": True},
    "glv009": {"name": "Перчатки Ассасина", "type": ITEM_TYPE_GLOVES, "rarity": "rare", "drop_chance": 2.0, "stats": {"dexterity": 4, "max_energy_shield": 5}, "cost": 300, "equipable": True},
    "glv010": {"name": "Рукавицы Титана", "type": ITEM_TYPE_GLOVES, "rarity": "rare", "drop_chance": 1.0, "stats": {"strength": 5, "armor": 6, "max_hp": 5}, "cost": 650, "equipable": True},
# Ботинки
    "bts001": {"name": "Стоптанные Сапоги", "type": ITEM_TYPE_BOOTS, "rarity": "common", "drop_chance": 15.0, "stats": {"armor": 1}, "cost": 10, "equipable": True},
    "bts002": {"name": "Тканые Тапочки", "type": ITEM_TYPE_BOOTS, "rarity": "common", "drop_chance": 15.0, "stats": {"max_energy_shield": 2}, "cost": 10, "equipable": True},
    "bts003": {"name": "Кожаные Ботинки", "type": ITEM_TYPE_BOOTS, "rarity": "common", "drop_chance": 10.0, "stats": {"armor": 3}, "cost": 25, "equipable": True},
    "bts004": {"name": "Солдатские Сапоги", "type": ITEM_TYPE_BOOTS, "rarity": "magic", "drop_chance": 8.0, "stats": {"armor": 5, "strength": 1}, "cost": 80, "equipable": True},
    "bts005": {"name": "Шерстяные Сапоги", "type": ITEM_TYPE_BOOTS, "rarity": "magic", "drop_chance": 7.0, "stats": {"max_energy_shield": 6, "intelligence": 1}, "cost": 85, "equipable": True},
    "bts006": {"name": "Ботинки Путника", "type": ITEM_TYPE_BOOTS, "rarity": "magic", "drop_chance": 6.0, "stats": {"armor": 3, "dexterity": 2}, "cost": 90, "equipable": True},
    "bts007": {"name": "Латные Сабатоны", "type": ITEM_TYPE_BOOTS, "rarity": "rare", "drop_chance": 4.0, "stats": {"armor": 10, "strength": 2, "max_hp": 5}, "cost": 280, "equipable": True},
    "bts008": {"name": "Сапоги Голема", "type": ITEM_TYPE_BOOTS, "rarity": "rare", "drop_chance": 3.0, "stats": {"armor": 8, "strength": 4}, "cost": 300, "equipable": True},
    "bts009": {"name": "Шелковые Туфли", "type": ITEM_TYPE_BOOTS, "rarity": "rare", "drop_chance": 2.0, "stats": {"max_energy_shield": 15, "intelligence": 3}, "cost": 320, "equipable": True},
    "bts010": {"name": "Сапоги-Скороходы", "type": ITEM_TYPE_BOOTS, "rarity": "rare", "drop_chance": 1.0, "stats": {"dexterity": 5, "armor": 5}, "cost": 800, "equipable": True},
# Кольца
    "rng001": {"name": "Железное Кольцо", "type": ITEM_TYPE_RING, "rarity": "common", "drop_chance": 10.0, "stats": {"strength": 1}, "cost": 40, "equipable": True},
    "rng002": {"name": "Медное Кольцо", "type": ITEM_TYPE_RING, "rarity": "common", "drop_chance": 10.0, "stats": {"armor": 2}, "cost": 40, "equipable": True},
    "rng003": {"name": "Коралловое Кольцо", "type": ITEM_TYPE_RING, "rarity": "common", "drop_chance": 10.0, "stats": {"max_hp": 5}, "cost": 50, "equipable": True},
    "rng004": {"name": "Кольцо с Лазуритом", "type": ITEM_TYPE_RING, "rarity": "common", "drop_chance": 10.0, "stats": {"max_mana": 5}, "cost": 50, "equipable": True},
    "rng005": {"name": "Нефритовое Кольцо", "type": ITEM_TYPE_RING, "rarity": "magic", "drop_chance": 8.0, "stats": {"dexterity": 2}, "cost": 100, "equipable": True},
    "rng006": {"name": "Рубиновое Кольцо", "type": ITEM_TYPE_RING, "rarity": "magic", "drop_chance": 7.0, "stats": {"strength": 2, "max_hp": 3}, "cost": 110, "equipable": True},
    "rng007": {"name": "Сапфировое Кольцо", "type": ITEM_TYPE_RING, "rarity": "magic", "drop_chance": 6.0, "stats": {"intelligence": 2, "max_mana": 4}, "cost": 110, "equipable": True},
    "rng008": {"name": "Кольцо Удачи", "type": ITEM_TYPE_RING, "rarity": "rare", "drop_chance": 4.0, "stats": {"dexterity": 3, "max_hp": 8}, "cost": 300, "equipable": True},
    "rng009": {"name": "Кольцо Силы Титана", "type": ITEM_TYPE_RING, "rarity": "rare", "drop_chance": 3.0, "stats": {"strength": 5, "armor": 4}, "cost": 350, "equipable": True},
    "rng010": {"name": "Кольцо Архимага", "type": ITEM_TYPE_RING, "rarity": "rare", "drop_chance": 2.0, "stats": {"intelligence": 4, "max_mana": 10, "max_energy_shield": 5}, "cost": 400, "equipable": True},
    "rng011": {"name": "Кольцо Двух Камней", "type": ITEM_TYPE_RING, "rarity": "rare", "drop_chance": 1.5, "stats": {"strength": 2, "intelligence": 2, "max_hp": 5, "max_mana": 5}, "cost": 450, "equipable": True},
    "rng012": {"name": "Кольцо Предвестника", "type": ITEM_TYPE_RING, "rarity": "rare", "drop_chance": 1.0, "stats": {"strength": 3, "dexterity": 3, "intelligence": 3}, "cost": 850, "equipable": True},
# Амулеты
    "amu001": {"name": "Веревка на шею", "type": ITEM_TYPE_AMULET, "rarity": "common", "drop_chance": 15.0, "stats": {}, "cost": 5, "equipable": True},
    "amu002": {"name": "Янтарный Амулет", "type": ITEM_TYPE_AMULET, "rarity": "common", "drop_chance": 12.0, "stats": {"strength": 2}, "cost": 60, "equipable": True},
    "amu003": {"name": "Нефритовый Амулет", "type": ITEM_TYPE_AMULET, "rarity": "common", "drop_chance": 12.0, "stats": {"dexterity": 2}, "cost": 60, "equipable": True},
    "amu004": {"name": "Лазуритовый Амулет", "type": ITEM_TYPE_AMULET, "rarity": "common", "drop_chance": 12.0, "stats": {"intelligence": 2}, "cost": 60, "equipable": True},
    "amu005": {"name": "Коралловый Амулет", "type": ITEM_TYPE_AMULET, "rarity": "magic", "drop_chance": 8.0, "stats": {"max_hp": 10}, "cost": 130, "equipable": True},
    "amu006": {"name": "Амулет Ученого", "type": ITEM_TYPE_AMULET, "rarity": "magic", "drop_chance": 7.0, "stats": {"intelligence": 3, "max_mana": 5}, "cost": 140, "equipable": True},
    "amu007": {"name": "Амулет Берсерка", "type": ITEM_TYPE_AMULET, "rarity": "magic", "drop_chance": 6.0, "stats": {"strength": 4, "max_hp": 5}, "cost": 150, "equipable": True},
    "amu008": {"name": "Амулет Следопыта", "type": ITEM_TYPE_AMULET, "rarity": "rare", "drop_chance": 4.0, "stats": {"dexterity": 5, "max_energy_shield": 5}, "cost": 400, "equipable": True},
    "amu009": {"name": "Золотой Амулет", "type": ITEM_TYPE_AMULET, "rarity": "rare", "drop_chance": 3.0, "stats": {"max_hp": 15, "max_mana": 10}, "cost": 450, "equipable": True},
    "amu010": {"name": "Амулет Равновесия", "type": ITEM_TYPE_AMULET, "rarity": "rare", "drop_chance": 1.0, "stats": {"strength": 4, "dexterity": 4, "intelligence": 4}, "cost": 950, "equipable": True},
# Пояса
    "blt001": {"name": "Простая саржа", "type": ITEM_TYPE_BELT, "rarity": "common", "drop_chance": 15.0, "stats": {}, "cost": 10, "equipable": True},
    "blt002": {"name": "Кожаный пояс", "type": ITEM_TYPE_BELT, "rarity": "common", "drop_chance": 12.0, "stats": {"max_hp": 8}, "cost": 35, "equipable": True},
    "blt003": {"name": "Тяжелый пояс", "type": ITEM_TYPE_BELT, "rarity": "common", "drop_chance": 12.0, "stats": {"strength": 2}, "cost": 45, "equipable": True},
    "blt004": {"name": "Крепкий Пояс", "type": ITEM_TYPE_BELT, "rarity": "magic", "drop_chance": 10.0, "stats": {"max_hp": 12, "strength": 1}, "cost": 120, "equipable": True},
    "blt005": {"name": "Пояс Странника", "type": ITEM_TYPE_BELT, "rarity": "magic", "drop_chance": 8.0, "stats": {"max_hp": 10, "dexterity": 2}, "cost": 130, "equipable": True},
    "blt006": {"name": "Тканый Пояс", "type": ITEM_TYPE_BELT, "rarity": "magic", "drop_chance": 7.0, "stats": {"max_mana": 10, "intelligence": 1}, "cost": 125, "equipable": True},
    "blt007": {"name": "Кольчужный Пояс", "type": ITEM_TYPE_BELT, "rarity": "rare", "drop_chance": 5.0, "stats": {"armor": 6, "max_hp": 10}, "cost": 350, "equipable": True},
    "blt008": {"name": "Пояс Чемпиона", "type": ITEM_TYPE_BELT, "rarity": "rare", "drop_chance": 4.0, "stats": {"strength": 5, "max_hp": 15}, "cost": 400, "equipable": True},
    "blt009": {"name": "Элегантный Пояс", "type": ITEM_TYPE_BELT, "rarity": "rare", "drop_chance": 3.0, "stats": {"dexterity": 3, "intelligence": 3, "max_energy_shield": 10}, "cost": 420, "equipable": True},
    "blt010": {"name": "Пояс Предка", "type": ITEM_TYPE_BELT, "rarity": "rare", "drop_chance": 1.0, "stats": {"strength": 3, "dexterity": 3, "intelligence": 3, "max_hp": 12}, "cost": 900, "equipable": True},
}

# --- Вспомогательная функция для получения случайного лута ---
# --- Обновляем ITEM_SLOTS для легендарок ---
# Проходим по легендаркам и добавляем их тип в ITEM_SLOTS
for item_id, item_data in ALL_ITEMS.items():
    if item_data.get('rarity') == 'legendary' and item_data.get('equipable'): # Только для надеваемых легендарок
        item_type = item_data.get('type') # Тип слота (helmet, ring...)
        # Определяем уникальный тип для легендарки этого слота
        legendary_item_type_key = f"legendary_{item_type}" # Например, legendary_gloves
        # Добавляем слот(ы) в ITEM_SLOTS для этого уникального типа
        if item_type == ITEM_TYPE_RING:
             ITEM_SLOTS[legendary_item_type_key] = [SLOT_RING1, SLOT_RING2]
        elif item_type in ITEM_SLOTS: # Если базовый тип известен
             ITEM_SLOTS[legendary_item_type_key] = ITEM_SLOTS[item_type]
        # else: Неизвестный базовый тип для легендарки

        # Перезаписываем тип самой легендарки на уникальный ключ
        # Это нужно, чтобы фильтровать их отдельно, если понадобится
        ALL_ITEMS[item_id]['type'] = legendary_item_type_key
        

# --- Константы для Магазинов/Гемблера/Кузнеца ---
SHOP_REFRESH_INTERVAL = 24 * 60 * 60 # 24 часа в секундах
SHOP_WEAPON_ITEMS = 5 # Количество оружий в магазине
SHOP_ARMOR_ITEMS = 5 # Количество брони (шлем, тело, перч, бот)
SHOP_LEGENDARY_CHANCE = 0.01 # 1% шанс на легендарку в обычном магазине

GAMBLER_BOX_COSTS = { # Стоимость коробок
    "small": 100,
    "medium": 500,
    "large": 2000
}
# Шансы наград Гемблера (сумма должна быть 100)
GAMBLER_REWARD_CHANCES = {
    "xp": 30,       # Шанс получить опыт
    "gold": 45,     # Шанс получить золото
    "item": 25      # Шанс получить предмет
}
# Шансы для предмета от Гемблера
GAMBLER_ITEM_CHANCES = {
    "common": 60,
    "magic": 25,
    "rare": 10,
    "fragment": 4, # Шанс на фрагмент
    "legendary": 1  # Шанс на легендарку
}

BLACKSMITH_ITEMS_COUNT = 3 # Количество легендарок у кузнеца
BLACKSMITH_REFRESH_INTERVAL = 24 * 60 * 60 # 24 часа
BLACKSMITH_CRAFT_COST = 5 # Сколько фрагментов нужно для крафта

# --- Функция дропа ---
def get_random_loot_item_id() -> str | None:
    # ... (остается без изменений, она выбирает из ALL_ITEMS) ...
    if random.random() > 0.5:
        return None
    items_list = list(ALL_ITEMS.items())
    # Исключаем фрагменты и легендарки из ОБЫЧНОГО дропа
    eligible_items = [(id, data) for id, data in items_list if data.get('type') != ITEM_TYPE_FRAGMENT and data.get('rarity') != 'legendary']
    if not eligible_items: return None

    chances = [item_data["drop_chance"] for _, item_data in eligible_items]
    item_ids = [item_id for item_id, _ in eligible_items]

    chosen_id_list = random.choices(item_ids, weights=chances, k=1)
    return chosen_id_list[0] if chosen_id_list else None

def calculate_final_spell_damage(base_damage: int, intelligence: int) -> int:
    """Рассчитывает финальный урон заклинания с учетом интеллекта (БЕЗ КРИТА)."""
    multiplier = 1 + intelligence * SPELL_DAMAGE_INTELLIGENCE_SCALING
    final_base_damage = math.ceil(base_damage * multiplier)
    # Убрал лог отсюда, чтобы не спамить
    return final_base_damage
# --- Функция дропа Легендарки (для боссов) ---
# --- !!! НОВАЯ ФУНКЦИЯ ДЛЯ КРИТА !!! ---
def calculate_damage_with_crit(base_damage: int, crit_chance: float, crit_multiplier: float) -> tuple[int, bool]:
    """
    Рассчитывает финальный урон, учитывая шанс и множитель крита.
    Возвращает кортеж (финальный_урон, был_ли_крит).
    """
    is_crit = random.uniform(0, 100) < crit_chance
    if is_crit:
        # Применяем множитель (например, 150.0 -> 1.5)
        final_damage = math.ceil(base_damage * (crit_multiplier / 100.0))
        logging.debug(f"Crit! Base: {base_damage}, Multi: {crit_multiplier}%, Final: {final_damage}")
        return final_damage, True # Урон, БылКрит=True
    else:
        # Если крита нет, возвращаем базовый урон
        return base_damage, False # Урон, БылКрит=False
# --- КОНЕЦ НОВОЙ ФУНКЦИИ ---
def get_random_legendary_item_id() -> str | None:
    """Возвращает ID случайного легендарного предмета."""
    legendary_ids = [item_id for item_id, data in ALL_ITEMS.items() if data.get('rarity') == 'legendary']
    if not legendary_ids:
        return None
    return random.choice(legendary_ids)
