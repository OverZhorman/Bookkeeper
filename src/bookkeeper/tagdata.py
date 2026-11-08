"""More of the shared tag list (see tags.py): tropes, settings and content notes collected from the tags the sites
actually use (NovelUpdates-style English tags on Wuxia.click, their Russian translations on Ranobes, RanobeLib's
tags, Author.Today and Litnet tags, Flibusta genres, Wattpad hashtags), plus Ukrainian names for every tag.

Format, as in tags.py: id: (English label, Russian label, category, synonyms in any language).
Synonyms are matched after removing case, spaces and punctuation, so "Lit-RPG", "литрпг" and "#ЛитРПГ" are one."""

MORE_TAGS: dict[str, tuple[str, str, str, list[str]]] = {
    # --- protagonist ---
    "calm-lead": ("Calm lead", "Спокойный ГГ", "protagonist", [
        "calm protagonist", "спокойный гг", "хладнокровный гг", "хладнокровный главный герой", "невозмутимый гг",
        "спокійний гг"]),
    "caring-lead": ("Caring lead", "Заботливый ГГ", "protagonist", [
        "caring protagonist", "заботливый гг", "заботливый главный герой", "добрый гг", "kind protagonist"]),
    "cold-lead": ("Cold lead", "Холодный ГГ", "protagonist", [
        "cold protagonist", "холодный гг", "бесчувственный гг", "безразличный гг", "apathetic protagonist",
        "апатичный гг", "апатичный протагонист", "безэмоциональный гг"]),
    "ruthless-lead": ("Ruthless lead", "Безжалостный ГГ", "protagonist", [
        "ruthless protagonist", "безжалостный гг", "безжалостный герой", "безжалостный главный герой",
        "жестокий гг", "жестокий главный герой", "cruel protagonist", "жорстокий гг"]),
    "cunning-lead": ("Cunning lead", "Хитрый ГГ", "protagonist", [
        "cunning protagonist", "хитрый гг", "коварный гг", "black belly", "чёрное сердце", "хитрый главный герой",
        "манипулятор гг"]),
    "dense-lead": ("Dense / oblivious lead", "Недогадливый ГГ", "protagonist", [
        "dense protagonist", "густой гг", "недогадливый гг", "тугодум", "глуповатый гг", "глупый гг",
        "oblivious protagonist"]),
    "naive-lead": ("Naive lead", "Наивный ГГ", "protagonist", ["naive protagonist", "наивный гг", "наивная героиня"]),
    "cute-lead": ("Cute lead", "Милый ГГ", "protagonist", ["cute protagonist", "милый гг", "милая героиня"]),
    "determined-lead": ("Determined lead", "Целеустремлённый ГГ", "protagonist", [
        "determined protagonist", "целеустремленный гг", "настойчивый гг", "решительный гг", "решительная героиня",
        "proactive protagonist", "активный гг", "умная и решительная героиня", "решительная попаданка"]),
    "confident-lead": ("Confident lead", "Уверенный ГГ", "protagonist", [
        "confident protagonist", "уверенный гг", "самоуверенный гг", "наглый и самоуверенный герой", "наглый гг",
        "arrogant protagonist", "высокомерный гг"]),
    "shameless-lead": ("Shameless lead", "Бесстыжий ГГ", "protagonist", [
        "shameless protagonist", "бесстыдный гг", "бесстыдный главный герой", "бесстыжий гг"]),
    "cautious-lead": ("Cautious lead", "Осторожный ГГ", "protagonist", [
        "cautious protagonist", "осторожный гг", "герой не торопится"]),
    "hard-working-lead": ("Hard-working lead", "Трудолюбивый ГГ", "protagonist", [
        "hard-working protagonist", "hardworking protagonist", "трудолюбивый гг", "трудолюбивый главный герой",
        "harsh training", "тяжелые тренировки", "працьовитий гг"]),
    "strong-from-start": ("Strong from the start", "Сильный с самого начала", "protagonist", [
        "protagonist strong from the start", "главный герой силен с самого начала", "гг силен с самого начала",
        "сильный с самого начала", "сильный с начала"]),
    "mature-lead": ("Adult / mature lead", "Взрослый ГГ", "protagonist", [
        "mature protagonist", "зрелый гг", "зрелый протагонист", "взрослые герои", "зрелые герои", "взрослый гг",
        "пожилой протагонист", "old protagonist", "взрослый герой"]),
    "child-lead": ("Child lead", "ГГ ребёнок", "protagonist", [
        "child protagonist", "гг ребенок", "главный герой - ребенок", "главный герой ребенок", "гг ребёнок"]),
    "weak-lead": ("Weak lead", "Слабый ГГ", "protagonist", [
        "weak protagonist", "слабый гг", "главный герой не имеет таланта", "бесталанный гг", "underestimated protagonist",
        "недооцененный гг", "слабак"]),
    "lazy-lead": ("Lazy lead", "Ленивый ГГ", "protagonist", [
        "lazy protagonist", "ленивый гг", "лень как двигатель прогресса", "carefree protagonist", "беззаботный гг"]),
    "loner-lead": ("Loner lead", "ГГ одиночка", "protagonist", [
        "loner protagonist", "главный герой - одиночка", "одинокий гг", "гг одиночка", "introverted protagonist",
        "замкнутый гг", "одиночество"]),
    "orphan-lead": ("Orphan", "Сирота", "protagonist", [
        "orphans", "orphan", "сирота", "сироты", "гг сирота", "главный герой - сирота", "orphan protagonist",
        "abandoned children", "брошенные дети"]),
    "god-lead": ("Lead is a god", "ГГ бог", "protagonist", [
        "главный герой бог", "главный герой - бог", "гг бог", "protagonist is a god"]),
    "mary-sue": ("Mary Sue / Gary Stu", "Мэри Сью", "protagonist", [
        "мэри сью", "мэрисью", "мерисью", "гг - мэри сью", "марти сью", "mary sue", "gary stu", "мери сью"]),
    "ojash-lead": ("Ordinary schoolboy lead (oyash)", "ГГ ояш", "protagonist", [
        "гг ояш", "ояш", "гг ояш (обычный японский школьник)"]),
    "not-ojash": ("Not a doormat lead", "ГГ не ояш", "protagonist", ["гг не ояш", "не ояш", "адекватный герой",
                                                                     "адекватная героиня", "адекватные герои",
                                                                     "разумные герои"]),
    "cheat-ability": ("Cheat ability", "Чит / читерские способности", "protagonist", [
        "cheats", "cheat", "читы", "чит", "читерство", "cheat ability"]),
    "special-abilities": ("Special abilities / superpowers", "Сверхспособности", "theme", [
        "special abilities", "special ability", "особые возможности", "сверхспособности", "суперспособности",
        "супер сила", "суперсила", "superpowers", "super powers", "способности", "надздібності"]),
    "morally-grey": ("Morally grey", "Серая мораль", "protagonist", [
        "серая мораль", "morally grey", "morally gray", "моральная неоднозначность", "grey morality"]),
    "oc": ("Original character (fanfic)", "ОЖП / ОМП (оригинальный персонаж)", "fanfic", [
        "oc", "ос", "original character", "оригинальный персонаж", "original female character", "original male character"]),

    # --- worlds & settings ---
    "fantasy-world": ("Fantasy world", "Фэнтезийный мир", "setting", [
        "fantasy world", "фэнтези мир", "фэнтезийный мир", "магический мир", "magical world", "magic world",
        "волшебный мир", "фентезійний світ"]),
    "sword-and-magic": ("Sword and sorcery", "Меч и магия", "setting", [
        "sword and magic", "sword and sorcery", "меч и магия", "мир меча и магии", "мечи и магия"]),
    "original-world": ("Author's own world", "Авторский мир", "setting", [
        "авторский мир", "авторский мир и расы", "авторские расы", "author's world", "авторський світ"]),
    "alternate-world": ("Alternate world / reality", "Альтернативный мир", "setting", [
        "alternate world", "alternative world", "альтернативный мир", "альтернативная реальность", "alternate reality",
        "альтернативна реальність"]),
    "multiverse": ("Many worlds / multiverse", "Множество миров", "setting", [
        "parallel worlds", "параллельные миры", "параллельный мир", "параллельныемиры", "multiple realms",
        "множество миров", "несколько миров", "множество реальностей", "multiverse", "мультивселенная",
        "interdimensional travel", "межпространственные путешествия", "порталы между мирами", "multiple worlds",
        "многомерная вселенная"]),
    "kingdoms": ("Kingdoms and empires", "Королевства и империи", "setting", [
        "kingdoms", "королевства", "королевство", "empires", "империи", "империя", "kingdom", "empire"]),
    "royalty": ("Royalty", "Королевская семья", "theme", [
        "royalty", "королевская власть", "королевская семья", "императорская семья", "принц", "принцесса", "король",
        "королева", "император", "императрица", "princes", "princesses", "главный герой - король", "монархия"]),
    "ancient-times": ("Ancient times", "Древний мир", "setting", [
        "ancient times", "древний мир", "древние времена", "античность", "каменный век", "stone age", "давній світ"]),
    "ancient-china": ("Ancient China", "Древний Китай", "setting", [
        "ancient china", "древний китай", "древнийкитай", "китайская древность"]),
    "asian-setting": ("Asian setting", "Азиатский сеттинг", "setting", [
        "азиатский сеттинг", "восточный сеттинг", "asian setting", "легенды востока"]),
    "european-ambience": ("European setting", "Европейская атмосфера", "setting", [
        "european ambience", "европейская атмосфера", "европейский сеттинг", "european setting"]),
    "futuristic": ("Future / futuristic setting", "Будущее", "setting", [
        "futuristic setting", "будущее", "далекое будущее", "far future", "high technology", "высокие технологий",
        "высокие технологии", "майбутнє"]),
    "ussr": ("USSR", "СССР", "setting", ["ссср", "жизнь в ссср", "советский союз", "ussr", "soviet union", "срср"]),
    "back-to-ussr": ("Back to the USSR", "Назад в СССР", "genre", [
        "назад в ссср", "попаданец в ссср", "попаданцы в ссср", "попадание в ссср", "back in the ussr",
        "back to the ussr"]),
    "russian-empire": ("Russian Empire", "Российская империя", "setting", [
        "российская империя", "золотой век российской империи", "russian empire", "царская россия",
        "российская империя 19 век", "російська імперія"]),
    "russia": ("Russia", "Россия", "setting", ["россия", "russia", "русь", "росія"]),
    "rusreal": ("RusReal", "Русреал", "genre", ["русреал", "рус реал", "rusreal"]),

    # --- genres & forms ---
    "technomagic": ("Magitech / techno-fantasy", "Технофэнтези / техномагия", "genre", [
        "техномагия", "технофэнтези", "технофентези", "технофэнтэзи", "magical technology", "магические технологии",
        "magitech", "techno-fantasy", "technofantasy", "техномагія"]),
    "magical-realism": ("Magical realism", "Магический реализм", "genre", [
        "магический реализм", "magical realism", "magic realism", "магічний реалізм"]),
    "realism": ("Realism", "Реализм", "genre", ["реализм", "realism", "реалізм"]),
    "contemporary-prose": ("Contemporary fiction", "Современная проза", "genre", [
        "современная проза", "современная русская и зарубежная проза", "современная русская проза", "проза",
        "prose", "contemporary fiction", "literary fiction", "сучасна проза"]),
    "classic": ("Classic literature", "Классика", "genre", [
        "классика", "классическая проза", "зарубежная классическая проза", "советская классическая проза",
        "классическая проза хх века", "классическая проза xx века", "классическая проза хix века",
        "классическая проза xix века", "classics", "classic literature", "antique", "античная литература", "класика"]),
    "womens-fiction": ("Women's fiction", "Женский роман", "genre", ["женский роман", "women's fiction",
                                                                     "womens fiction", "жіночий роман"]),
    "dorama": ("Dorama", "Дорама", "genre", ["дорама", "русдорама", "литдорама", "dorama"]),
    "fairy-tale": ("Fairy tale", "Сказка", "genre", [
        "сказка", "сказки", "fairy tale", "fairytale", "fairy tales", "литературные и народные сказки: прочее",
        "народные сказки", "сказки зарубежных писателей", "казка", "казки"]),
    "litstrategy": ("Strategy / LitStrategy", "ЛитСтратегия", "genre", [
        "литстратегия", "лит стратегия", "стратегия", "strategy", "litstrategy"]),
    "nonfiction": ("Non-fiction", "Нон-фикшн", "format", [
        "non-fiction", "nonfiction", "документальная литература", "публицистика", "научная литература",
        "популярная психология", "психология и психотерапия", "самосовершенствование", "биографии и мемуары: прочее",
        "мемуары", "биографии", "журналы, газеты", "деловая литература", "эзотерика, эзотерическая литература",
        "эзотерика", "маркетинг, pr", "здоровье", "обществознание, социология", "карьера, кадры",
        "педагогика, воспитание детей, литература для родителей", "учебники и пособия", "справочники",
        "образовательная, прикладная, научно-популярная литература", "научно-популярная литература",
        "биографии и мемуары: исторические персоны", "военная история", "культурология", "литературоведение",
        "документальне", "статья", "статті"]),
    "novel": ("Novel (full-length)", "Роман", "format", ["роман", "novel", "full-length novel", "роман, повесть"]),
    "novella": ("Novella", "Повесть", "format", ["повесть", "novella", "повість"]),
    "collection": ("Collection / anthology", "Сборник", "format", [
        "сборник", "сборник рассказов", "anthology", "collection", "збірка"]),
    "web-novel": ("Web novel", "Веб-новелла", "format", [
        "веб", "веб-новелла", "веб новелла", "web novel", "webnovel", "новелла", "самиздат, сетевая литература",
        "сетевая литература", "самиздат", "веб-новела"]),
    "light-novel": ("Light novel (ranobe)", "Ранобэ / лайт-новелла", "format", [
        "лайт-новелла", "лайт новелла", "light novel", "lightnovel", "ранобэ", "ранобе", "ранобе (лайт-новела)"]),
    "machine-translation": ("Machine translation", "Машинный перевод", "format", [
        "machine translation", "машинный перевод", "mtl", "machine translated", "машинний переклад"]),
    "ai-generated": ("AI-generated text", "Сгенерировано ИИ", "format", [
        "сгенерировано ии", "частично сгенерировано ии", "творчество нейросети", "ai-generated", "ai generated",
        "generated by ai", "згенеровано ші"]),
    "adapted": ("Has adaptations (manga, anime…)", "Есть адаптации", "format", [
        "adapted to manga", "adapted to manhwa", "adapted to manhua", "adapted to anime", "adapted to drama",
        "adapted to movie", "adapted to drama cd", "adapted to game", "adapted to visual novel",
        "есть аниме-адаптация", "есть манга-адаптация", "есть манхва-адаптация", "есть маньхуа-адаптация",
        "есть сериал", "есть фильм-адаптация", "адаптация в драму", "адаптация в радиопостановку",
        "адаптировано к визуальному роману", "есть видеоигра по мотивам", "экранизация"]),
    "illustrated": ("Illustrated", "С иллюстрациями", "format", ["иллюстрации", "illustrations", "illustrated",
                                                                  "с иллюстрациями", "в цвете"]),
    "award-winning": ("Award-winning", "Отмечено наградой", "format", ["award-winning work", "award-winning",
                                                                       "призёр конкурса"]),
    "children": ("Children's book", "Детское", "demographic", [
        "детское", "детская литература", "кодомо", "kodomo", "детская проза", "для детей", "детская литература: прочее",
        "детская проза: прочее", "children", "children's", "дитяче"]),
    "anime-based": ("Anime & manga based", "По аниме и манге", "fanfic", [
        "аниме", "anime", "манга", "manga", "манхва", "manhwa", "маньхуа", "manhua", "по аниме", "додзинси",
        "doujinshi"]),

    # --- themes ---
    "power-ranks": ("Power ranks / levels", "Ранги силы", "theme", [
        "ранги силы", "game ranking system", "игровая система рангов", "power levels", "уровни силы",
        "множество уровней силы", "strength-based social hierarchy", "иерархия силы", "ранги", "ранговая система",
        "ранги сили"]),
    "past-life-memories": ("Past-life memories", "Воспоминания о прошлой жизни", "theme", [
        "воспоминания из другого мира", "previous life talent", "знания из прошлой жизни", "опыт из прошлой жизни",
        "transplanted memories", "передача воспоминаний", "воспоминания о прошлой жизни", "прошлая жизнь",
        "memories of past life", "спогади з минулого життя"]),
    "return-from-another-world": ("Returned from another world", "Возвращение из другого мира", "theme", [
        "возвращение из другого мира", "returning from another world", "вернулся из другого мира", "returner"]),
    "reverse-isekai": ("Reverse isekai", "Обратный исекай", "theme", ["обратный исекай", "reverse isekai",
                                                                       "обратное попаданство"]),
    "games": ("Games / gamers", "Игры / геймеры", "theme", [
        "игра", "игры", "видеоигры", "video games", "videogames", "games", "gamers", "геймеры", "компьютерные игры",
        "card games", "карточные игры", "традиционные игры", "азартные игры", "gambling", "геймер", "ігри"]),
    "survival-game": ("Death game / survival game", "Игра на выживание", "theme", [
        "survival game", "игра на выживание", "death game", "смертельная игра", "королевская битва", "battle royale"]),
    "esports": ("E-sports", "Киберспорт", "theme", ["e-sports", "esports", "киберспорт", "кіберспорт"]),
    "otome-game": ("Otome game", "Отомэ-игра", "theme", ["otome game", "отомэ-игра", "отоме игра", "отоме-игра",
                                                         "мир отомэ игры"]),
    "streaming": ("Streaming", "Стримы", "theme", ["livestreaming", "стримы", "стример", "стримеры", "streamer",
                                                   "streaming", "стрімінг"]),
    "showbiz": ("Showbiz / celebrities", "Шоу-бизнес", "theme", [
        "showbiz", "шоу-бизнес", "celebrities", "знаменитости", "acting", "актерское мастерство",
        "главный герой - актер", "idols", "айдолы", "певцы и певицы", "singers", "модели", "models",
        "famous protagonist", "знаменитый гг", "шоу-бізнес"]),
    "business": ("Business", "Бизнес", "theme", [
        "business management", "бизнес", "businessmen", "менеджмент", "management", "владелец магазина",
        "family business", "семейный бизнес", "производственный роман", "корпорации", "корпоративный роман",
        "предприниматель", "business", "бізнес"]),
    "wealthy": ("Rich characters", "Богатые персонажи", "theme", [
        "wealthy characters", "богатые персонажи", "некоторые персонажи богачи", "богатство", "большие деньги",
        "миллиардер", "rich characters", "влиятельные родители"]),
    "poor-to-rich": ("Rags to riches", "Из грязи в князи", "theme", [
        "poor to rich", "бедные до богатых", "из грязи в князи", "rags to riches", "внезапное богатство",
        "poor protagonist", "бедный гг", "главный герой не богатый"]),
    "farming": ("Farming / country life", "Фермерство", "theme", [
        "farming", "фермерство", "сельское хозяйство", "фермер", "колхоз", "сад", "развиваем сад",
        "фермерство (сельская жизнь)", "фермерство"]),
    "medicine": ("Medicine / healers", "Медицина / лекари", "theme", [
        "медицина", "medicine", "medical knowledge", "медицинские знания", "doctors", "врачи", "врач", "доктор",
        "лекарь", "целитель", "целительница", "целительство", "хирург", "больница", "hospital", "healer", "healers",
        "иглоукалывание", "героиня врач", "попаданка врач", "врачи и учителя", "темный целитель", "кровавый целитель",
        "медицина"]),
    "crime": ("Crime / mafia", "Криминал", "theme", [
        "преступники / криминал", "криминал", "мафия", "mafia", "якудза", "yakuza", "банды", "gangs",
        "организованная преступность", "organized crime", "преступники", "criminals", "убийства", "murders",
        "убийство", "crime", "кримінал"]),
    "assassins": ("Assassins", "Ассасины / убийцы", "theme", [
        "assassins", "assassin", "ассасины", "ассасин", "убийца", "киллер", "наемный убийца"]),
    "spies": ("Spies / special services", "Шпионы / спецслужбы", "theme", [
        "шпионы", "шпионский детектив", "spies", "espionage", "спецслужбы", "шпигуни"]),
    "secret-organizations": ("Secret organizations", "Тайные организации", "theme", [
        "secret organizations", "evil organizations", "злые организации", "тайные общества", "тайные организации",
        "секретные организации"]),
    "religion": ("Religion / church", "Религия", "theme", [
        "religions", "религия", "evil religions", "злые религии", "priests", "жрецы", "жрицы", "saints", "святые",
        "церковь", "буддизм", "христианство", "religion", "религия, религиозная литература", "релігія"]),
    "pirates": ("Pirates & the sea", "Пираты и море", "theme", [
        "пираты", "pirates", "море", "sea", "морские сражения", "морские приключения", "naval", "моряки", "пірати"]),
    "ninja": ("Ninja", "Ниндзя", "theme", ["ниндзя", "ninja", "шиноби", "shinobi"]),
    "samurai": ("Samurai", "Самураи", "theme", ["самураи", "samurai", "самурайский боевик", "самурай"]),
    "murim": ("Murim", "Мурим", "theme", ["мурим", "murim"]),
    "knights": ("Knights", "Рыцари", "theme", ["knights", "рыцари", "рыцарь", "паладины", "paladins", "лицарі"]),
    "weapon-master": ("Swordsman / weapon master", "Мастер меча / оружия", "theme", [
        "sword wielder", "мечник", "мастер меча", "sword master", "мастер копья", "владение копьем", "копейщик",
        "spear wielder", "лучник", "archer", "главный герой - рубака"]),
    "hunters": ("Hunters", "Охотники", "theme", ["hunters", "охотники", "охотник", "охота", "hunter",
                                                "охота в группе", "мисливці"]),
    "adventurers": ("Adventurers / guilds", "Авантюристы / гильдии", "theme", [
        "авантюристы", "adventurers", "guilds", "гильдии", "гильдия", "гильдия авантюристов", "авантюрист"]),
    "elemental-magic": ("Elemental magic", "Магия стихий", "theme", [
        "elemental magic", "стихии", "магия стихий", "стихийная магия", "магия молний", "магія стихій"]),
    "summoning": ("Summoning", "Призыв / призыватели", "theme", [
        "призыватели", "summoning magic", "магия призыва", "summoners", "герой - призыватель", "призыватель",
        "summoner", "summoning"]),
    "artifacts": ("Artifacts", "Артефакты", "theme", [
        "artifacts", "артефакты", "легендарные артефакты", "магический артефакт", "волшебные предметы",
        "magic items", "артефакт", "артефакти"]),
    "magic-beasts": ("Magic beasts / mythical creatures", "Магические звери", "theme", [
        "magic beasts", "магические звери", "волшебные звери", "мифические звери", "beasts", "звери",
        "мифическиесущества", "мифические существа", "fantasy creatures", "вымышленныесущества", "вымышленные существа",
        "существа", "магические существа", "mythical creatures", "magical creatures"]),
    "pets": ("Pets / animal companions", "Питомцы", "theme", [
        "pets", "домашние животные", "питомцы", "beast companions", "звери-компаньоны", "кот", "коты", "кошки",
        "cats", "собаки", "dogs", "фамильяр", "familiar", "домашні тварини"]),
    "beastkin": ("Beastkin / demi-humans", "Зверолюди", "theme", [
        "зверолюди", "beastkin", "demi-humans", "полулюди", "кемономими", "animal characteristics", "животные черты",
        "звіролюди"]),
    "monster-girls": ("Monster girls", "Монстродевушки", "theme", ["монстродевушки", "девушки-монстры",
                                                                   "monster girls"]),
    "fantasy-races": ("Fantasy races (orcs, dwarves…)", "Фэнтезийные расы", "theme", [
        "orcs", "орки", "dwarfs", "dwarves", "гномы", "дварфы", "goblins", "гоблины", "фэнтезийные расы",
        "fantasy races", "тролли", "trolls"]),
    "immortals": ("Immortals", "Бессмертные", "theme", [
        "бессмертные", "immortals", "бессмертие", "immortality", "кровь бессмертных", "безсмертні"]),
    "ghosts": ("Ghosts / spirits", "Призраки / духи", "theme", [
        "призраки / духи", "призраки", "ghosts", "spirits", "духи", "души", "духи среди нас", "привидения",
        "привиди"]),
    "angels": ("Angels", "Ангелы", "theme", ["ангелы", "angels", "ангел", "падшие ангелы", "fallen angels", "янголи"]),
    "witches": ("Witches", "Ведьмы", "theme", ["ведьма", "ведьмы", "witches", "witch", "ведьмак", "відьми"]),
    "evolution": ("Evolution / mutations", "Эволюция / мутации", "theme", [
        "эволюция", "evolution", "развитие и эволюция", "мутации", "mutations", "мутированные существа", "еволюція"]),
    "amnesia": ("Amnesia", "Амнезия", "theme", ["amnesia", "амнезия", "потеряпамяти", "потеря памяти", "memory loss",
                                                 "амнезія"]),
    "hikikomori": ("Hikikomori / NEET", "Хикикомори", "theme", ["хикикомори", "hikikomori", "neet", "нит"]),
    "maids": ("Maids & servants", "Горничные и слуги", "theme", [
        "горничные", "maids", "maid", "дворецкий", "butler", "отношения хозяин-слуга", "master-servant relationship"]),
    "master-disciple": ("Master and disciple", "Учитель и ученик", "theme", [
        "master-disciple relationship", "отношения мастер-ученик", "учитель и ученик", "teachers", "учителя",
        "наставник"]),
    "friendship": ("Friendship", "Дружба", "theme", [
        "дружба", "friendship", "друзья", "friends", "настоящая дружба", "подруги", "brotherhood", "братство",
        "teamwork", "командная работа", "дружба и любовь"]),
    "loyal-subordinates": ("Loyal subordinates", "Верные подчинённые", "theme", [
        "loyal subordinates", "верные подчиненные", "лояльные подчиненные", "верные слуги"]),
    "misunderstandings": ("Misunderstandings", "Недопонимание", "theme", [
        "misunderstandings", "недопонимание", "недоразумения", "непорозуміння"]),
    "heartwarming": ("Heartwarming", "Трогательное", "theme", [
        "heartwarming", "cute story", "трогательно", "милая история", "добрая история", "трогательное", "добрая книга"]),
    "happy-ending": ("Happy ending", "Хэппи-энд", "theme", [
        "счастливыйфинал", "счастливый финал", "хэппи энд", "хэппи-энд", "happy ending", "happy end", "счастливый конец",
        "щасливий кінець"]),
    "emotional": ("Emotional", "Эмоционально", "theme", [
        "очень эмоционально", "эмоции на грани", "сильные чувства", "emotional", "эмоционально"]),
    "power-struggle": ("Power struggle", "Борьба за власть", "theme", [
        "борьба за власть", "power struggle", "междоусобица", "борьба кланов", "боротьба за владу"]),
    "betrayal": ("Betrayal", "Предательство", "theme", ["предательство", "betrayal", "betrayed", "зрада"]),
    "death": ("Death / loss of loved ones", "Смерть / потеря близких", "theme", [
        "death of loved ones", "смерть близких", "death", "смерть", "смерти", "потеря", "loss", "гибель близких"]),
    "dark-past": ("Tragic / mysterious past", "Тёмное прошлое", "theme", [
        "tragic past", "past trauma", "mysterious past", "past plays a big role", "mysterious family background",
        "тайны прошлого", "наследие прошлого", "трагичное прошлое", "тяжелое прошлое", "травмы",
        "мистический ореол вокруг семьи", "герои с тайнами"]),
    "dark-world": ("Dark / grim world", "Мрачный мир", "theme", [
        "мрачный мир", "dark", "дарк", "жестокий мир", "мрачное", "темное", "grim", "похмурий світ"]),
    "depression": ("Depression / madness", "Депрессия / безумие", "theme", [
        "depression", "депрессия", "безумие", "madness", "insanity", "mental illness", "психические расстройства",
        "депресія"]),
    "slavery": ("Slavery", "Рабство", "theme", ["рабы", "slaves", "s*aves", "рабство", "главный герой - раб",
                                                "slavery", "раби"]),
    "human-experiments": ("Human experiments", "Эксперименты над людьми", "theme", [
        "эксперименты над людьми", "human experimentation", "human experiments", "генетические модификации"]),
    "childcare": ("Raising children", "Воспитание детей", "theme", [
        "childcare", "parenting", "родительство", "уход за детьми", "воспитание детей", "cute children", "милые дети",
        "милое дитя", "общий ребенок", "ребенок", "одинокий родитель", "single parent"]),
    "siblings": ("Siblings", "Братья и сёстры", "theme", [
        "siblings", "братья и сестры", "брат и сестра", "сестра", "брат", "братья", "сестры", "doting older siblings",
        "заботливые старшие братья и сестры", "overprotective siblings", "brother complex", "братский комплекс",
        "sister complex", "younger sisters", "младшие сестры", "есть сестра", "siblings not related by blood",
        "не родные братья и сестры", "братья и сестры не связанные по крови", "twins", "близнецы", "sibling rivalry",
        "брати і сестри"]),
    "pregnancy": ("Pregnancy", "Беременность", "theme", ["pregnancy", "беременность", "беременная героиня",
                                                         "вагітність"]),

    # --- romance & relationships ---
    "mixed-orientation": ("Mixed (several kinds of relationships)", "Смешанная направленность", "orientation", [
        "смешанная", "смешанная направленность", "mixed", "multi", "mixed relationships", "змішана"]),
    "other-orientation": ("Other kinds of relationships", "Другие виды отношений", "orientation", [
        "другие виды отношений", "other relationships", "other", "інші види стосунків"]),
    "slow-burn": ("Slow-burn romance", "Медленная романтика", "relationship", [
        "slow romance", "slow burn", "slowburn", "слоуберн", "слоу берн", "медленный роман", "медленная романтика",
        "late romance", "поздняя романтика", "неспешное развитие отношений"]),
    "early-romance": ("Early romance", "Ранняя романтика", "relationship", ["early romance", "ранняя романтика"]),
    "romantic-subplot": ("Romantic subplot", "Романтическая линия", "relationship", [
        "romantic subplot", "romance subplot", "малая романтика", "любовная линия", "романтическая линия"]),
    "love-interest-first": ("Love interest falls in love first", "Возлюбленный влюбляется первым", "relationship", [
        "love interest falls in love first", "любовный интерес влюбляется первым", "героиня влюбляется первой"]),
    "lead-falls-first": ("Lead falls in love first", "ГГ влюбляется первым", "relationship", [
        "protagonist falls in love first", "главный герой влюбляется первым"]),
    "doting-love": ("Devoted love interest", "Преданный возлюбленный", "relationship", [
        "doting love interests", "devoted love interests", "kind love interests", "заботливый любовный интерес",
        "преданный любовный интерес", "unconditional love", "безусловная любовь", "persistent love interests",
        "единственная любовь", "главный герой лоялен к любви", "однолюб", "благородный герой"]),
    "possessive-love": ("Possessive / obsessive love", "Собственническая любовь", "relationship", [
        "possessive characters", "obsessive love", "любовная одержимость", "навязчивая любовь", "clingy lover",
        "собственник", "ревность", "jealousy"]),
    "domineering-hero": ("Domineering hero", "Властный герой", "relationship", [
        "властный герой", "властный мужчина", "доминирующий герой", "domineering male lead", "domineering",
        "владний герой"]),
    "yandere": ("Yandere", "Яндере", "relationship", ["яндере", "yandere"]),
    "tsundere": ("Tsundere", "Цундере", "relationship", ["цундере", "tsundere"]),
    "strong-love-interest": ("Strong love interest", "Сильный возлюбленный", "relationship", [
        "strong love interests", "сильные мужчины", "сильные герои", "настоящий мужчина", "сильный мужчина",
        "харизматичный герой", "харизматичный мужчина", "power couple", "влиятельная парочка", "smart couple"]),
    "handsome-lead": ("Handsome male lead", "Красивый главный герой", "relationship", [
        "handsome male lead", "красивый мужчина свинец", "красивый гг", "красавец", "красивый герой"]),
    "beautiful-lead": ("Beautiful female lead", "Красивая героиня", "relationship", [
        "beautiful female lead", "красивая героиня", "красивые девушки", "прекрасная героиня"]),
    "enemies-to-lovers": ("Enemies to lovers", "От ненависти до любви", "relationship", [
        "enemies become lovers", "враги становятся возлюбленными", "враги становятся любовниками",
        "от ненависти до любви", "от ненависти к любви", "любовьненависть", "любовь-ненависть", "enemies to lovers",
        "hate to love", "від ненависті до кохання"]),
    "clash-of-characters": ("Clash of characters", "Противостояние характеров", "relationship", [
        "противостояние характеров", "столкновение характеров", "противостояние героев", "противостояние характров",
        "bickering couple", "героиня с характером"]),
    "fated-lovers": ("Fated mates / true pair", "Истинная пара", "relationship", [
        "истинная пара", "fated lovers", "fated mates", "соулмейты", "soulmates", "соулмейт", "предназначенные",
        "истинные", "справжня пара"]),
    "marriage": ("Marriage", "Брак", "relationship", [
        "marriage", "брак", "свадьба", "wedding", "замужество", "женитьба", "engagement", "помолвка", "шлюб"]),
    "arranged-marriage": ("Arranged / forced marriage", "Брак по договорённости", "relationship", [
        "arranged marriage", "брак по договоренности", "аранжированный брак", "вынужденный брак",
        "marriage of convenience", "контрактный брак", "брак по расчету", "contract marriage", "договорной брак",
        "отбор невест", "отбор"]),
    "fake-relationship": ("Fake relationship", "Фиктивные отношения", "relationship", [
        "фиктивные отношения", "фиктивный брак", "фиктивый брак", "pretend lovers", "fake relationship",
        "fake marriage"]),
    "divorce": ("Divorce", "Развод", "relationship", [
        "развод", "после развода", "divorce", "бывшие", "бывшие муж и жена", "развод и новая любовь", "розлучення"]),
    "infidelity": ("Infidelity", "Измена", "relationship", [
        "измена", "романы о неверности", "измена и предательство", "предательство и измена", "измена мужа",
        "предательство мужа", "affair", "роман на стороне", "infidelity", "неверность", "измена и предательство мужа",
        "мерзавец муж", "подружня зрада"]),
    "ntr": ("NTR (netorare)", "НТР (нетораре)", "content", [
        "нетораре", "netorare", "netori", "нетори", "неторасе", "ntr"]),
    "love-triangle": ("Love triangle", "Любовный треугольник", "relationship", [
        "love triangles", "love triangle", "любовный треугольник", "love rivals", "соперники в любви",
        "любовний трикутник"]),
    "first-love": ("First love", "Первая любовь", "relationship", [
        "first love", "первая любовь", "childhood love", "любовь детства", "подростковаялюбовь", "перше кохання"]),
    "childhood-friends": ("Childhood friends", "Друзья детства", "relationship", [
        "childhood friends", "друзья детства", "обещание из детства", "childhood promise", "друзі дитинства"]),
    "love-at-first-sight": ("Love at first sight", "Любовь с первого взгляда", "relationship", [
        "love at first sight", "любовь с первого взгляда", "кохання з першого погляду"]),
    "unrequited-love": ("Unrequited love", "Безответная любовь", "relationship", [
        "unrequited love", "безответная любовь", "secret crush", "тайная влюбленность", "неразделенная любовь",
        "нерозділене кохання"]),
    "age-gap": ("Age gap", "Разница в возрасте", "relationship", [
        "разницаввозрасте", "разница в возрасте", "older love interests", "younger love interests", "age gap",
        "age difference", "большая разница в возрасте между героем и его любовным интересом", "різниця у віці"]),
    "office-romance": ("Office romance / boss", "Служебный роман", "relationship", [
        "служебный роман", "босс", "начальник и подчиненная", "босс и подчиненная", "босс и подчинённая",
        "office romance", "boss", "отношения начальник-подчиненный", "службовий роман"]),
    "polygamy": ("Polygamy", "Многоженство", "relationship", ["polygamy", "многоженство", "багатоженство"]),
    "omegaverse": ("Omegaverse", "Омегаверс", "relationship", ["омегаверс", "omegaverse", "abo", "a/b/o", "омега",
                                                               "альфа и омега"]),
    "mpreg": ("Male pregnancy", "Мужская беременность", "content", ["mpreg", "мужскаябеременность",
                                                                     "мужская беременность"]),
    # --- content notes ---
    "ecchi": ("Ecchi / fan service", "Этти / фансервис", "content", [
        "ecchi", "этти", "эччи", "фансервис", "fan service", "fanservice", "нагота", "nudity"]),
    "mature-themes": ("Mature themes", "Зрелая тематика", "content", [
        "mature", "зрелая тематика", "зрелый", "r-15", "16+", "16", "mature themes", "доросла тематика"]),
    "sexual-violence": ("Sexual violence", "Сексуальное насилие", "content", [
        "r*pe", "rape", "изнас***вания", "изнасилование", "s*xual abuse", "sexual abuse", "sexual violence",
        "сексуальное насилие", "жертва изнас***вания становится любовником", "r*pe victim becomes lover",
        "обратное изнас***вание", "домогательство"]),
    "abuse": ("Abuse / bullying", "Жестокое обращение / травля", "content", [
        "child abuse", "abusive characters", "bullying", "запугивание", "буллинг", "травля", "издевательства",
        "жестокое обращение", "cruel characters", "жестокие персонажи"]),
    "suicide": ("Suicide", "Суицид", "content", ["суицид", "suicides", "suicide", "самоубийство", "суїцид"]),
    "drugs": ("Drugs / alcohol", "Наркотики / алкоголь", "content", [
        "наркотики", "drugs", "наркомания", "алкоголь", "alcohol", "алкоголизм", "курение", "smoking", "наркотики"]),
    "profanity": ("Profanity", "Нецензурная лексика", "content", [
        "нецензурнаялексика", "нецензурная лексика", "ненормативная лексика", "мат", "маты", "нецензурная",
        "profanity", "swearing", "лайка"]),
    "incest": ("Incest", "Инцест", "content", ["инцест", "incest", "інцест"]),
    "loli": ("Loli characters", "Лоли", "content", ["лоли", "loli", "лоликон", "lolicon"]),

    # --- fandoms (fanfiction) ---
    "fandom-naruto": ("Naruto", "Наруто", "fandom", [
        "наруто", "naruto", "мир наруто", "мирнаруто", "аниме наруто", "анименаруто", "наруто шиппуден", "боруто",
        "boruto", "акацуки", "коноха", "команда 7", "команда7"]),
    "fandom-harry-potter": ("Harry Potter", "Гарри Поттер", "fandom", [
        "гарри поттер", "harry potter", "harrypotter", "гп", "поттер", "хогвартс", "hogwarts", "слизерин",
        "гриффиндор", "драмиона", "дамбигад", "гаррі поттер"]),
    "fandom-marvel": ("Marvel", "Марвел", "fandom", ["марвел", "marvel", "мстители", "avengers", "человек-паук",
                                                     "spider-man", "мцу", "mcu"]),
    "fandom-bts": ("BTS (k-pop)", "BTS (k-pop)", "fandom", ["bts", "бтс", "bangtan", "вигуки", "vkook", "юнмины",
                                                            "намджины"]),
    "fandom-stray-kids": ("Stray Kids (k-pop)", "Stray Kids (k-pop)", "fandom", [
        "straykids", "stray kids", "стрейкидс", "стрей кидс", "skz", "хенликсы", "минсоны"]),
    "fandom-kpop": ("K-pop", "K-pop", "fandom", ["k-pop", "kpop", "кпоп", "к-поп", "blackpink", "exo", "twice",
                                                 "ateez", "enhypen", "txt"]),
    "fandom-mha": ("My Hero Academia", "Моя геройская академия", "fandom", [
        "моя геройская академия", "my hero academia", "boku no hero academia", "bnha", "mha", "мга"]),
    "fandom-bsd": ("Bungou Stray Dogs", "Великий из бродячих псов", "fandom", [
        "великий из бродячих псов", "бродячие псы", "bungou stray dogs", "bsd", "бсд"]),
    "fandom-aot": ("Attack on Titan", "Атака титанов", "fandom", ["атака титанов", "attack on titan", "aot",
                                                                  "shingeki no kyojin"]),
    "fandom-tokyo-revengers": ("Tokyo Revengers", "Токийские мстители", "fandom", [
        "токийские мстители", "tokyo revengers"]),
    "fandom-genshin": ("Genshin Impact", "Геншин", "fandom", ["геншин", "геншин импакт", "genshin", "genshin impact"]),
    "fandom-undertale": ("Undertale", "Андертейл", "fandom", ["андертейл", "undertale", "андертейл ау"]),
    "fandom-transformers": ("Transformers", "Трансформеры", "fandom", [
        "трансформеры", "transformers", "автоботы", "десептиконы", "трансформеры прайм", "transformers prime"]),
    "fandom-hxh": ("Hunter x Hunter", "Хантер х Хантер", "fandom", ["хантер х хантер", "хантерххантер",
                                                                     "hunter x hunter"]),
    "fandom-one-piece": ("One Piece", "Ван Пис", "fandom", ["ванпис", "ван пис", "one piece", "onepiece"]),
    "fandom-fairy-tail": ("Fairy Tail", "Хвост феи", "fandom", ["хвост феи", "fairy tail"]),
    "fandom-demon-slayer": ("Demon Slayer", "Клинок, рассекающий демонов", "fandom", [
        "клинок рассекающий демонов", "клинок, рассекающий демонов", "demon slayer", "kimetsu no yaiba"]),
    "fandom-lotr": ("Tolkien / Lord of the Rings", "Властелин колец / Толкин", "fandom", [
        "властелин колец", "lord of the rings", "хоббит", "hobbit", "толкин", "tolkien"]),
    "fandom-maze-runner": ("The Maze Runner", "Бегущий в лабиринте", "fandom", ["бегущий в лабиринте",
                                                                                 "maze runner", "the maze runner"]),
    "fandom-twilight": ("Twilight", "Сумерки", "fandom", ["сумерки", "twilight"]),
    "fandom-star-wars": ("Star Wars", "Звёздные войны", "fandom", ["звездные войны", "star wars"]),
    "fandom-warhammer": ("Warhammer", "Warhammer", "fandom", ["warhammer", "warhammer 40000", "warhammer 40k",
                                                              "вархаммер"]),
    "fandom-minecraft": ("Minecraft", "Майнкрафт", "fandom", ["майнкрафт", "minecraft"]),
    "fandom-winx": ("Winx", "Винкс", "fandom", ["винкс", "winx"]),
    "fandom-ninjago": ("Ninjago", "Ниндзяго", "fandom", ["ниндзяго", "ninjago"]),
    "fandom-fnaf": ("Five Nights at Freddy's", "ФНАФ", "fandom", ["фнаф", "fnaf", "five nights at freddy's"]),
    "fandom-hazbin": ("Hazbin Hotel", "Отель Хазбин", "fandom", ["отель хазбин", "hazbin hotel"]),
    "fandom-countryhumans": ("Countryhumans", "Countryhumans", "fandom", ["countryhumans"]),
    "fandom-elder-scrolls": ("The Elder Scrolls", "The Elder Scrolls", "fandom", ["the elder scrolls", "elder scrolls",
                                                                                  "скайрим", "skyrim"]),
    "fandom-mdzs": ("Grandmaster of Demonic Cultivation (MDZS)", "Магистр дьявольского культа", "fandom", [
        "магистр дьявольского культа", "магистрдьявольскогокульта", "mo dao zu shi", "mdzs", "мдк",
        "grandmaster of demonic cultivation"]),
    "fandom-tgcf": ("Heaven Official's Blessing (TGCF)", "Благословение небожителей", "fandom", [
        "благословение небожителей", "благословениенебожителей", "tian guan ci fu", "tgcf",
        "heaven official's blessing"]),
    "fandom-black-butler": ("Black Butler", "Тёмный дворецкий", "fandom", ["темный дворецкий", "темныйдворецкий",
                                                                          "black butler", "kuroshitsuji"]),
    "crossover": ("Crossover", "Кроссовер", "fanfic", ["кроссовер", "crossover", "кросовер"]),
    "reactions": ("Reaction fics", "Реакции", "fanfic", ["реакции", "реакция", "reactions", "reaction", "реакції"]),
}

# More ways the sites write tags that already exist in tags.py.
MORE_SYNONYMS: dict[str, list[str]] = {
    "isekai": ["попаданчество", "попадание", "попаданки", "поподанка", "перемещение в другой мир",
               "перемещение в иной мир", "иные миры", "другие миры", "другиемиры", "наши в другом мире",
               "gate to another world", "врата в другой мир", "multiple transported individuals",
               "множество перемещенных людей", "переміщення в інший світ"],
    "reincarnation": ["multiple reincarnated individuals", "множество реинкарнированных людей",
                      "несколько перерожденных персонажей", "несколько перевоплощенных людей", "переродился в другом мире"],
    "regression": ["регресс", "прожить жизнь заново", "возвращение в свое прошлое", "жизнь заново"],
    "progression": ["strong to stronger", "от сильного к сильнейшему", "становление героя", "развитие героя",
                    "развитие личности", "герой развивается", "становление и развитие героя",
                    "развитие и становление героя", "страновление героя", "становление героини", "рост героини",
                    "от слабого до сильного", "слабый становится сильным", "прокачка персонажа", "саморазвитие",
                    "accelerated growth", "slow growth at start", "медленный рост в начале", "из овцы в волчицу"],
    "op-lead": ["всемогущий гг", "гг имеет высшую власть", "манчкин", "сверхсильный главный герой",
                "сильный главный герой", "сильная гг", "сильная героиня гг"],
    "smart-lead": ["genius protagonist", "гениальный гг", "главный герой - гений", "умный герой",
                   "умный главный герой", "умная героиня", "strategist", "стратег", "военный гений"],
    "male-lead": ["главный герой - мужчина", "главный герой мужчина"],
    "female-lead": ["главный герой - женщина", "главная героиня - женщина", "героиня"],
    "nonhuman-lead": ["главный герой - нелюдь", "главный герой - негуманоид", "не гуманоидный гг",
                      "non-humanoid protagonist", "главный герой - наполовину человек"],
    "anti-hero": ["antihero protagonist", "беспринципный главный герой"],
    "hidden-identity": ["hiding true identity", "hidden abilities", "скрывает истинную личность",
                        "несколько идентичностей", "multiple identities", "двойная жизнь", "запечатанная сила"],
    "fantasy": ["фэнтази", "фентази", "фантазия", "российское фэнтези", "классическое фэнтези"],
    "dark-fantasy": ["даркфэнтези", "дарк фэнтези", "дарк-фэнтези", "тёмное фэнтези"],
    "heroic-fantasy": ["героическая фантастика", "героическая фантастика и фэнтези"],
    "epic-fantasy": ["эпическая фантастика и фэнтези"],
    "sci-fi": ["научная фантастика и фэнтези", "фантастика (жанр)"],
    "litrpg": ["элементы реалрпг", "элементы литрпг", "реал рпг"],
    "boyar-anime": ["бояръ", "боярь", "бояръанимэ", "бояр", "боярка", "добробоярка", "боярка здорового человека",
                    "бояранимэ"],
    "slice-of-life": ["бытовуха", "бытовое фентэзи", "повседневная жизнь", "домашние дела", "буденність"],
    "romance": ["любовные романы", "любовныероманы", "любовный", "lovestory", "love story", "влюбленность",
                "страсть", "passion", "любовь и страсть", "кохання", "любовь вопреки", "запретная любовь",
                "новая любовь"],
    "historical": ["история", "исторические фигуры", "historical figures", "18 век", "19 век", "17 век",
                   "victorian", "викторианская эпоха"],
    "mystery": ["полиция", "police", "полицейский детектив", "криминальный детектив", "детективы", "investigations",
                "расследования", "mystery solving", "журналистское расследование", "классический детектив",
                "загадка", "тайна", "тайны", "тайны и загадки", "детективи"],
    "thriller": ["остросюжетное", "остросюжетный"],
    "horror": ["крипипаста", "creepypasta", "ужас", "готический роман"],
    "comedy": ["comedic undertone", "комедийный оттенок", "комедийный подтекст", "юмор и ирония", "легко и с юмором",
               "черный юмор", "чёрный юмор", "юмор но это не точно", "юмористическая проза", "пародии"],
    "drama": ["драмма", "мелодрама", "melodrama"],
    "angst": ["боль", "стекло", "грусть", "слезы", "слёзы", "hurt"],
    "action": ["экшен", "fighting", "драки", "бои", "битвы", "битва", "сражения", "battles", "fights",
               "битвы и сражения", "боевые сцены"],
    "war": ["wars", "войны", "strategic battles", "стратегические сражения", "проза о войне", "военные действия"],
    "military": ["военные", "army", "soldiers", "солдаты", "generals", "генералы", "наемники", "mercenaries",
                 "военное дело", "офицер", "армія"],
    "adventure": ["приключение", "путешествие", "путешествия", "travel", "journey", "опасные приключения",
                  "приключенческий роман", "приключения в современном мире", "world travel", "кругосветное путешествие",
                  "изучение мира", "exploration", "пригода"],
    "politics": ["schemes and conspiracies", "интриги и заговоры", "интриги и политические заговоры",
                 "интриги и тайны", "тайны и интриги", "клановые интриги", "дипломатия", "diplomacy",
                 "court official", "придворные", "nationalism", "национализм", "многоходовки", "интрига",
                 "политика (жанр)"],
    "aristocracy": ["дворяне", "падшее дворянство", "fallen nobility", "родовые способности", "рода", "возвышение рода",
                    "аристо"],
    "villainess": ["villainess noble girls", "злодейка-аристократка"],
    "progressorism": ["индустриализация", "industrialization", "знания современного мира", "изобретатель"],
    "kingdom-building": ["строительство города", "градостроение", "city building", "town building", "army building",
                         "строительство армии", "колонизация", "colonization", "строительство и развитие",
                         "развитие и строительство", "стройка", "обустройство в новом мире"],
    "dungeon": ["мастер подземелий", "dungeon master"],
    "system": ["системы", "system novel"],
    "cultivation": ["культивирование", "культивации", "fast cultivation", "быстрая культивация",
                    "быстрое совершенствование", "unique cultivation technique", "звездная культивация", "закалка тела",
                    "закаливание тела", "body tempering", "дао", "dao", "культивирование с помощью пилюли",
                    "заклинатели", "заклинатель"],
    "xianxia": ["санься", "сянься"],
    "superheroes": ["супергерой"],
    "gods": ["богини", "goddesses", "божественная защита", "отношения бог-человек", "миры где играют боги",
             "evil gods", "злые боги", "godly powers", "божественные силы", "deity"],
    "demons": ["devils", "дьяволы", "дьявол", "король демонов", "демонический"],
    "magic": ["wizards", "волшебники", "маг", "колдуны", "чародеи", "главный герой типа маг", "магические печати",
              "magic formations", "магические формирования", "магическое пространство", "magical space",
              "anti-magic", "антимагия"],
    "necromancy": ["некроманты", "некроманти"],
    "undead": ["личи", "liches", "lich"],
    "mythology": ["мифы", "легенды", "legends", "мифы. легенды. эпос", "нечисть", "фольклор", "міфологія"],
    "vampires": ["провампиров", "про вампиров"],
    "werewolves": ["прооборотней", "про оборотней", "werebeasts", "оборотень*", "метаморфы"],
    "dragons": ["драконы*"],
    "survival": ["борьба за выживание", "робинзонада"],
    "revenge": ["мстительный гг", "месть предателю"],
    "space": ["outer space", "космическое пространство", "открытый космос", "космические корабли"],
    "virtual-reality": ["полное погружение", "виртуальный мир*"],
    "mecha": ["боевые роботы", "шагающие роботы"],
    "ai": ["искуственный интеллект", "нейросети", "андроиды", "androids", "android"],
    "crafting": ["алхимик", "крафт*"],
    "cooking": ["готовка", "кулинария*"],
    "sports": ["волейбол", "теннис", "водные виды спорта", "футбол", "football"],
    "modern-day": ["городской", "современность*"],
    "school-life": ["school", "колледж", "college/university", "студенты*", "старшая школа", "high school",
                    "боевые школы"],
    "academy": ["боевая академия"],
    "young-adult": ["подростки", "подросток", "подростковая", "молодежная проза", "teen", "подростковая проза*"],
    "fanfiction": ["фф", "фанф"],
    "au": ["ау", "неканон", "альтернативная вселенная (au)", "отклонения от канона", "отклонение от канона",
           "отклоненияотканона", "отклонениеотканона", "canon divergence"],
    "crime": ["похищение", "похищения", "kidnappings", "kidnapping"],
    "supernatural": ["проклятие", "проклятия", "curses", "curse"],
    "ooc": ["частичныйоос", "частичный оос", "оос (out of character)"],
    "adult": ["18", "21+", "секс", "sex", "первыйраз", "первый раз", "эротическая литература", "эротика (жанр)",
              "first-time interc**rse", "first-time intercourse", "f*llatio", "фелляция", "c*nnilingus", "куннилингус",
              "m*sturbation", "мастурбация", "s*x friends", "threesome", "втроем", "анал", "пайзури", "сквиртинг",
              "на лицо", "вуайеризм", "интим на свежем воздухе", "бдсм", "bdsm", "мазохизм", "садизм",
              "мастурбация грудью", "pussy job", "семейные отношения, секс", "lemon"],
    "violence": ["жестокость и насилие", "depictions of cruelty", "torture", "пытки", "гуро", "guro", "каннибализм",
                 "cannibalism", "жестокость*"],
    "slash": ["shounen ai*", "сёнен-ай", "сенен-ай", "геи", "gay", "manly gay couple", "мужская гей-пара", "бл",
              "boys love (bl)"],
    "femslash": ["сёдзе-ай", "лесби", "лесбиянки", "girls love (gl)"],
    "lgbt": ["трансгендер", "transgender", "бисексуальный гг", "bisexual", "бисексуальность"],
    "gen": ["нет романтики"],
    "no-harem": ["нет гарема", "сильный герой однолюб"],
    "harem": ["главный герой - собирает гарем", "императорский гарем", "возможен гарем"],
    "translation": ["любительский перевод", "fan translation"],
    "short-story": ["сингл", "короткийрассказ", "короткий рассказ", "мини", "малые литературные формы прозы: рассказы, эссе, новеллы, феерия"],
    "poetry": ["современная русская поэзия", "стихи для детей и подростков"],
    "family": ["complex family relationships", "комплекс семейных отношений", "family conflict", "семейный конфликт",
               "familial love", "семейная любовь", "doting parents", "любящие родители", "семейные отношения",
               "found family", "обретенная семья", "adopted children", "приемные дети", "absent parents",
               "отсутствие родителей", "семья*"],
    "multiple-pov": ["multiple protagonists", "несколько главных героев", "взаимосвязанные сюжетные линии"],
    "time-travel": ["временной парадокс", "встреча через время", "попаданка в прошлое", "попаданцы во времени*"],
    "gender-bender": ["male to female", "из мужчины в женщину", "cross-dressing", "кроссдрессинг"],
}

# Labels that mean several tags at once (added to tags.COMPOUND). Listing the label itself keeps it as its own tag.
MORE_COMPOUND: dict[str, list[str]] = {
    "ожп": ["oc", "female-lead"],
    "омп": ["oc", "male-lead"],
    "прыжки между мирами": ["multiverse", "isekai"],
    "путешествия между мирами": ["multiverse", "isekai"],
    "world hopping": ["multiverse", "isekai"],
    "reincarnated in another world": ["reincarnation", "isekai"],
    "reincarnated in a game world": ["into-game", "reincarnation"],
    "перемещение в игровой мир": ["into-game"],
    "попаданка в злодейку": ["villainess", "isekai", "female-lead"],
    "попаданка в злодейку литмоб": ["villainess", "isekai", "female-lead"],
    "попаданка в чужое тело": ["transmigration", "female-lead"],
    "перерождение героини": ["reincarnation", "female-lead"],
    "попаданка в российскую империю": ["isekai", "female-lead", "russian-empire"],
    "попаданка и дракон": ["isekai", "female-lead", "dragons"],
    "попаданкавнаруто": ["fandom-naruto", "isekai", "female-lead"],
    "попаданка в наруто": ["fandom-naruto", "isekai", "female-lead"],
    "попаданец в дракона": ["isekai", "nonhuman-lead", "dragons"],
    "становление дракона": ["dragons", "nonhuman-lead", "progression"],
    "развитие дракона": ["dragons", "nonhuman-lead", "progression"],
    "властный дракон": ["dragons", "domineering-hero"],
    "развод с драконом": ["dragons", "divorce"],
    "дракон и истинная пара": ["dragons", "fated-lovers"],
    "одна ночь с драконом": ["dragons", "romance"],
    "генерал дракон": ["dragons", "military", "romance"],
    "ректор дракон": ["dragons", "academy", "romance"],
    "измена и развод": ["infidelity", "divorce"],
    "любовь и месть": ["romance", "revenge"],
    "магические питомцы": ["pets", "magic"],
    "мама попаданка": ["isekai", "female-lead", "childcare"],
    "кланы": ["aristocracy"],
    "кланы и интриги": ["aristocracy", "politics"],
    "родовая магия": ["aristocracy", "magic"],
    "боярърпг": ["boyar-anime", "litrpg"],
    "киберфеодализм": ["cyberpunk", "aristocracy"],
    "магический стимпанк": ["steampunk", "technomagic"],
    "прогрессорство и быт": ["progressorism", "slice-of-life"],
    "быт и прогрессорство": ["progressorism", "slice-of-life"],
    "бытовые секреты попаданки": ["isekai", "female-lead", "slice-of-life"],
    "изготовление артефактов": ["crafting", "artifacts"],
    "система и уровни": ["system", "rpg-elements"],
    "система улучшений и развития тела": ["system", "progression"],
    "сверхспособности и саморазвитие": ["special-abilities", "progression"],
    "mmorpg (литрпг)": ["virtual-reality", "litrpg"],
    "межгалактическая война": ["space", "war"],
    "космические войны": ["space", "war"],
    "космические сражения": ["space", "war"],
    "космические приключения": ["space", "adventure"],
    "великая отечественная война": ["war", "historical"],
    "исторические приключения": ["historical", "adventure"],
    "историческая фантастика": ["historical", "sci-fi"],
    "исторический детектив": ["mystery", "historical"],
    "исторические любовные романы": ["historical", "romance"],
    "историческая проза": ["historical", "contemporary-prose"],
    "политический детектив": ["mystery", "politics"],
    "шпионский детектив": ["spies", "mystery"],
    "детективная фантастика": ["mystery", "sci-fi"],
    "артефакт-детективы": ["mystery", "artifacts"],
    "боевая фантастика и фэнтези": ["action", "sci-fi", "fantasy"],
    "юмористическая фантастика и фэнтези": ["comedy", "sci-fi", "fantasy"],
    "социально-психологическая фантастика": ["sci-fi", "psychological"],
    "фантастический боевик": ["sci-fi", "action"],
    "мифологическое фэнтези": ["mythology", "fantasy"],
    "азиатское фэнтези": ["fantasy", "asian-setting"],
    "азиатское фэнтези (уся, сянься, культивация)": ["wuxia", "xianxia", "cultivation"],
    "любовное фэнтези, любовно-фантастические романы": ["romantic-fantasy"],
    "современные любовные романы": ["romance", "modern-day"],
    "короткие любовные романы": ["romance", "short-story"],
    "мини: любовный роман": ["romance", "short-story"],
    "мини: современный любовный роман": ["romance", "modern-day", "short-story"],
    "остросюжетный любовный роман": ["romance", "thriller"],
    "остросюжетные любовные романы": ["romance", "thriller"],
    "мистический любовный роман": ["romance", "supernatural"],
    "романтическая комедия": ["romance", "comedy"],
    "студенческий роман": ["romance", "school-life"],
    "военная академия": ["academy", "military"],
    "ангелы и демоны": ["angels", "demons"],
    "гарем рабов": ["harem", "slavery"],
    "male yandere": ["yandere", "possessive-love"],
    "мужчина-яндере": ["yandere", "possessive-love"],
    "детская фантастика: фэнтези": ["children", "fantasy"],
    "детская проза: приключения": ["children", "adventure"],
    "детская фантастика: ужасы и мистика": ["children", "horror"],
    "детские детективы: дети-сыщики": ["children", "mystery"],
    "зарубежная литература для детей": ["children"],
    "боевые искусства, спорт": ["martial-arts", "sports"],
    "попаданцы в другие миры": ["isekai"],
    # library genres (LitMir, RuLit, RoyalLib) and Rulate tags
    "любовно-фантастические романы": ["romantic-fantasy"],
    "зарубежные любовные романы": ["romance"],
    "криминальные детективы": ["mystery", "crime"],
    "полицейские детективы": ["mystery", "crime"],
    "иронические детективы": ["mystery", "comedy"],
    "детские приключения": ["children", "adventure"],
    "ужасы и мистика": ["horror", "supernatural"],
    "детективы и триллеры": ["mystery", "thriller"],
    "попаданец в аниме": ["isekai", "anime-based"],
    "попаданцы в аниме": ["isekai", "anime-based"],
    "алхимия и магия": ["crafting", "magic"],
    "боги и демоны": ["gods", "demons"],
    "быстрое развитие": ["progression"],
    "безжалостные персонажи": ["ruthless-lead"],
    "главный герой женщина": ["female-lead"],
    # WebNovel categories
    "urban": ["modern-day"],
    "eastern": ["fantasy", "asian-setting"],
    "realistic": ["realism"],
    "hurt/comfort": ["hurt-comfort"],
    "comfort": ["hurt-comfort"],
    # characters keep their own tag and add the fandom
    **{name: [name, "fandom-naruto"] for name in (
        "саске", "какаши", "итачи", "учиха", "мадара", "узумаки", "хината", "сакура", "орочимару", "гаара", "обито",
        "тобирама", "минато", "сакурахаруно", "сакура харуно", "харуно", "дейдара", "шикамару", "хидан", "сасори",
        "изуна", "кушина", "пейн", "цунаде", "ино", "курама", "сенджу", "саскеучиха", "саске учиха", "хаширама",
        "шисуи")},
    **{name: [name, "fandom-harry-potter"] for name in (
        "драко", "дракомалфой", "драко малфой", "малфой", "гермиона", "гермионагрейнджер", "гермиона грейнджер",
        "грейнджер", "северусснейп", "северус снейп", "снейп", "уизли", "ронуизли", "рон уизли", "сириусблэк",
        "сириус блэк", "томреддл", "том реддл", "дамблдор")},
    **{name: [name, "fandom-bts"] for name in (
        "чонгук", "jungkook", "тэхен", "taehyung", "чимин", "jimin", "юнги", "намджун", "хосок", "чончонгук")},
    **{name: [name, "fandom-stray-kids"] for name in (
        "минхо", "хенджин", "феликс", "банчан", "чонин", "джисон", "сынмин")},
    **{name: [name, "fandom-mha"] for name in ("тодороки", "мидория", "деку", "изуку", "бакуго")},
    **{name: [name, "fandom-bsd"] for name in ("дазай", "дазайосаму", "дазай осаму", "чуя", "ацуши")},
    **{name: [name, "fandom-aot"] for name in ("леви", "левиаккерман", "леви аккерман", "эрен")},
    **{name: [name, "fandom-tokyo-revengers"] for name in ("такемичи", "дракен", "майки")},
    **{name: [name, "fandom-hxh"] for name in ("киллуа", "гон", "хисока", "курапика")},
    **{name: [name, "fandom-undertale"] for name in ("санс", "эррор", "инк")},
    **{name: [name, "fandom-marvel"] for name in ("локи", "loki")},
    **{name: [name, "fandom-lotr"] for name in ("леголас",)},
    **{name: [name, "fandom-demon-slayer"] for name in ("танджиро",)},
    **{name: [name, "fandom-fairy-tail"] for name in ("нацу",)},
    **{name: [name, "fandom-ninjago"] for name in ("ллойд",)},
    **{name: [name, "fandom-maze-runner"] for name in ("ньют",)},
    **{name: [name, "fandom-naruto"] for name in ("чакра",)},
}

MORE_RULES: dict[str, list[str]] = {
    "slow-burn": ["romance"], "early-romance": ["romance"], "romantic-subplot": ["romance"],
    "love-interest-first": ["romance"], "lead-falls-first": ["romance"], "doting-love": ["romance"],
    "possessive-love": ["romance"], "domineering-hero": ["romance"], "enemies-to-lovers": ["romance"],
    "fated-lovers": ["romance"], "love-triangle": ["romance"], "first-love": ["romance"],
    "love-at-first-sight": ["romance"], "unrequited-love": ["romance"], "office-romance": ["romance", "modern-day"],
    "arranged-marriage": ["marriage", "romance"], "fake-relationship": ["romance"], "strong-love-interest": ["romance"],
    "clash-of-characters": ["romance"], "omegaverse": ["romance"],
    "machine-translation": ["translation"], "murim": ["martial-arts"], "elemental-magic": ["magic"],
    "summoning": ["magic"], "witches": ["magic"], "technomagic": ["fantasy", "magic"],
    "back-to-ussr": ["ussr", "time-travel"], "otome-game": ["into-game"], "survival-game": ["survival", "games"],
    "esports": ["games"], "past-life-memories": ["reincarnation"], "ghosts": ["supernatural"],
    "angels": ["supernatural"], "ancient-china": ["ancient-times"], "monster-girls": ["monsters"],
    "sword-and-magic": ["fantasy", "magic"], "fantasy-world": ["fantasy"], "rusreal": ["modern-day", "russia"],
    "russian-empire": ["historical"], "anime-based": ["fanfiction"], "oc": ["fanfiction"],
    "light-novel": ["japanese-novel"],
    **{tid: ["fanfiction"] for tid in MORE_TAGS if tid.startswith("fandom-")},
}

# Ukrainian names for every tag.
UK: dict[str, str] = {
    "pov-first": "Від першої особи", "pov-third": "Від третьої особи", "pov-second": "Від другої особи",
    "multiple-pov": "Кілька точок зору", "present-tense": "Теперішній час", "male-lead": "ГГ чоловік",
    "female-lead": "ГГ жінка", "op-lead": "Сильний ГГ / імба", "progression": "Прокачка / зростання сили",
    "smart-lead": "Розумний ГГ", "villain-lead": "ГГ лиходій", "anti-hero": "Антигерой",
    "nonhuman-lead": "ГГ не людина", "gender-bender": "Зміна статі", "hidden-identity": "Приховування особистості",
    "fantasy": "Фентезі", "sci-fi": "Фантастика", "litrpg": "ЛітРПГ", "gamelit": "Геймліт",
    "rpg-elements": "Елементи РПГ", "system": "Система", "game-messages": "Ігрові повідомлення в тексті",
    "virtual-reality": "Віртуальна реальність", "isekai": "Попаданці", "reincarnation": "Реінкарнація / переродження",
    "transmigration": "Вселення в чуже тіло", "regression": "Регресія / другий шанс",
    "time-travel": "Подорож у часі", "into-game": "Попаданець у гру", "into-book": "Попаданець у книгу",
    "alt-history": "Альтернативна історія", "boyar-anime": "Бояр-аніме", "apocalypse": "(Пост)апокаліпсис",
    "dystopia": "Антиутопія", "cyberpunk": "Кіберпанк", "steampunk": "Стімпанк", "space": "Космос",
    "space-opera": "Космоопера", "military": "Військове", "war": "Війна", "action": "Бойовик / екшн",
    "adventure": "Пригоди", "romance": "Любовний роман / романтика", "romantic-fantasy": "Любовне фентезі",
    "drama": "Драма", "angst": "Ангст", "fluff": "Флафф", "hurt-comfort": "Hurt/Comfort", "comedy": "Гумор",
    "horror": "Жахи", "mystery": "Детектив", "thriller": "Трилер", "supernatural": "Містика",
    "psychological": "Психологія", "philosophy": "Філософія", "tragedy": "Трагедія",
    "slice-of-life": "Повсякденність", "school-life": "Шкільне життя", "academy": "Академія",
    "urban-fantasy": "Міське фентезі", "dark-fantasy": "Темне фентезі", "epic-fantasy": "Епічне фентезі",
    "heroic-fantasy": "Героїчне фентезі", "historical": "Історичне", "wuxia": "Уся", "xianxia": "Сянься",
    "xuanhuan": "Сюаньхуань", "cultivation": "Культивація", "martial-arts": "Бойові мистецтва", "magic": "Магія",
    "mecha": "Меха", "vampires": "Вампіри", "werewolves": "Перевертні", "dragons": "Дракони", "demons": "Демони",
    "elves": "Ельфи", "gods": "Боги", "monsters": "Монстри", "undead": "Нежить", "necromancy": "Некромантія",
    "dungeon": "Підземелля", "survival": "Виживання", "kingdom-building": "Будівництво королівства",
    "progressorism": "Прогресорство", "crafting": "Крафт", "harem": "Гарем", "reverse-harem": "Зворотний гарем",
    "no-harem": "Без гарему", "villainess": "Лиходійка", "revenge": "Помста", "politics": "Політика / інтриги",
    "aristocracy": "Аристократія", "modern-day": "Сучасність", "medieval": "Середньовіччя",
    "mythology": "Міфологія", "superheroes": "Супергерої", "family": "Сім'я", "cooking": "Кулінарія",
    "sports": "Спорт", "music": "Музика", "ai": "Штучний інтелект", "slash": "Слеш", "femslash": "Фемслеш",
    "het": "Гет", "gen": "Джен", "lgbt": "ЛГБТ", "adult": "Для дорослих (18+)", "violence": "Насильство / жорстокість",
    "fanfiction": "Фанфік", "original": "Оріджинал", "translation": "Переклад", "short-story": "Оповідання",
    "poetry": "Поезія", "chinese-novel": "Китайська новела", "korean-novel": "Корейська новела",
    "japanese-novel": "Японське ранобе", "english-novel": "Англомовна новела", "demographic-shounen": "Сьонен",
    "demographic-seinen": "Сейнен", "demographic-shoujo": "Сьодзьо", "demographic-josei": "Дзьосей",
    "young-adult": "Підліткове", "au": "AU", "ooc": "ООС",
    # new tags
    "calm-lead": "Спокійний ГГ", "caring-lead": "Турботливий ГГ", "cold-lead": "Холодний ГГ",
    "ruthless-lead": "Безжальний ГГ", "cunning-lead": "Хитрий ГГ", "dense-lead": "Недогадливий ГГ",
    "naive-lead": "Наївний ГГ", "cute-lead": "Милий ГГ", "determined-lead": "Цілеспрямований ГГ",
    "confident-lead": "Впевнений ГГ", "shameless-lead": "Безсоромний ГГ", "cautious-lead": "Обережний ГГ",
    "hard-working-lead": "Працьовитий ГГ", "strong-from-start": "Сильний від самого початку",
    "mature-lead": "Дорослий ГГ", "child-lead": "ГГ дитина", "weak-lead": "Слабкий ГГ", "lazy-lead": "Лінивий ГГ",
    "loner-lead": "ГГ одинак", "orphan-lead": "Сирота", "god-lead": "ГГ бог", "mary-sue": "Мері Сью",
    "ojash-lead": "ГГ ояш", "not-ojash": "ГГ не ояш", "cheat-ability": "Чит-здібності",
    "special-abilities": "Надздібності", "morally-grey": "Сіра мораль", "oc": "ОЖП / ОЧП (оригінальний персонаж)",
    "fantasy-world": "Фентезійний світ", "sword-and-magic": "Меч і магія", "original-world": "Авторський світ",
    "alternate-world": "Альтернативний світ", "multiverse": "Безліч світів", "kingdoms": "Королівства та імперії",
    "royalty": "Королівська родина", "ancient-times": "Давній світ", "ancient-china": "Давній Китай",
    "asian-setting": "Азійський сетинг", "european-ambience": "Європейська атмосфера", "futuristic": "Майбутнє",
    "ussr": "СРСР", "back-to-ussr": "Назад у СРСР", "russian-empire": "Російська імперія", "russia": "Росія",
    "rusreal": "Русреал", "technomagic": "Технофентезі / техномагія", "magical-realism": "Магічний реалізм",
    "realism": "Реалізм", "contemporary-prose": "Сучасна проза", "classic": "Класика",
    "womens-fiction": "Жіночий роман", "dorama": "Дорама", "fairy-tale": "Казка", "litstrategy": "ЛітСтратегія",
    "nonfiction": "Нон-фікшн", "novel": "Роман", "novella": "Повість", "collection": "Збірка",
    "web-novel": "Веб-новела", "light-novel": "Ранобе / лайт-новела", "machine-translation": "Машинний переклад",
    "ai-generated": "Згенеровано ШІ", "adapted": "Є адаптації", "illustrated": "З ілюстраціями",
    "award-winning": "Відзначено нагородою", "children": "Дитяче", "anime-based": "За аніме та мангою",
    "power-ranks": "Ранги сили", "past-life-memories": "Спогади про минуле життя",
    "return-from-another-world": "Повернення з іншого світу", "reverse-isekai": "Зворотний ісекай",
    "games": "Ігри / геймери", "survival-game": "Гра на виживання", "esports": "Кіберспорт",
    "otome-game": "Отоме-гра", "streaming": "Стріми", "showbiz": "Шоу-бізнес", "business": "Бізнес",
    "wealthy": "Багаті персонажі", "poor-to-rich": "З грязі в князі", "farming": "Фермерство",
    "medicine": "Медицина / цілителі", "crime": "Кримінал", "assassins": "Асасини / вбивці",
    "spies": "Шпигуни / спецслужби", "secret-organizations": "Таємні організації", "religion": "Релігія",
    "pirates": "Пірати та море", "ninja": "Ніндзя", "samurai": "Самураї", "murim": "Мурім", "knights": "Лицарі",
    "weapon-master": "Майстер меча / зброї", "hunters": "Мисливці", "adventurers": "Авантюристи / гільдії",
    "elemental-magic": "Магія стихій", "summoning": "Призов / призивачі", "artifacts": "Артефакти",
    "magic-beasts": "Магічні звірі", "pets": "Улюбленці", "beastkin": "Звіролюди", "monster-girls": "Монстродівчата",
    "fantasy-races": "Фентезійні раси", "immortals": "Безсмертні", "ghosts": "Привиди / духи", "angels": "Янголи",
    "witches": "Відьми", "evolution": "Еволюція / мутації", "amnesia": "Амнезія", "hikikomori": "Хікікоморі",
    "maids": "Покоївки та слуги", "master-disciple": "Учитель і учень", "friendship": "Дружба",
    "loyal-subordinates": "Вірні підлеглі", "misunderstandings": "Непорозуміння", "heartwarming": "Зворушливе",
    "happy-ending": "Щасливий кінець", "emotional": "Емоційно", "power-struggle": "Боротьба за владу",
    "betrayal": "Зрада", "death": "Смерть / втрата близьких", "dark-past": "Темне минуле",
    "dark-world": "Похмурий світ", "depression": "Депресія / божевілля", "slavery": "Рабство",
    "human-experiments": "Експерименти над людьми", "childcare": "Виховання дітей", "siblings": "Брати і сестри",
    "mixed-orientation": "Змішана спрямованість", "other-orientation": "Інші види стосунків",
    "pregnancy": "Вагітність", "slow-burn": "Повільна романтика", "early-romance": "Рання романтика",
    "romantic-subplot": "Романтична лінія", "love-interest-first": "Кохана людина закохується першою",
    "lead-falls-first": "ГГ закохується першим", "doting-love": "Віддана кохана людина",
    "possessive-love": "Власницьке кохання", "domineering-hero": "Владний герой", "yandere": "Яндере",
    "tsundere": "Цундере", "strong-love-interest": "Сильна кохана людина", "handsome-lead": "Красивий головний герой",
    "beautiful-lead": "Красива героїня", "enemies-to-lovers": "Від ненависті до кохання",
    "clash-of-characters": "Протистояння характерів", "fated-lovers": "Справжня пара", "marriage": "Шлюб",
    "arranged-marriage": "Шлюб за домовленістю", "fake-relationship": "Фіктивні стосунки", "divorce": "Розлучення",
    "infidelity": "Зрада подружжя", "ntr": "НТР (нетораре)", "love-triangle": "Любовний трикутник",
    "first-love": "Перше кохання", "childhood-friends": "Друзі дитинства",
    "love-at-first-sight": "Кохання з першого погляду", "unrequited-love": "Нерозділене кохання",
    "age-gap": "Різниця у віці", "office-romance": "Службовий роман", "polygamy": "Багатоженство",
    "omegaverse": "Омегаверс", "mpreg": "Чоловіча вагітність", "ecchi": "Етті / фансервіс",
    "mature-themes": "Доросла тематика", "sexual-violence": "Сексуальне насильство",
    "abuse": "Жорстоке поводження / цькування", "suicide": "Суїцид", "drugs": "Наркотики / алкоголь",
    "profanity": "Нецензурна лексика", "incest": "Інцест", "loli": "Лолі",
    "fandom-naruto": "Наруто", "fandom-harry-potter": "Гаррі Поттер", "fandom-marvel": "Марвел",
    "fandom-bts": "BTS (k-pop)", "fandom-stray-kids": "Stray Kids (k-pop)", "fandom-kpop": "K-pop",
    "fandom-mha": "Моя геройська академія", "fandom-bsd": "Великий з бродячих псів", "fandom-aot": "Атака титанів",
    "fandom-tokyo-revengers": "Токійські месники", "fandom-genshin": "Геншин", "fandom-undertale": "Андертейл",
    "fandom-transformers": "Трансформери", "fandom-hxh": "Мисливець х Мисливець", "fandom-one-piece": "Ван Піс",
    "fandom-fairy-tail": "Хвіст феї", "fandom-demon-slayer": "Клинок, що розсікає демонів",
    "fandom-lotr": "Володар перснів / Толкін", "fandom-maze-runner": "Той, що біжить лабіринтом",
    "fandom-twilight": "Сутінки", "fandom-star-wars": "Зоряні війни", "fandom-warhammer": "Warhammer",
    "fandom-minecraft": "Майнкрафт", "fandom-winx": "Вінкс", "fandom-ninjago": "Ніндзяго", "fandom-fnaf": "ФНАФ",
    "fandom-hazbin": "Готель Хазбін", "fandom-countryhumans": "Countryhumans",
    "fandom-elder-scrolls": "The Elder Scrolls", "fandom-mdzs": "Магістр диявольського культу",
    "fandom-tgcf": "Благословення небожителів", "fandom-black-butler": "Темний дворецький",
    "crossover": "Кросовер", "reactions": "Реакції",
}
