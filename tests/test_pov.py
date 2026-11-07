from bookkeeper.analysis.pov import analyse, narration_only, game_system_lines
from bookkeeper.analysis.text import detect_lang, html_to_text


def _repeat(par: str, n: int) -> str:
    return "\n".join([par] * n)


def test_russian_dash_dialogue_keeps_authors_words():
    text = "— Пойдём, — сказал я и вышел.\n— Я не знаю.\n— Ты кто? — спросила она. — Откуда ты?"
    narr = narration_only(text)
    assert "сказал я и вышел" in narr
    assert "не знаю" not in narr
    assert "спросила она" in narr
    assert "Откуда" not in narr


def test_quotes_and_system_messages_are_removed():
    text = 'He said, "I will go." [Вы получили навык: Огонь]\n«Я тоже», — подумал он.'
    narr = narration_only(text)
    assert "I will" not in narr and "навык" not in narr and "Я тоже" not in narr


def test_first_person_russian_with_gender():
    par = ("Я проснулся рано утром и долго смотрел в потолок. Мне не хотелось вставать, но я заставил себя "
           "подняться. Он уже ждал меня на кухне, и я молча налил себе чаю. Мой день начинался как обычно.")
    r = analyse([_repeat(par, 40)])
    assert r["pov"] == "first"
    assert r["narrator"] == "male"


def test_female_narrator_russian():
    par = ("Я проснулась рано утром и долго смотрела в потолок. Мне не хотелось вставать, но я заставила себя "
           "подняться. Он уже ждал меня на кухне, и я молча налила себе чаю. Я была рада его видеть.")
    r = analyse([_repeat(par, 40)])
    assert r["pov"] == "first"
    assert r["narrator"] == "female"


def test_third_person_with_dialogue_full_of_i():
    par = ('"I don\'t know what I want," she said. He looked at her and shook his head. '
           '"I think I should go," he replied, and she watched him leave. They never spoke of it again.')
    r = analyse([_repeat(par, 60)])
    assert r["pov"] == "third"


def test_mixed_book():
    first = _repeat("I walked to the door and I opened it. My hands were shaking as I stepped outside.", 150)
    third = _repeat("She walked to the door and opened it. Her hands were shaking as she stepped outside.", 150)
    r = analyse([first, third, first, third])
    assert r["pov"] == "mixed"


def test_ukrainian():
    par = ("Я прокинувся рано вранці й довго дивився в стелю. Мені не хотілося вставати, але я змусив себе "
           "підвестися. Він уже чекав мене на кухні, і я мовчки налив собі чаю.")
    text = _repeat(par, 40)
    assert detect_lang(text) == "uk"
    r = analyse([text])
    assert r["pov"] == "first"
    assert r["narrator"] == "male"


def test_game_system_lines():
    text = "[Получен новый навык: Огненный шар]\nСила: 12\nЛовкость: 8\nОн вздохнул.\n[Level up!]"
    assert game_system_lines(text) >= 3


def test_html_to_text_keeps_paragraphs():
    html = "<p>Первый&nbsp;абзац, <i>курсив</i>.</p><p>— Реплика, — сказал он.</p><br>Третий"
    assert html_to_text(html).split("\n") == ["Первый абзац, курсив.", "— Реплика, — сказал он.", "Третий"]
