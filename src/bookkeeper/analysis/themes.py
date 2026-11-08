"""Possible tags from the opening chapters.

While checking the narration, Bookkeeper already has the first few chapters in hand. This module counts telltale
words in them (Russian, Ukrainian and English): dragons, cultivation sects, levels and skills, a phone and the
internet… A tag is suggested when enough of its word groups show up often enough. These are only *possible* tags:
they are kept apart from the site's own tags, shown with a "?" and a percentage, and count in a search only when you
ask for them ("?dragons").

Each entry: word groups (regular expressions, matched on lowercase text), how many different groups must appear,
the least number of hits, the least density (hits per 10,000 words) and the density that counts as 100%."""
import re
from dataclasses import dataclass

VERSION = 1


@dataclass
class Theme:
    groups: list[str]
    need: int = 1
    min_hits: int = 3
    min_density: float = 2.0
    full_density: float = 10.0


def T(groups, need=1, min_hits=3, min_density=2.0, full_density=10.0) -> Theme:
    return Theme(groups if isinstance(groups, list) else [groups], need, min_hits, min_density, full_density)


THEMES: dict[str, Theme] = {
    "system": T([r"\bсистем[аеуыо]\b|\[систем|\bsystem\b|\[system", r"\bинтерфейс|\binterface|\bуведомлени|\bnotification|\bзадани[ея]\b|\bквест|\bquest"], 2, 5, 4, 15),
    "rpg-elements": T([r"\bуров(ень|ня|не|нем|ни|ней)\b|\blevel\b|\blvl\b", r"\bхарактеристик|\bstats?\b|\bатрибут|\battribute",
                       r"\bнавык|\bскилл|\bskills?\b", r"\bочк(и|ов|ами)\b|\bpoints?\b", r"\bопыт[ау]?\b|\bexp\b|\bxp\b"], 3, 8, 6, 25),
    "magic": T([r"\bмаги[яиюейч]|\bмагическ|\bмаг\b|\bмагов\b|\bmagic|\bmages?\b", r"\bзаклинани|\bзаклят|\bspells?\b",
                r"\bман[аыуе]\b|\bmana\b", r"\bчар(ы|ов|ами)\b|\bколдов|\bволшеб|\bwizard|\bsorcer"], 2, 6, 5, 20),
    "cultivation": T([r"\bкультивац|\bcultivat", r"\bци\b|\bqi\b", r"\bдань?тянь|\bdantian", r"\bсект[аыуе]?\b|\bsects?\b",
                      r"\bдао\b|\bdao\b", r"\bмеридиан|\bmeridian", r"\bстарейшин|\belders?\b"], 2, 6, 5, 20),
    "martial-arts": T([r"\bбоев(ые|ых|ым) искусств|\bmartial arts?", r"\bкунг-?фу|\bkung ?fu", r"\bрукопашн|\bединоборств"], 1, 3, 2.5, 10),
    "isekai": T([r"\bдруг(ой|ом|ого) мир|\bин(ой|ом|ого) мир|\banother world|\bother world",
                 r"\bпопал[аи]? (в|сюда)\b|\bперемест|\bперенес(ли|ло|ся|лась)|\bпризвал|\bsummoned|\btransported",
                 r"\bземл[яиеюй]\b|\bна земле\b|\bearth\b|\bмо(ем|ём|ей) мир"], 2, 4, 3, 12),
    "reincarnation": T([r"\bперерод|\bперерожд|\bреинкарнац|\breincarnat|\breborn\b|\brebirth",
                        r"\bпрошл(ой|ую|ая) жизн|\bprevious life|\bpast life|\bновой жизни"], 1, 2, 2, 8),
    "transmigration": T(r"\bв (этом|это|чужом|чужое|новом) тел|\bпрежн(ий|его|ему) (владел|хозя)|\bthis body\b|\boriginal owner|\bвселил", 1, 2, 1.5, 6),
    "regression": T(r"\bвернул(ся|ась|ось) в прошлое|\bрегресс|\bregress|\breturned to the past|\btime loop|\bвременн(ая|ой|ую) петл", 1, 2, 1.5, 6),
    "time-travel": T(r"\bмашин(а|у|ой) времени|\btime machine|\bпутешестви[ея] во времени|\btime travel", 1, 2, 1.5, 6),
    "dragons": T(r"\bдракон|\bdragon|\bвиверн|\bwyvern", 1, 3, 2, 10),
    "vampires": T(r"\bвампир|\bvampire|\bкровосос", 1, 3, 2, 10),
    "werewolves": T(r"\bоборот(ень|ня|ни|ней|нем|ням)\b|\bволколак|\bwerewol|\bликантроп|\blycan", 1, 3, 2, 10),
    "elves": T(r"\bэльф|\belf\b|\belves\b|\belven", 1, 3, 2, 10),
    "fantasy-races": T([r"\bгном(ы|ов|а|ам|ами)?\b|\bdwar(f|ves)", r"\bорк(и|ов|а|ам|ами)?\b|\borcs?\b", r"\bгоблин|\bgoblin",
                        r"\bтролл|\btrolls?\b"], 1, 4, 3, 12),
    "demons": T(r"\bдемон|\bdemons?\b|\bдьявол|\bdevils?\b", 1, 3, 2.5, 10),
    "gods": T(r"\bбогин|\bбожеств|\bбогов\b|\bбоги\b|\bбогам\b|\bgoddess|\bdeit(y|ies)|\bgods\b|\bпантеон", 1, 3, 2, 10),
    "angels": T(r"\bангел|\bangels?\b", 1, 3, 2, 10),
    "undead": T(r"\bнежит|\bзомби|\bскелет|\bлич\b|\bупыр|\bundead|\bzombie|\bskeleton|\bghoul", 1, 3, 2.5, 10),
    "necromancy": T(r"\bнекромант|\bnecroman", 1, 2, 1.5, 6),
    "ghosts": T(r"\bпризрак|\bпривидени|\bghosts?\b|\bspect(er|re)", 1, 3, 2, 8),
    "witches": T(r"\bведьм|\bwitch", 1, 3, 2, 8),
    "monsters": T(r"\bмонстр|\bчудовищ|\bmonsters?\b", 1, 4, 4, 15),
    "dungeon": T(r"\bподземель|\bданж|\bdungeon", 1, 3, 2, 10),
    "adventurers": T([r"\bгильди|\bguild", r"\bавантюрист|\badventurer"], 1, 3, 2.5, 10),
    "academy": T([r"\bакадеми|\bacadem", r"\bректор|\bфакультет|\bстудент|\bпрофессор|\bprofessor|\bлекци|\blecture|\bstudents?\b"], 2, 4, 3, 12),
    "school-life": T([r"\bшкол(а|ы|е|у|ой|ьник|ьниц)|\bschool", r"\bуро(к|ка|ке|ки|ков)\b|\bclassroom|\bclassmates?\b|\bодноклассн|\bучител|\bteacher|\bперемен(а|ы|у|е)\b"], 2, 5, 4, 15),
    "military": T([r"\bсолдат|\bsoldier", r"\bарми[яиюей]\b|\barmy\b|\bвойск", r"\bлейтенант|\bсержант|\bполковник|\blieutenant|\bsergeant|\bcolonel|\bбатальон|\bbattalion",
                   r"\bвоенн|\bmilitary"], 2, 6, 5, 20),
    "space": T([r"\bкосмос|\bкосмическ|\bouter space|\bspace ?ship", r"\bпланет|\bplanets?\b", r"\bзвездолет|\bstarship|\bspacecraft|\bорбит|\borbit",
                r"\bгалакт|\bgalax"], 2, 4, 3, 12),
    "apocalypse": T([r"\bапокалипс|\bapocalyp|\bконец света", r"\bмутант|\bmutant|\bрадиац|\bradiation|\bзаражен|\binfected",
                     r"\bвыживш|\bsurvivors?\b"], 2, 4, 3, 12),
    "modern-day": T([r"\bтелефон|\bсмартфон|\bphone\b|\bsmartphone|\bмобильн", r"\bинтернет|\binternet|\bсоцсет",
                     r"\bкомпьютер|\bноутбук|\bcomputer|\blaptop", r"\bавтомобил|\bметро\b|\bтакси\b|\bsubway|\btaxi\b",
                     r"\bофис|\boffice\b"], 3, 6, 5, 20),
    "medieval": T([r"\bрыцар|\bknights?\b", r"\bзам(ок|ка|ке|ком)\b|\bcastle", r"\bкорол(ь|я|ю|ем|евств)|\bking(dom)?\b",
                   r"\bбарон|\bгерцог|\bbaron|\bduke\b", r"\bтаверн|\btavern|\bтрактир", r"\bмеч(а|ом|у|и)?\b|\bswords?\b"], 3, 8, 6, 25),
    "aristocracy": T([r"\bаристократ|\baristocra", r"\bдворян|\bnobl(e|es|ility)\b", r"\bбарон|\bгерцог|\bкнязь|\bкняж|\bмаркиз|\bbaron|\bduke\b|\bduchess|\bmarquis",
                      r"\bклан(а|ы|ов)?\b|\bclans?\b|\bглав(а|у|ой) рода"], 2, 5, 4, 15),
    "royalty": T([r"\bпринц|\bprince", r"\bкорол(ь|я|ю|ем|ева|евы|еву)\b|\bking\b|\bqueen", r"\bимператор|\bимператриц|\bemperor|\bempress",
                  r"\bтрон|\bthrone"], 2, 5, 4, 15),
    "romance": T([r"\bпоцел|\bkiss", r"\bвлюб|\bin love\b|\bлюблю\b|\blove you", r"\bсвидани|\bon a date",
                  r"\bсердце (забил|стуч|ек|колот|пропуст)|\bheart (raced|pounded|skipped)"], 2, 4, 3, 12),
    "crafting": T([r"\bкузн|\bковк|\bblacksmith|\bforg(e|ing)\b", r"\bалхими|\bзель[яе]|\balchem|\bpotions?\b", r"\bкрафт|\bcraft"], 1, 4, 3, 12),
    "business": T([r"\bбизнес|\bbusiness", r"\bкомпани[яиюей]\b|\bcompany\b|\bфирм", r"\bприбыл|\bprofit|\bинвест|\binvest|\bсделк",
                   r"\bконтракт|\bcontract"], 2, 5, 4, 15),
    "medicine": T([r"\bврач|\bдоктор|\bdoctor|\bлекар|\bцелител|\bhealer", r"\bбольниц|\bhospital|\bклиник|\bclinic",
                   r"\bпациент|\bpatient|\bдиагноз|\bdiagnos|\bоперац"], 2, 5, 4, 15),
    "virtual-reality": T([r"\bвирт|\bvirtual", r"\bкапсул|\bcapsule|\bшлем\b", r"\bлогаут|\bвыйти из игры|\blog ?out\b|\blogged out",
                          r"\bnpc\b|\bнпс\b|\bнпц\b|\bнип\b"], 2, 4, 3, 12),
    "ussr": T([r"\bссср\b|\bсоветск", r"\bкомсомол|\bпартком|\bпартсобран|\bгенсек|\bпионер", r"\bтоварищ"], 2, 4, 3, 12),
    "pirates": T(r"\bпират|\bpirate|\bкорсар|\bcorsair", 1, 3, 2, 8),
    "ninja": T(r"\bниндзя|\bшиноби|\bninja|\bshinobi|\bчакр|\bchakra", 1, 3, 2, 8),
    "samurai": T(r"\bсамура|\bsamurai", 1, 3, 2, 8),
    "survival": T(r"\bвыжить|\bвыживани|\bsurviv", 1, 3, 3, 10),
    "revenge": T(r"\bотомст|\bмест(ь|и)\b|\brevenge|\bvengeance", 1, 3, 2, 8),
    "politics": T([r"\bинтриг|\bintrigue", r"\bзаговор|\bconspira|\bпереворот|\bcoup\b", r"\bполитик|\bpolitic|\bпарламент|\bparliament"], 2, 4, 3, 10),
    "war": T([r"\bвойн(а|ы|у|е|ой)\b|\bwar\b|\bwars\b", r"\bфронт\b|\bfront ?line", r"\bнаступлени|\boffensive\b|\binvasion|\bвторжени"], 2, 5, 4, 15),
    "crime": T([r"\bубийств|\bубийц|\bmurder", r"\bполици|\bpolice|\bследовател|\bдетектив|\bdetective", r"\bпреступ|\bcrime|\bcriminal|\bбандит|\bмафи|\bmafia"], 2, 5, 4, 15),
    "mystery": T([r"\bрасследован|\binvestigat", r"\bулик|\bclues?\b|\bподозрева|\bsuspect", r"\bдетектив|\bdetective|\bследовател"], 2, 4, 3, 12),
    "pregnancy": T(r"\bберемен|\bpregnan", 1, 2, 1.5, 6),
    "marriage": T([r"\bсвадьб|\bwedding|\bвенчани", r"\bмуж(а|ем|у)?\b|\bhusband", r"\bжен(а|ы|у|ой)\b|\bwife\b", r"\bбрак(а|е|у)?\b|\bmarri"], 2, 6, 5, 20),
    "divorce": T(r"\bразвод|\bdivorc", 1, 2, 1.5, 6),
    "infidelity": T(r"\bизмен(а|ы|у|ой|ил|ила|ял|яет)\b|\bлюбовниц|\bcheat(ed|ing) on|\baffair\b|\bmistress", 1, 3, 2, 8),
    "slavery": T(r"\bраб(ы|а|ов|ам|ами|ыня|ыни|ство|ства)?\b|\bslaves?\b|\bневольни", 1, 3, 2.5, 10),
    "drugs": T(r"\bнаркот|\bdrugs?\b|\bкокаин|\bcocaine|\bгероин(а|ом)?\b", 1, 2, 1.5, 6),
    "profanity": T(r"\bбля\b|\bблять|\bблядь|\bхуй|\bхуя|\bхуе|\bпизд|\bебат|\bебан|\bъеб|\bfuck|\bshit\b", 1, 4, 3, 12),
    "adult": T([r"\bсекс|\bsex\b|\bоргазм|\borgasm|\bэрекц|\berection|\bвозбужд|\barous", r"\bсоск|\bnipple|\bbreasts?\b",
                r"\bобнажен|\bголая\b|\bголый\b|\bnaked\b|\bnude\b"], 2, 5, 4, 15),
    "violence": T([r"\bкров(ь|и|ью|ав)|\bblood", r"\bтруп|\bcorpses?\b", r"\bубил|\bубить|\bkill", r"\bкишк|\bguts\b|\bвыпотрош|\bрасчлен|\bdismember|\bgore\b"],
                  3, 8, 6, 25),
    "kingdom-building": T([r"\bпоселени|\bдеревн|\bvillage|\bsettlement", r"\bпострои|\bстроител|\bbuilding\b", r"\bкрестьян|\bpeasant|\bжител"], 3, 6, 5, 18),
    "summoning": T(r"\bпризыв|\bпризва|\bsummon", 1, 3, 2, 8),
}

_COMPILED = {tag: [re.compile(g) for g in theme.groups] for tag, theme in THEMES.items()}
_UK = str.maketrans({"і": "и", "ї": "и", "є": "е", "ґ": "г", "ё": "е"})


def detect(texts: list[str]) -> list[dict]:
    """[{tag, score 0..1, per_10k}] for the possible tags found in the opening chapters, likeliest first."""
    text = "\n".join(texts).lower().translate(_UK)
    words = max(1, len(re.findall(r"\w+", text)))
    if words < 800:
        return []
    out = []
    for tag, theme in THEMES.items():
        counts = [len(rx.findall(text)) for rx in _COMPILED[tag]]
        hits, groups = sum(counts), sum(1 for c in counts if c)
        density = hits * 10000 / words
        if hits >= theme.min_hits and groups >= theme.need and density >= theme.min_density:
            out.append({"tag": tag, "score": round(min(1.0, density / theme.full_density), 2),
                        "per_10k": round(density, 1)})
    out.sort(key=lambda x: -x["score"])
    return out
