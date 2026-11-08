"""One shared tag list for all sites.

Every site labels things its own way ("ЛитРПГ", "LitRPG", "LITRPG", "Элементы РПГ"...). Each raw label is
reduced to a key (lowercase, letters and digits only), looked up among the synonyms below and mapped to a
shared tag. Labels we don't know stay as their own tag, so nothing is lost.

Rules then add implied tags: a LitRPG book also gets "RPG / game elements", a romantic fantasy gets both
"Romance" and "Fantasy", and so on. You can add your own synonyms and rules in data/my_tags.toml.
"""
import json
import os
import re
import tomllib
from functools import lru_cache

from . import config

# id: (English label, Russian label, category, synonyms in any language)
TAGS: dict[str, tuple[str, str, str, list[str]]] = {
    # --- narration ---
    "pov-first": ("First person", "От первого лица", "narration", [
        "от первого лица", "повествование от первого лица", "первое лицо", "от 1 лица", "от 1-го лица",
        "1 лицо", "рассказ от первого лица", "повествование от 1 лица", "first person", "first-person",
        "first person pov", "pov first person", "pov: first person", "first-person narrator",
        "first person narrator", "first person narrative", "1st person", "1st person pov", "first pov",
        "від першої особи", "розповідь від першої особи", "оповідь від першої особи"]),
    "pov-third": ("Third person", "От третьего лица", "narration", [
        "от третьего лица", "повествование от третьего лица", "третье лицо", "от 3 лица", "от 3-го лица",
        "third person", "third-person", "third person pov", "pov third person", "third person limited",
        "third person omniscient", "3rd person", "3rd person pov", "від третьої особи"]),
    "pov-second": ("Second person", "От второго лица", "narration", [
        "от второго лица", "повествование от второго лица", "второе лицо", "second person",
        "second-person", "second person pov", "pov second person", "2nd person", "reader-insert",
        "reader insert", "x reader", "від другої особи"]),
    "multiple-pov": ("Multiple points of view", "Несколько точек зрения", "narration", [
        "multiple pov", "multiple povs", "multiple points of view", "multiple lead characters",
        "смена пов", "смена точек зрения", "разные точки зрения", "несколько пов", "пов нескольких персонажей",
        "pov разных персонажей", "смена фокальных персонажей", "multi pov"]),
    "present-tense": ("Present tense", "Настоящее время", "narration", [
        "present tense", "настоящее время", "повествование в настоящем времени"]),
    # --- protagonist ---
    "male-lead": ("Male lead", "ГГ мужчина", "protagonist", [
        "гг мужчина", "главный герой мужчина", "гг парень", "male protagonist", "male lead", "male mc",
        "malelead", "main character male", "гг мужского пола", "герой мужчина", "мужской персонаж гг",
        "головний герой чоловік"]),
    "female-lead": ("Female lead", "ГГ женщина", "protagonist", [
        "гг женщина", "главная героиня", "гг девушка", "female protagonist", "female lead", "female mc",
        "femalelead", "main character female", "героиня", "сильная героиня", "головна героїня"]),
    "op-lead": ("Overpowered lead", "Сильный ГГ / имба", "protagonist", [
        "гг имба", "имба", "сильный гг", "сильный главный герой", "сильный герой", "overpowered protagonist",
        "overpowered", "op mc", "op protagonist", "overpowered mc", "strong lead", "strong protagonist",
        "очень сильный гг", "непобедимый гг", "сильная героиня гг"]),
    "progression": ("Progression / power growth", "Прокачка / рост силы", "protagonist", [
        "progression", "progression fantasy", "прокачка", "рост силы", "от слабого к сильному", "weak to strong",
        "weaktostrong", "характерный рост", "character growth", "развитие главного героя", "развитие гг",
        "развитие персонажа", "постепенное развитие", "гг развивается", "слабый гг в начале"]),
    "smart-lead": ("Smart lead", "Умный ГГ", "protagonist", [
        "умный гг", "умный главный герой", "умная героиня", "clever protagonist", "smart mc", "smart protagonist",
        "расчетливый гг"]),
    "villain-lead": ("Villain lead", "ГГ злодей", "protagonist", [
        "гг злодей", "главный герой злодей", "villain protagonist", "villainous lead", "evil protagonist",
        "темный гг", "злой гг"]),
    "anti-hero": ("Anti-hero", "Антигерой", "protagonist", [
        "антигерой", "anti-hero", "antihero", "anti-hero lead", "гг антигерой",
        "беспринципный гг", "циничный гг"]),
    "nonhuman-lead": ("Non-human lead", "ГГ не человек", "protagonist", [
        "гг не человек", "нечеловеческий главный герой", "non-human protagonist", "nonhuman protagonist",
        "non-human lead", "monster protagonist", "гг монстр", "гг нежить", "гг дракон", "гг паук"]),
    "gender-bender": ("Gender bender", "Смена пола", "protagonist", [
        "gender bender", "смена пола", "гендербендер", "genderswap", "gender swap", "перерождение в девушку"]),
    "hidden-identity": ("Secret identity", "Скрытие личности", "protagonist", [
        "скрытие личности", "скрытая личность", "secret identity", "hidden identity", "hiding true abilities",
        "скрывает силу", "скрытие силы"]),
    # --- genres ---
    "fantasy": ("Fantasy", "Фэнтези", "genre", [
        "фэнтези", "фентези", "фэнтэзи", "fantasy", "high fantasy", "low fantasy", "высокое фэнтези",
        "низкое фэнтези", "фантэзи"]),
    "sci-fi": ("Science fiction", "Фантастика", "genre", [
        "фантастика", "научная фантастика", "нф", "sci-fi", "science fiction", "scifi", "soft sci-fi",
        "hard sci-fi", "твердая научная фантастика", "социальная фантастика", "наукова фантастика"]),
    "litrpg": ("LitRPG", "ЛитРПГ", "genre", [
        "литрпг", "лит рпг", "лит-рпг", "litrpg", "lit-rpg", "lit rpg", "литрпг фэнтези", "реалрпг", "realrpg",
        "real rpg"]),
    "gamelit": ("GameLit", "Геймлит", "genre", ["gamelit", "геймлит", "game lit", "game literature"]),
    "rpg-elements": ("RPG / game elements", "Элементы РПГ", "theme", [
        "элементы рпг", "rpg elements", "rpg", "рпг", "игровые элементы", "game elements", "level system",
        "система уровней", "уровни", "статы", "characteristics", "skills"]),
    "system": ("System", "Система", "theme", [
        "система", "system", "игровая система", "системный", "system administrator", "system invasion",
        "интерфейс", "the system", "system novel"]),
    "game-messages": ("Game messages in text", "Игровые сообщения в тексте", "theme", []),
    "virtual-reality": ("Virtual reality", "Виртуальная реальность", "setting", [
        "виртуальная реальность", "virtual reality", "vrmmo", "vrmmorpg", "vr", "виртуальный мир",
        "mmorpg", "ммо", "ммо рпг", "вирт", "virtual world", "full dive"]),
    "isekai": ("Another world / Isekai", "Попаданцы", "theme", [
        "попаданцы", "попаданец", "попаданство", "попадалово", "isekai", "исекай", "иссекай",
        "другой мир", "путешествие в другой мир", "перенос в другой мир", "transported to another world",
        "transported into another world", "another world", "попаданцы в магические миры",
        "попаданцы в другие миры", "portal fantasy", "portal fantasy isekai", "summoned hero", "призыв героя",
        "призыв в другой мир", "попаданцы в иные миры", "попаданці"]),
    "reincarnation": ("Reincarnation", "Реинкарнация / перерождение", "theme", [
        "реинкарнация", "перерождение", "переродился", "переродилась", "reincarnation", "reincarnated",
        "rebirth", "reborn", "новая жизнь", "перерождение в другом мире", "реінкарнація", "переродження"]),
    "transmigration": ("Transmigration (into another body)", "Вселение в чужое тело", "theme", [
        "transmigration", "трансмиграция", "вселение в тело", "в чужом теле", "попадание в тело",
        "переселение души", "переселение в тело", "body swap", "обмен телами"]),
    "regression": ("Regression / second chance", "Регрессия / второй шанс", "theme", [
        "регрессия", "регрессор", "возвращение в прошлое", "regression", "regressor", "second chance",
        "второй шанс", "returning", "time loop", "временная петля", "loop", "петля времени", "день сурка"]),
    "time-travel": ("Time travel", "Путешествие во времени", "theme", [
        "путешествие во времени", "путешествия во времени", "попаданцы во времени", "time travel",
        "попаданцы в прошлое", "попаданец в прошлое", "в прошлое", "хроноопера"]),
    "into-game": ("Trapped in a game", "Попаданец в игру", "theme", [
        "попаданцы в игру", "попаданец в игру", "попаданка в игру", "transported into a game world",
        "trapped in a game", "game world", "игровой мир", "в мире игры"]),
    "into-book": ("Inside a novel", "Попаданец в книгу", "theme", [
        "попаданцы в книгу", "попаданка в книгу", "попаданец в книгу", "попаданцы в роман",
        "transported into a novel", "into a novel", "book transmigration", "в мире книги", "в мире романа"]),
    "alt-history": ("Alternate history", "Альтернативная история", "genre", [
        "альтернативная история", "альтистория", "альт история", "alternate history", "alternative history",
        "альтернативна історія"]),
    "boyar-anime": ("Boyar-anime", "Бояръ-Аниме", "genre", ["бояръ-аниме", "бояр аниме", "бояръ аниме",
                                                             "боярь аниме", "бояраниме"]),
    "apocalypse": ("Apocalypse / post-apocalypse", "(Пост)апокалипсис", "genre", [
        "постапокалипсис", "постапокалиптика", "постап", "апокалипсис", "post-apocalyptic", "post apocalyptic",
        "postapocalyptic", "apocalypse", "конец света", "постапокаліпсис", "апокаліпсис"]),
    "dystopia": ("Dystopia", "Антиутопия", "genre", ["антиутопия", "dystopia", "антиутопія"]),
    "cyberpunk": ("Cyberpunk", "Киберпанк", "genre", ["киберпанк", "cyberpunk", "кіберпанк"]),
    "steampunk": ("Steampunk", "Стимпанк", "genre", ["стимпанк", "steampunk", "паропанк"]),
    "space": ("Space", "Космос", "setting", [
        "космос", "космическая фантастика", "space", "космическое", "космические корабли", "spaceship",
        "звездолеты", "first contact", "первый контакт"]),
    "space-opera": ("Space opera", "Космоопера", "genre", ["космоопера", "космическая опера", "space opera"]),
    "military": ("Military", "Военное", "genre", [
        "военная фантастика", "боевая фантастика", "military", "военное", "war and military", "армия",
        "военные", "военная проза", "military sci-fi", "military fantasy"]),
    "war": ("War", "Война", "theme", ["война", "war", "wars", "военные действия", "войны", "війна"]),
    "action": ("Action", "Боевик / экшн", "genre", [
        "боевик", "экшн", "экшен", "action", "боевое фэнтези", "бойовик"]),
    "adventure": ("Adventure", "Приключения", "genre", [
        "приключения", "приключенческое фэнтези", "adventure", "adventures", "пригоди", "приключенческое"]),
    "romance": ("Romance", "Любовный роман / романтика", "genre", [
        "любовный роман", "романтика", "romance", "romantic", "любовь", "романтическое",
        "love", "современный любовный роман", "короткий любовный роман", "любовні романи",
        "любовний роман", "романтика (жанр)"]),
    "romantic-fantasy": ("Romantic fantasy", "Любовное фэнтези", "genre", [
        "любовное фэнтези", "романтическое фэнтези", "romantic fantasy", "romance fantasy", "любовна фантастика",
        "любовная фантастика", "романтическая фантастика", "любовне фентезі"]),
    "drama": ("Drama", "Драма", "genre", ["драма", "drama"]),
    "angst": ("Angst", "Ангст", "genre", ["ангст", "angst"]),
    "fluff": ("Fluff", "Флафф", "genre", ["флафф", "fluff"]),
    "hurt-comfort": ("Hurt/Comfort", "Hurt/Comfort", "genre", ["hurt/comfort", "hurt comfort", "hurtcomfort"]),
    "comedy": ("Comedy / humor", "Юмор", "genre", [
        "комедия", "юмор", "юмористическое фэнтези", "юмористическая фантастика", "юмористическое",
        "humor", "humour", "comedy", "стеб", "стёб", "пародия", "parody", "satire", "сатира", "гумор"]),
    "horror": ("Horror", "Ужасы", "genre", ["ужасы", "хоррор", "horror", "жахи", "хорор"]),
    "mystery": ("Mystery / detective", "Детектив", "genre", [
        "детектив", "mystery", "detective", "расследование", "фантастический детектив", "детективное фэнтези",
        "магический детектив", "детектив (жанр)"]),
    "thriller": ("Thriller", "Триллер", "genre", ["триллер", "thriller", "трилер"]),
    "supernatural": ("Supernatural / mystic", "Мистика", "genre", [
        "мистика", "mystic", "mysticism", "supernatural", "сверхъестественное", "паранормальное",
        "paranormal", "містика"]),
    "psychological": ("Psychological", "Психология", "genre", [
        "психология", "психологическое", "psychological", "психологический", "психологія"]),
    "philosophy": ("Philosophy", "Философия", "genre", ["философия", "philosophy", "философское"]),
    "tragedy": ("Tragedy", "Трагедия", "genre", ["трагедия", "tragedy", "трагедія"]),
    "slice-of-life": ("Slice of life", "Повседневность", "genre", [
        "повседневность", "slice of life", "повседневная жизнь", "бытовое фэнтези", "бытовая магия",
        "уютное", "cozy", "cozy fantasy", "буденність"]),
    "school-life": ("School life", "Школьная жизнь", "setting", [
        "школа", "школьная жизнь", "school life", "школьники", "учебные заведения", "студенты", "университет",
        "college", "university"]),
    "academy": ("Academy", "Академия", "setting", [
        "академия", "академия магии", "magic academy", "academy", "магическая школа", "школа магии",
        "магічна академія"]),
    "urban-fantasy": ("Urban fantasy", "Городское фэнтези", "genre", [
        "городское фэнтези", "urban fantasy", "міське фентезі"]),
    "dark-fantasy": ("Dark fantasy", "Тёмное фэнтези", "genre", [
        "темное фэнтези", "dark fantasy", "grimdark", "мрачное фэнтези", "грязное фэнтези", "темне фентезі"]),
    "epic-fantasy": ("Epic fantasy", "Эпическое фэнтези", "genre", ["эпическое фэнтези", "epic fantasy",
                                                                    "епічне фентезі"]),
    "heroic-fantasy": ("Heroic fantasy", "Героическое фэнтези", "genre", ["героическое фэнтези", "heroic fantasy",
                                                                          "героїчне фентезі"]),
    "historical": ("Historical", "Исторический", "genre", [
        "исторический", "исторический роман", "историческое фэнтези", "historical", "history",
        "исторические", "історичний", "исторический любовный роман", "историческая проза"]),
    "wuxia": ("Wuxia", "Уся", "genre", ["уся", "wuxia"]),
    "xianxia": ("Xianxia", "Сянься", "genre", ["сянься", "xianxia"]),
    "xuanhuan": ("Xuanhuan", "Сюаньхуань", "genre", ["сюаньхуань", "xuanhuan"]),
    "cultivation": ("Cultivation", "Культивация", "theme", [
        "культивация", "cultivation", "совершенствование", "путь совершенствования", "культивація"]),
    "martial-arts": ("Martial arts", "Боевые искусства", "theme", [
        "боевые искусства", "martial arts", "восточные единоборства", "бойові мистецтва"]),
    "magic": ("Magic", "Магия", "theme", [
        "магия", "маги", "magic", "волшебство", "magical", "магическое", "колдовство", "чародейство",
        "магія", "magic system"]),
    "mecha": ("Mecha", "Меха", "theme", ["меха", "mecha", "роботы", "robots", "мехи"]),
    "vampires": ("Vampires", "Вампиры", "theme", ["вампиры", "vampires", "vampire", "вампир", "вампіри"]),
    "werewolves": ("Werewolves / shifters", "Оборотни", "theme", [
        "оборотни", "werewolves", "werewolf", "shapeshifters", "shifters", "оборотень", "перевертні"]),
    "dragons": ("Dragons", "Драконы", "theme", ["драконы", "dragons", "dragon", "дракон", "дракони"]),
    "demons": ("Demons", "Демоны", "theme", ["демоны", "demons", "demon", "демон", "владыка демонов",
                                            "demon lord", "демони"]),
    "elves": ("Elves", "Эльфы", "theme", ["эльфы", "elves", "elf", "эльф", "ельфи"]),
    "gods": ("Gods", "Боги", "theme", ["боги", "gods", "божества", "deities", "бог", "боги и богини"]),
    "monsters": ("Monsters", "Монстры", "theme", ["монстры", "monsters", "чудовища", "монстри"]),
    "undead": ("Undead", "Нежить", "theme", ["нежить", "undead", "зомби", "zombies", "zombie", "нежить и зомби"]),
    "necromancy": ("Necromancy", "Некромантия", "theme", ["некромант", "некромантия", "necromancer", "necromancy"]),
    "dungeon": ("Dungeons", "Подземелья", "theme", [
        "подземелья", "подземелье", "данжи", "данжен", "dungeon", "dungeons", "dungeon core", "towers", "башня"]),
    "survival": ("Survival", "Выживание", "theme", ["выживание", "survival", "виживання"]),
    "kingdom-building": ("Kingdom / base building", "Строительство королевства", "theme", [
        "строительство королевства", "развитие королевства", "kingdom building", "kingdombuilding",
        "построение империи", "строительство", "base building", "basebuilding", "строительство базы",
        "развитие поселения", "управление поселением", "ruling class", "градостроительство", "лорд"]),
    "progressorism": ("Modern knowledge / progressor", "Прогрессорство", "theme", [
        "прогрессорство", "прогрессор", "modern knowledge", "современные знания", "uplift"]),
    "crafting": ("Crafting", "Крафт", "theme", ["крафт", "крафтинг", "crafting", "ремесло", "кузнец",
                                               "blacksmith", "алхимия", "alchemy"]),
    "harem": ("Harem", "Гарем", "theme", ["гарем", "harem", "гаремник", "harem-seeking protagonist"]),
    "reverse-harem": ("Reverse harem", "Обратный гарем", "theme", ["обратный гарем", "reverse harem"]),
    "no-harem": ("No harem", "Без гарема", "theme", ["без гарема", "no harem", "nonharem", "не гарем"]),
    "villainess": ("Villainess", "Злодейка", "theme", ["злодейка", "villainess", "отыгрывая злодейку",
                                                      "злодійка"]),
    "revenge": ("Revenge", "Месть", "theme", ["месть", "revenge", "помста"]),
    "politics": ("Politics / intrigue", "Политика / интриги", "theme", [
        "политика", "политические интриги", "интриги", "politics", "political intrigue", "politic",
        "дворцовые интриги", "заговоры"]),
    "aristocracy": ("Aristocracy", "Аристократия", "theme", [
        "аристократия", "дворянство", "nobility", "aristocracy", "nobles", "аристократ", "аристократы",
        "знать", "кланы", "аристократичні", "дворяни"]),
    "modern-day": ("Modern day", "Современность", "setting", [
        "современность", "современный мир", "modern day", "modern setting", "contemporary", "наши дни",
        "сучасність"]),
    "medieval": ("Medieval", "Средневековье", "setting", ["средневековье", "medieval", "средние века"]),
    "mythology": ("Mythology", "Мифология", "theme", ["мифология", "mythology", "mythos", "мифы", "фольклор",
                                                     "славянское фэнтези", "славянская мифология"]),
    "superheroes": ("Superheroes", "Супергерои", "theme", ["супергерои", "superheroes", "super heroes"]),
    "family": ("Family", "Семья", "theme", ["семья", "family", "дети", "отцы и дети"]),
    "cooking": ("Cooking", "Кулинария", "theme", ["кулинария", "cooking", "еда", "food"]),
    "sports": ("Sports", "Спорт", "theme", ["спорт", "sports"]),
    "music": ("Music", "Музыка", "theme", ["музыка", "music"]),
    "ai": ("Artificial intelligence", "Искусственный интеллект", "theme", [
        "искусственный интеллект", "artificial intelligence", "ии", "ai"]),
    # --- relationships ---
    "slash": ("Boys' love / slash", "Слэш", "relationship", [
        "слэш", "слеш", "slash", "яой", "yaoi", "bl", "boys love", "boys' love", "сёнэн-ай", "сенэн-ай",
        "shounen ai", "shonen ai", "m/m", "мм"]),
    "femslash": ("Girls' love / femslash", "Фемслэш", "relationship", [
        "фемслэш", "фемслеш", "femslash", "юри", "yuri", "gl", "girls love", "girls' love", "сёдзё-ай",
        "shoujo ai", "f/f"]),
    "het": ("Het", "Гет", "relationship", ["гет", "het", "f/m", "m/f"]),
    "gen": ("Gen (no romance)", "Джен", "relationship", ["джен", "gen", "no romance", "без романтики",
                                                        "без любовной линии"]),
    "lgbt": ("LGBTQ+", "ЛГБТ", "relationship", ["лгбт", "lgbt", "lgbtq", "lgbtqa", "lgbtqa+", "queer"]),
    # --- content ---
    "adult": ("Adult content (18+)", "Для взрослых (18+)", "content", [
        "эротика", "эротическое фэнтези", "erotica", "smut", "18+", "r18", "r-18", "nc-17", "nc-21",
        "adult", "explicit", "эротическая фантастика", "откровенные сцены", "лемон"]),
    "violence": ("Graphic violence", "Насилие / жестокость", "content", [
        "насилие", "жестокость", "graphic violence", "gore", "violence", "кровь", "расчлененка", "жорстокість"]),
    # --- origin & format ---
    "fanfiction": ("Fanfiction", "Фанфик", "format", [
        "фанфик", "фанфики", "фанфикшн", "fanfiction", "fan fiction", "fanfic", "фанфік", "фанфіки"]),
    "original": ("Original work", "Ориджинал", "format", ["ориджинал", "ориджиналы", "original", "originals",
                                                         "авторское", "авторский", "оригінал"]),
    "translation": ("Translation", "Перевод", "format", ["перевод", "translation", "translated", "переклад"]),
    "short-story": ("Short story", "Рассказ", "format", [
        "рассказ", "рассказы", "short story", "one shot", "one-shot", "oneshot", "драббл", "drabble",
        "мини", "оповідання", "новелла (рассказ)"]),
    "poetry": ("Poetry", "Поэзия", "format", ["поэзия", "стихи", "poetry", "поезія", "вірші"]),
    "chinese-novel": ("Chinese novel", "Китайская новелла", "origin", ["китай", "китайская новелла",
                                                                       "chinese", "chinese novel", "cn"]),
    "korean-novel": ("Korean novel", "Корейская новелла", "origin", ["корея", "корейская новелла",
                                                                     "korean", "korean novel", "kr"]),
    "japanese-novel": ("Japanese light novel", "Японское ранобэ", "origin", [
        "япония", "японское ранобэ", "japanese", "japanese novel", "jp"]),
    "english-novel": ("English web novel", "Англоязычная новелла", "origin", ["английский", "english novel",
                                                                            "english web novel"]),
    "demographic-shounen": ("Shounen", "Сёнэн", "demographic", ["сёнэн", "сенэн", "shounen", "shonen"]),
    "demographic-seinen": ("Seinen", "Сэйнэн", "demographic", ["сэйнэн", "сейнен", "seinen"]),
    "demographic-shoujo": ("Shoujo", "Сёдзё", "demographic", ["сёдзё", "седзе", "shoujo", "shojo"]),
    "demographic-josei": ("Josei", "Дзёсэй", "demographic", ["дзёсэй", "дзесей", "josei"]),
    "young-adult": ("Young adult", "Подростковое", "demographic", [
        "подростковое", "young adult", "ya", "подростковая проза", "подростковая литература", "для подростков"]),
    "au": ("Alternate universe (fanfic)", "AU", "fanfic", ["au", "alternate universe", "альтернативная вселенная"]),
    "ooc": ("Out of character (fanfic)", "ООС", "fanfic", ["ooc", "оос", "out of character"]),
}

# One label that means several tags at once.
COMPOUND: dict[str, list[str]] = {
    "магическая академия": ["academy", "magic"],
    "академия магии": ["academy", "magic"],
    "попаданка": ["isekai", "female-lead"],
    "попаданка в другой мир": ["isekai", "female-lead"],
    "попаданка в магический мир": ["isekai", "female-lead", "magic"],
    "попаданец в магический мир": ["isekai", "male-lead", "magic"],
    "попаданцы в магические миры": ["isekai", "magic"],
    "попаданцы в космос": ["isekai", "space"],
    "попаданцы в прошлое": ["time-travel", "isekai"],
    "зомби-апокалипсис": ["undead", "apocalypse"],
    "зомби апокалипсис": ["undead", "apocalypse"],
    "zombie apocalypse": ["undead", "apocalypse"],
    "магия и приключения": ["magic", "adventure"],
    "космическая фантастика": ["space", "sci-fi"],
    "боевая фантастика": ["military", "sci-fi", "action"],
    "военная фантастика": ["military", "sci-fi"],
    "историческое фэнтези": ["historical", "fantasy"],
    "юмористическое фэнтези": ["comedy", "fantasy"],
    "юмористическая фантастика": ["comedy", "sci-fi"],
    "фантастический детектив": ["mystery", "sci-fi"],
    "детективное фэнтези": ["mystery", "fantasy"],
    "магический детектив": ["mystery", "magic", "fantasy"],
    "приключенческое фэнтези": ["adventure", "fantasy"],
    "боевое фэнтези": ["action", "fantasy"],
    "эротическое фэнтези": ["adult", "fantasy"],
    "эротическая фантастика": ["adult", "sci-fi"],
    "исторический любовный роман": ["historical", "romance"],
    "современный любовный роман": ["romance", "modern-day"],
    "перерождение в другом мире": ["reincarnation", "isekai"],
    "перерождение в девушку": ["gender-bender", "reincarnation"],
    "гг паук": ["nonhuman-lead"],
    "сильная героиня": ["female-lead", "op-lead"],
    "сильная героиня гг": ["female-lead", "op-lead"],
    "сильный герой": ["op-lead"],
    "military sci-fi": ["military", "sci-fi"],
    "military fantasy": ["military", "fantasy"],
    "soft sci-fi": ["sci-fi"],
    "hard sci-fi": ["sci-fi"],
    "portal fantasy isekai": ["isekai", "fantasy"],
    "cozy fantasy": ["slice-of-life", "fantasy"],
    "славянское фэнтези": ["mythology", "fantasy"],
}

# Books with the tag on the left also get the tags on the right (applied repeatedly).
RULES: dict[str, list[str]] = {
    "litrpg": ["rpg-elements", "gamelit"],
    "gamelit": ["rpg-elements"],
    "system": ["rpg-elements"],
    "game-messages": ["rpg-elements"],
    "into-game": ["isekai", "rpg-elements"],
    "into-book": ["isekai"],
    "romantic-fantasy": ["romance", "fantasy"],
    "urban-fantasy": ["fantasy"],
    "dark-fantasy": ["fantasy"],
    "epic-fantasy": ["fantasy"],
    "heroic-fantasy": ["fantasy"],
    "xianxia": ["cultivation", "fantasy"],
    "xuanhuan": ["fantasy"],
    "cultivation": ["fantasy"],
    "wuxia": ["martial-arts"],
    "space-opera": ["sci-fi", "space"],
    "cyberpunk": ["sci-fi"],
    "boyar-anime": ["alt-history", "magic", "aristocracy"],
    "villainess": ["female-lead"],
    "reverse-harem": ["romance"],
    "slash": ["lgbt"],
    "femslash": ["lgbt"],
    "necromancy": ["magic"],
    "vampires": ["supernatural"],
    "werewolves": ["supernatural"],
    "academy": ["school-life"],
}

CATEGORY_ORDER = ["narration", "genre", "theme", "protagonist", "setting", "orientation", "relationship",
                  "content", "format", "origin", "demographic", "fandom", "fanfic", "other"]

# The rest of the list (tropes, settings, content notes, fandoms, Ukrainian names) lives in tagdata.py;
# descriptions, contradictions and extra family links in tagdocs.py.
from .tagdata import MORE_COMPOUND, MORE_RULES, MORE_SYNONYMS, MORE_TAGS, UK  # noqa: E402
from . import tagdocs  # noqa: E402
from .tagdocs import ANTI, CATEGORY_OVERRIDES, DESCRIPTIONS, MORE_FAMILY  # noqa: E402

ORIENTATION = tagdocs.ORIENTATION  # the Orientation filter's tags, for the web app

TAGS.update(MORE_TAGS)
for _tid, _extra in MORE_SYNONYMS.items():
    _en, _ru, _cat, _syn = TAGS[_tid]
    TAGS[_tid] = (_en, _ru, _cat, [*_syn, *_extra])
for _tid, _cat in CATEGORY_OVERRIDES.items():
    _en, _ru, _old, _syn = TAGS[_tid]
    TAGS[_tid] = (_en, _ru, _cat, _syn)
COMPOUND.update(MORE_COMPOUND)
for _source in (MORE_RULES, MORE_FAMILY):
    for _tid, _extra in _source.items():
        RULES[_tid] = list(dict.fromkeys([*RULES.get(_tid, []), *_extra]))

# Bump when the built-in list changes: every book's site labels are then mapped again on the next start.
TAGS_VERSION = 4

# Sites name fandoms freely ("Ведьмак", "The Witcher"). Connectors pass them as "fandom:<name>": a fandom we know
# becomes its shared tag, any other becomes a tag of its own in the Fandoms category.
FANDOM_PREFIX = "fandom:"

_KEY_RE = re.compile(r"[^0-9a-zа-яіїєґ+]+")


def key(label: str) -> str:
    """Reduce a label to letters and digits so 'Lit-RPG', 'LITRPG' and 'lit rpg' all match."""
    s = label.lower().replace("ё", "е").strip().lstrip("#")
    return _KEY_RE.sub("", s)


def _user_config() -> dict:
    path = config.USER_TAGS_FILE
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


@lru_cache(maxsize=1)
def _tables():
    """(synonym key -> [tag ids], rules, tag info). Built-in data plus the user's my_tags.toml."""
    user = _user_config()
    info = {tid: {"label": en, "label_ru": ru, "label_uk": UK.get(tid), "category": cat}
            for tid, (en, ru, cat, _) in TAGS.items()}
    for tid, extra in (user.get("tags") or {}).items():
        if isinstance(extra, dict):
            base = info.setdefault(tid, {"label": tid, "label_ru": None, "label_uk": None, "category": "other"})
            base.update({k: v for k, v in extra.items() if k in ("label", "label_ru", "label_uk", "category")})
    syn: dict[str, list[str]] = {}
    for tid, (en, ru, _cat, synonyms) in TAGS.items():
        for s in [tid, en, ru, UK.get(tid) or "", *synonyms]:
            if key(s):
                syn.setdefault(key(s), [tid])
    for label, ids in COMPOUND.items():
        syn[key(label)] = list(ids)
    for label, ids in (user.get("synonyms") or {}).items():
        syn[key(label)] = [ids] if isinstance(ids, str) else list(ids)
    for label, ids in (user.get("fixes") or {}).items():  # made on the Fix labels page; they win
        syn[key(label)] = [ids] if isinstance(ids, str) else list(ids)
    rules = {k: list(v) for k, v in RULES.items()}
    for k, v in (user.get("rules") or {}).items():
        rules.setdefault(k, [])
        rules[k] += [v] if isinstance(v, str) else list(v)
    return syn, rules, info


def reload() -> None:
    _tables.cache_clear()
    _children_index.cache_clear()
    _alias_index.cache_clear()


def canonical(label: str) -> list[str]:
    """Shared tag ids for a label as written on a site. Unknown labels become their own tag."""
    if label.lower().startswith(FANDOM_PREFIX):
        name = label[len(FANDOM_PREFIX):].strip()
        known = [t for t in canonical(name) if is_known(t) and info(t)["category"] == "fandom"] if name else []
        return known or ([FANDOM_PREFIX + name.lower().replace("ё", "е")] if name else [])
    k = key(label)
    if not k:
        return []
    syn, _, _ = _tables()
    if k in syn:
        return syn[k]
    # Bilingual labels such as "Naruto / Наруто" or "Фэнтези | Fantasy": use whichever side is known.
    parts = [p for p in re.split(r"\s+[/|]\s+", label) if p.strip()]
    if len(parts) > 1:
        known = [t for p in parts for t in syn.get(key(p), [])]
        if known:
            return list(dict.fromkeys(known))
    return [label.strip().lower().replace("ё", "е")]


def implied(tag_ids: set[str]) -> set[str]:
    """Tags added by the rules (not including the ones you passed in)."""
    out: set[str] = set()
    todo = list(tag_ids)
    while todo:
        t = todo.pop()
        for extra in parents(t):
            if extra not in tag_ids and extra not in out:
                out.add(extra)
                todo.append(extra)
    return out


def info(tag_id: str) -> dict:
    _, _, tag_info = _tables()
    if tag_id in tag_info:
        return tag_info[tag_id]
    if tag_id.startswith(FANDOM_PREFIX):
        return {"label": tag_id[len(FANDOM_PREFIX):], "label_ru": None, "label_uk": None, "category": "fandom"}
    return {"label": tag_id, "label_ru": None, "label_uk": None, "category": "other"}


# ---------------------------------------------------------------- the family tree
def parents(tag_id: str) -> list[str]:
    """Tags this one implies (its parents): every LitRPG book is also "RPG elements"."""
    _, rules, _ = _tables()
    out = list(rules.get(tag_id, ()))
    if tag_id.startswith(FANDOM_PREFIX) and "fanfiction" not in out:
        out.append("fanfiction")
    return out


@lru_cache(maxsize=1)
def _children_index() -> dict[str, list[str]]:
    _, rules, _ = _tables()
    index: dict[str, list[str]] = {}
    for child, ps in rules.items():
        for p in ps:
            index.setdefault(p, []).append(child)
    return index


def children(tag_id: str) -> list[str]:
    """Tags that imply this one (can't appear without it)."""
    return list(_children_index().get(tag_id, []))


def ancestors(tag_id: str) -> list[str]:
    seen, todo = [], list(parents(tag_id))
    while todo:
        t = todo.pop(0)
        if t not in seen and t != tag_id:
            seen.append(t)
            todo += parents(t)
    return seen


def descendants(tag_id: str) -> set[str]:
    seen, todo = set(), list(children(tag_id))
    while todo:
        t = todo.pop()
        if t not in seen and t != tag_id:
            seen.add(t)
            todo += children(t)
    return seen


def direct_parents(tag_id: str) -> list[str]:
    """Parents, without those already implied by another parent (Xianxia → Cultivation, not also → Fantasy)."""
    ps = parents(tag_id)
    return [p for p in ps if not any(p in ancestors(q) for q in ps if q != p)]


def child_tree(tag_id: str, _path: tuple = ()) -> list[dict]:
    """Children as a tree: each child appears under the most specific tag it belongs to."""
    kids = children(tag_id)
    kids = [c for c in kids if not any(c in descendants(o) for o in kids if o != c)]
    out = []
    for c in sorted(kids, key=lambda t: info(t)["label"].lower()):
        if c in _path:
            continue
        out.append({"id": c, "children": child_tree(c, _path + (tag_id,))})
    return out


def anti(tag_id: str) -> list[str]:
    """Tags that contradict this one."""
    out = list(ANTI.get(tag_id, []))
    out += [t for t, others in ANTI.items() if tag_id in others and t not in out]
    return out


def describe(tag_id: str) -> str | None:
    return DESCRIPTIONS.get(tag_id)


@lru_cache(maxsize=1)
def _alias_index() -> tuple[dict[str, list[str]], dict[str, list[tuple[str, list[str]]]]]:
    """(tag id -> every way it's written: names in three languages and synonyms,
        tag id -> site labels that mean it together with other tags: "магический детектив" = Fantasy + Mystery)."""
    names: dict[str, list[str]] = {}
    combos: dict[str, list[tuple[str, list[str]]]] = {}
    for tid, (en, ru, _cat, synonyms) in TAGS.items():
        names[tid] = [a for a in dict.fromkeys([en, ru, UK.get(tid) or "", *synonyms]) if a]
    for label, ids in COMPOUND.items():
        if len(ids) == 1:
            if ids[0] in names and label not in names[ids[0]]:
                names[ids[0]].append(label)
            continue
        for t in ids:
            combos.setdefault(t, []).append((label, [x for x in ids if x != t]))
    return names, combos


def aliases(tag_id: str) -> list[str]:
    """Other names for the tag (not its own names in the three languages)."""
    i = info(tag_id)
    own = {key(x) for x in (i.get("label"), i.get("label_ru"), i.get("label_uk")) if x}
    out, seen = [], set(own)
    for a in _alias_index()[0].get(tag_id, []):
        if key(a) not in seen:  # one spelling per name: "LitRPG", "litrpg" and "Lit-RPG" are the same
            seen.add(key(a))
            out.append(a)
    return out


def combined(tag_id: str) -> list[tuple[str, list[str]]]:
    """Site labels that mean this tag together with others: [(label, the other tag ids)]."""
    return _alias_index()[1].get(tag_id, [])


def suggest(text: str, category: str | None = None, limit: int = 15) -> list[tuple[str, str, int]]:
    """Known tags matching `text`: [(tag id, the name or alias that matched, rank)]. Rank 0: one of the tag's own
    names starts with it; 1: a synonym starts with it; 2 and 3: they contain it."""
    k = key(text)
    if not k:
        return []
    found = []
    for tid, (en, ru, cat, synonyms) in TAGS.items():
        if category and info(tid)["category"] != category:
            continue
        best = None
        for rank_start, rank_contains, names in ((0, 2, [en, ru, UK.get(tid) or ""]), (1, 3, synonyms)):
            for name in names:
                nk = key(name)
                if not nk:
                    continue
                if nk.startswith(k):
                    cand = (rank_start, name)
                elif k in nk:
                    cand = (rank_contains, name)
                else:
                    continue
                if best is None or cand[0] < best[0]:
                    best = cand
        if best:
            found.append((tid, best[1], best[0]))
    found.sort(key=lambda x: x[2])
    return found[:limit]


def collisions() -> list[tuple[str, str, str]]:
    """Built-in synonyms that point at a different tag than the one they're listed under
    (label, listed under, actually maps to). Used by the tests to keep the list clean."""
    syn, _, _ = _tables()
    out = []
    for tid, (en, ru, _cat, synonyms) in TAGS.items():
        for s in [en, ru, UK.get(tid) or "", *synonyms]:
            k = key(s)
            if k and k in syn and tid not in syn[k]:
                out.append((s, tid, ",".join(syn[k])))
    return out


def is_known(tag_id: str) -> bool:
    return tag_id in _tables()[2]


def all_ids() -> list[str]:
    """Every shared tag id."""
    return list(_tables()[2])


POV_TAGS = {"pov-first": "first", "pov-third": "third", "pov-second": "second"}

USER_FILE_TEMPLATE = """\
# Your own tag settings. Bookkeeper reads this file when it starts.
# Tag ids are the short English names you see in the address bar when you filter by a tag,
# e.g. "litrpg", "pov-first", "isekai". Unknown site labels are their own tag (lowercase label).

# Map labels from sites onto tags (the left side can be written any way the site writes it):
[synonyms]
# "попаданец в зомби-апокалипсис" = ["isekai", "undead", "apocalypse"]

# Rules: every book with the tag on the left also gets the tags on the right.
[rules]
# "harem" = ["romance"]

# Add or rename tags:
# [tags.my-favourite-trope]
# label = "My favourite trope"
# label_ru = "Мой любимый троп"
# category = "theme"
"""


def names() -> dict[str, list[str]]:
    """Every name, alias and site label Bookkeeper recognizes (reduced with key()) and the tags it means."""
    return _tables()[0]


def own_id(label: str) -> str:
    """The tag a site label becomes when it isn't one of the shared tags."""
    return label.strip().lower().replace("ё", "е")


def fixes() -> dict[str, list[str]]:
    """Label fixes from my_tags.toml's [fixes] table: {label as written: tag ids} ([] hides the label)."""
    return {k: ([v] if isinstance(v, str) else list(v)) for k, v in (_user_config().get("fixes") or {}).items()}


FIXES_HEADER = (
    "# Labels you fixed on Bookkeeper's \"Fix labels\" page: the label on the left means the tags on the right,\n"
    "# for every book. [] hides the label. Bookkeeper rewrites this table when you fix a label there; you can\n"
    "# also edit it here (then press \"Re-apply my tag rules\" on the Sites page).\n")


def _toml_str(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)  # a JSON string is a valid TOML string


def set_fix(label: str, ids: list[str] | None) -> None:
    """Save what a site label means (None removes the fix) in my_tags.toml's [fixes] table. The rest of the file,
    your comments included, stays as it is. Call reload() afterwards."""
    path = config.USER_TAGS_FILE
    text = path.read_text(encoding="utf-8") if path.exists() else USER_FILE_TEMPLATE
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"my_tags.toml has a mistake ({e}). Fix it in Notepad first.") from e
    current = {k: ([v] if isinstance(v, str) else list(v)) for k, v in (data.get("fixes") or {}).items()}
    wanted = {name: v for name, v in current.items() if key(name) != key(label)}
    if ids is not None:
        wanted[label.strip()] = list(dict.fromkeys(ids))
    body = "".join(f"{_toml_str(name)} = [{', '.join(_toml_str(t) for t in v)}]\n"
                   for name, v in sorted(wanted.items(), key=lambda kv: key(kv[0])))
    lines = text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if line.split("#")[0].strip() == "[fixes]"), None)
    if start is None:
        new = text + ("" if not text or text.endswith("\n") else "\n") + "\n" + FIXES_HEADER + "[fixes]\n" + body
    else:
        end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
        tail = end
        while end < len(lines) and tail > start + 1 and lines[tail - 1].lstrip().startswith("#"):
            tail -= 1  # comments right above the next table belong to it
        new = "".join(lines[:start + 1]) + body + ("\n" if end < len(lines) else "") + "".join(lines[tail:])
    check = tomllib.loads(new)  # never write a file Bookkeeper couldn't read back
    if {key(k) for k in check.get("fixes") or {}} != {key(k) for k in wanted}:
        raise ValueError("my_tags.toml couldn't be updated safely; edit its [fixes] table in Notepad")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(new, encoding="utf-8")
    os.replace(tmp, path)


def ensure_user_file() -> None:
    if not config.USER_TAGS_FILE.exists():
        config.USER_TAGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        config.USER_TAGS_FILE.write_text(USER_FILE_TEMPLATE, encoding="utf-8")
