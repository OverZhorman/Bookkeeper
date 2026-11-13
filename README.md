# Bookkeeper

Your own catalog of books and web novels from the sites you read. It merges every site's tags into one list, adds the tags authors forgot, and works out from the text whether a book is told in the **first person**.

- **Collects books** from your sites slowly in the background: title, author, description, genres, tags, length, status, likes and rating.
- **One shared tag list** of about 330 tags, each with an English, Russian and Ukrainian name. «ЛитРПГ», «LitRPG», «LITRPG» and «Lit-RPG» are one tag, and so are «Slow Romance» and «Медленная романтика». Rules add the obvious ones: a LitRPG book also gets "RPG / game elements".
- **Detects narration** (first, second or third person, or mixed) from each book's opening chapters. For Russian and Ukrainian first-person books it also tells a male narrator from a female one («я пошёл» / «я пошла»).
- **Finds the same book on different sites** and shares tags between the copies.
- **Search by tags with simple logic**: `Romance −Harem`, `(Isekai | Reincarnation) Magic`, in any language, with suggestions as you type. Every tag has a page with its aliases, parent and child tags, related tags and anti-tags.
- **Possible tags** found in the opening chapters (system messages, cultivation, dragons…), kept apart from the certain ones.
- **Fix site labels in bulk**: labels Bookkeeper doesn't recognize are listed most common first, with suggestions. Say once what one means (or hide it) and every book with it follows.
- **Edit any tag**: names in three languages, description, aliases, parent and child tags, anti-tags; or make tags of your own.
- **Improve tags with an AI chat**, many at a time: aliases of a broad tag become child tags (*Monster protagonist* under *Non-human lead*), wrong aliases move, links get fixed.
- **Filter and sort by anything**: fanfiction and fandoms, orientation, age rating (G to NC-21), books not updated for a month or a year, and more. Keep shelves (want to read, reading, read, dropped, hidden), favourites and notes.
- **Downloads** books as **EPUB, FB2 or TXT** for your e-reader. Logged in, downloads include the chapters you bought.
- **Logs in for you**, and can hand a book to a browser extension such as ExLoader.
- **18+ books** are collected like any other; one switch hides them.

Everything runs on your own computer. Nothing is uploaded anywhere.

## Install on Windows

1. On this GitHub page press the green **Code** button, then **Download ZIP**.
2. Unpack the ZIP into a folder of your choice, for example `Documents\Bookkeeper`.
3. Double-click **`Bookkeeper.bat`**.

The first start takes a few minutes. It downloads a small tool called [uv](https://docs.astral.sh/uv/), which installs Python and the libraries Bookkeeper needs (about 150 MB). Later starts take a few seconds. Bookkeeper then opens in your browser at <http://127.0.0.1:8765/>.

Keep the black window open while you use Bookkeeper. Closing it stops Bookkeeper.

If Windows says "Windows protected your PC", press **More info**, then **Run anyway**. It says this about any downloaded `.bat` file.

## First steps

1. Open **Sites** and switch on the sites you want. Collecting starts right away.
2. Open **Library**. Books appear as they are collected. In the filters, pick **Narration → 1st person**.
3. Click a book to see its details. From there you can correct its narration, put it on a shelf or download it.

Collecting runs at a slow, steady pace, about one page every 1–2 seconds per site, so the sites don't ban you. For each book that's about 2–4 pages: the catalog, the book's page, and the opening chapters. Big sites take days to collect fully. Popular books come first, so the library is useful within the first hour. You can close Bookkeeper at any time; it continues where it stopped.

## Logging in

Some sites show 18+ books, or chapters you bought, only to logged-in readers. On the **Sites** page, sites that support it have an **Account** box:

- **Log in…** opens the site's login page in a Waterfox window. Log in as usual: captchas, codes from e-mail and "log in with VK" all work. Bookkeeper keeps the session.
- **Use my Waterfox login** copies the login from your own Waterfox, if you're already logged in there.
- **Log in automatically with a saved password** (Author.Today, Rulate, Ficbook): Bookkeeper logs in by itself in a hidden window, and again whenever the login runs out. The password is encrypted with your Windows account and never leaves your computer.

Every 6 hours Bookkeeper checks that each login still works. Logged in, it reads what your account can read: 18+ books, and the chapters you bought, which downloads then include.

| Site | Login |
|---|---|
| Author.Today | Window, Waterfox login, or saved password (automatic) |
| Rulate | Window, Waterfox login, or saved password (automatic) |
| Ficbook | Window, Waterfox login, or saved password (automatic) |
| Litnet | Window or Waterfox login (its login has several steps) |
| RanobeLIB | Window (press «Войти» there) |

## Downloading with a browser extension

Some sites don't let you download even what you bought, but browser extensions can, for example [ExLoader](https://addons.mozilla.org/firefox/addon/exloader/) for Author.Today, Ficbook and Readli. Open a book in Bookkeeper and press **Open in my Waterfox**: the book opens in your normal Waterfox, where your extensions are. Download it with the extension there. For the next 30 minutes Bookkeeper watches your downloads folder; the file appears under the book and on the Downloads page, and a copy is kept in `data\downloads`.

## 18+ books

18+ and 21+ books are collected by default. To keep them out of sight, tick **Hide 18+ books** in the library filters (under **More**); **Only 18+ books** shows just those. A site's own 18+ mark and an 18+ tag both count. Each site's settings still have **Collect 18+ books** if you don't want them in your library at all.

## Waterfox

Bookkeeper uses Waterfox (or Firefox) for logins and site tests when it is installed, and Microsoft Edge otherwise. It runs its own Waterfox profile in `data\browser-profile\waterfox`, so your normal profile, tabs and extensions aren't touched. The choice, the Waterfox program and your downloads folder can be changed on the Sites page under **Browser**. Author.Today chapters are still read through Edge.

## How narration is detected

Characters say "I" all the time, even in third-person books, so pronouns can't simply be counted. For each book, Bookkeeper:

1. reads the opening chapters (usually 3, which are almost always free);
2. removes dialogue (`— Реплика, — сказал он.`, «…», "…"), quoted thoughts, game messages in `[brackets]` and author or translator notes;
3. counts "I / я" against "he / she / он / она" in the narration that's left, chunk by chunk;
4. calls the book **first**, **third** or **second person**, **mixed** when the chunks disagree, or **unsure**.

**Accuracy.** I tested it on 41 books whose narration I knew: 21 Russian web novels from Ranobelib and 20 English classics. The settings were fixed before the test. Result: **40 right, 1 "unsure", 0 wrong**, and narrator gender right for all 11 Russian first-person books. To run the test again yourself: `uv run python tools/validate_pov.py`.

**Priority.** When there are several sources of information, this order wins:

1. your own correction;
2. the site's own tag (for example «от первого лица»);
3. the text check;
4. a copy of the same book on another site.

You can filter by each of these sources.

## Sites

| Site | Status |
|---|---|
| RanobeLIB | ✅ Working |
| Author.Today | ✅ Working. Chapter text is read through Microsoft Edge on your computer, because the site scrambles it for anything that isn't a browser |
| Flibusta | ✅ Working: the whole library (over 700,000 books) from Flibusta's catalog file, then genres page by page and descriptions in the background. Pick the languages in the site's settings (Russian, Ukrainian, Belarusian and English to begin with). Downloads use Flibusta's own FB2/EPUB files |
| Litnet | ✅ Working (Russian and Ukrainian books) |
| Wuxia.click | ✅ Working (English translations, with NovelUpdates-style tags) |
| Wattpad | ✅ Working. Wattpad is too big to collect whole, so Bookkeeper collects the results of your search terms (Sites → Wattpad → Settings) |
| Kubikus forum | ✅ Working. It adds no books of its own: it reads the recommendation sections and marks the books people recommend, including books that arrive in your library later. Filter with "Only books recommended on forums" |
| RanobeHub | ✅ Working. Long books get their full chapter list during a download |
| Ranobes | ✅ Working (with NovelUpdates-style tags in Russian) |
| Samlib | ✅ Working. Too big to collect whole, so Bookkeeper reads the most-read novel-length works in the genres you choose (Sites → Samlib → Settings) |
| Rulate | ✅ Working. Logged in, downloads include the paid chapters you bought |
| Ficbook | ✅ Working. Too big to collect whole, so Bookkeeper reads the catalogs you choose (by default original works); spam posts are skipped. ExLoader can download Ficbook works too |
| LitMir | ✅ Working (the site-wide list, most popular first) |
| RuLit | ✅ Working (the site-wide list, most popular first) |
| RoyalLib | ✅ Working. Downloads use its own FB2 / EPUB / TXT files. It shows a captcha to fast readers, so Bookkeeper reads it slowly and stops if the captcha appears |
| WebNovel | ✅ Catalog only (titles, tags, ratings). WebNovel protects its chapter text, so there's no narration check or download there |
| Litvek | ✅ Working: its web fiction (*Самиздат, сетевая литература*, about 95,000 books) with each book's keywords; another genre or the whole library can be chosen in its settings. Its robots.txt asks programs not to use the download links, so a download is put together from the online reader. Some books are only a fragment there |
| WTR-LAB | ✅ Catalog only (titles, genres, NovelUpdates-style tags, ratings) of its machine translations, about 100,000 novels. Its robots.txt asks programs not to read chapters, so there's no narration check or download there |
| FreeWebNovel | ✅ Working (English translations and originals, about 16,000 novels). Its lists show only 1,000 novels each, so Bookkeeper reads many of them, every genre included |
| FanMTL | ✅ Working: machine translations of Chinese web novels, many of them fan fiction (Naruto, One Piece, Douluo, Marvel, Pokémon), about 165,000 novels. Its whole list is read by popularity, then by date added; fandoms become fandom tags |
| Royal Road, NovelUpdates, Scribble Hub, FanFiction.net, Archive of Our Own | Show a bot check; the site test now opens Waterfox so you can pass it |

If a site shows a bot check or blocks requests, Bookkeeper stops working on that site and says so on the Sites page. It doesn't keep retrying.

### Testing the sites that don't have a connector yet

Some sites block the server Bookkeeper was built on, so their connectors need pages seen from your computer:

1. On the **Sites** page, in **Coming next**, press **Test from this computer** next to a site.
2. Bookkeeper slowly opens a few of that site's pages: home, catalog, one book, one chapter.
3. If a page shows an "are you human?" check, a Waterfox window opens (Edge if Waterfox isn't installed). Complete the check yourself and keep the window open until the page has loaded; the test then continues.
4. Press **Download the test ZIP** and send the file to whoever is writing the connector.

The ZIP contains only those pages as the site showed them, plus a short report.

## Searching by tags

Type into the **Tags** field in the library filters. Suggestions appear as you type, in English, Russian or Ukrainian: **Tab** puts one in, **Enter** searches. The buttons under the field add the operators (rest the mouse on one to see what it does), and the line under the field says how your search reads.

| You type | You get |
|---|---|
| `Romance` | books with the tag (any name or alias works: Романтика, Любовь…) |
| `−Romance` or `!Romance` | books without it (also `NOT Romance`, `НЕ Romance`) |
| `Romance Magic` | both (also `Romance & Magic`, `Romance, Magic`) |
| `Isekai \| Reincarnation` | either one (also `OR`, `ИЛИ`, `АБО`) |
| `(Isekai \| Reincarnation) −Harem` | brackets group things |
| `?System` | has the tag, or possibly has it (found in the opening chapters) |
| `−?Harem` | not even possibly |
| `"slow burn"` | a name with spaces (names Bookkeeper knows work without quotes too) |
| `fandom*` | every tag whose name starts with "fandom" |

The **Fandoms** field works the same way, but every name in it is a fandom. Rest the mouse on any tag for a short description; **About this tag** (or **all tags** above the field) opens its page: names in three languages, aliases, parent tags (broader ones every book with it also gets), child tags (narrower ones that can't appear without it, numbered 1, 2, 2.1…), related tags (usually together in your library) and anti-tags.

**Possible tags.** While reading a book's opening chapters for the narration, Bookkeeper also counts words that point to a tag. Tags that come up often enough are added as *possible* (dotted on the book page, with how strongly they showed up). Plain tag searches ignore them; `?Tag` includes them. Books checked by older versions are read again in the background, a few at a time (switch off **Check narration** in a site's settings to stop that).

## Fixing site labels

Some labels from the sites aren't one of Bookkeeper's shared tags: Wattpad hashtags, character names, series names, typos. Open **Fix site labels** (from **All tags**, the Sites page or a label's own page). It lists those labels, most common first, with:

- **suggestions**: one click says the label means that tag («саске» → Naruto, «ковры на стенах» → Back to the USSR);
- **Means… type a tag** for anything else, and **+ another tag** when a label means two things («попаданцы в магический мир» → Isekai + Magic);
- **Hide** for junk labels (site names, years), which removes them from every book;
- **Leave as is** for labels that are fine as their own tag, which takes them off the list;
- **Undo**, which puts a label back the way Bookkeeper read it before.

A fix applies to every book with that label, written any way («Попаданиевдругоймир», «#попаданиевдругоймир»), and to books that arrive later. When Bookkeeper maps a label to the wrong tag, press ✎ next to it under "Written on the sites as" on the tag's page. Fixes are saved in the `[fixes]` table of `data\my_tags.toml`; **My fixes** lists them all.

### Fixing labels with an AI chat

Thousands of labels are a lot to fix by hand, so an AI chat (Gemini, ChatGPT, …) can do the reading, on your own subscription and without any API key:

1. On **Fix site labels**, press **✨ Fix with an AI chat**, pick a batch size (250 labels is about 70,000 characters) and press **Copy the request**. It holds the most common labels (with the site and search filters you picked), what their books usually have and a few titles, the list of shared tags, and instructions.
2. Paste it into the chat and send it, or use **Download as a file** and attach the file. The chat answers with one line per label: which shared tags it means, hide it, leave it as it is, or a new tag it suggests.
3. Copy the chat's whole reply into step 2 and press **Check the answers**. You see every answer first; ones Bookkeeper can't use (an unknown tag, a label that isn't in your library) are left out, and you can untick any others.
4. **Apply** fixes them all at once. They leave the list, so the next **Copy the request** brings the next batch.

Each import can be undone as a whole: right after it, or later under **My fixes**. An import never touches the names of shared tags, only labels that are still unrecognized.

The chat can also suggest new tags, with their **parent tags**: several labels like «гг монстр» and «monster protagonist» become a new *Monster protagonist* tag under *Non-human lead*, so their books get both. The check shows each new tag's parents before you apply it.

### Improving tags with an AI chat

Many site labels end up as aliases of a broad tag although they name something narrower. On the **Tags** page, press **✨ Improve tags with an AI chat** (or **✨ Improve with an AI chat** on one tag's page). The request holds the tags with the most aliases (or the ones you name), their parent, child and anti-tags, every alias with how many books have it, and the list of shared tags. The chat answers with:

- **new child tags**, and which aliases move to them (*Non-human lead* → *Monster protagonist*, *Humanoid protagonist*, *Genderless protagonist*…). Books keep the broad tag through the parent link;
- aliases that mean something else and move to the right tags, real labels to keep apart (as labels of their own), or
  junk to hide;
- **new aliases**: other ways sites and readers write a tag, and new combined labels (one label meaning two tags);
- **better names**, categories and descriptions (a renamed tag keeps its old name as an alias);
- parent, child and anti-tag links to add or remove between shared tags, and **related tags** ("see also") to link.

Check the answers, untick any you don't want, and apply. Tags you applied an answer for are marked as reviewed, so the next request brings the next ones (tick **again, with reviewed tags** to include them). Every import can be undone as a whole under **Earlier imports**.

## Editing tags

Open **Tags** in the top bar and click a tag, then **✎ Edit tag**. There you can change:

- its names in English, Russian and Ukrainian, its category and its description;
- its **aliases**: other names a site might use. Every book with a label written that way gets the tag;
- its **parent tags** (broader tags every book with it also gets) and **child tags** (narrower tags that can't appear without it);
- its **anti-tags** (tags that contradict it);
- **see also**: related tags worth a look from its page. They don't change any book's tags.

Every change is saved at once and applies to every book. **Undo all my changes** puts one of Bookkeeper's own tags back. **+ New tag** on the Tags page makes a tag of your own, and on an unrecognized label's page **Make it a shared tag** turns that label into one (its other spellings join it). Tags you made can be deleted.

## Your own tags and rules

Everything you change in the interface is saved in `data\my_tags.toml`, so it survives updates. You can also edit that file in Notepad; it explains itself:

- `[synonyms]` and `[fixes]`: what site labels mean (`"попаданец в зомби-апокалипсис" = ["isekai", "undead", "apocalypse"]`);
- `[rules]`: parent tags (`"harem" = ["romance"]`), and `[rules_off]` to switch one of Bookkeeper's own off;
- `[anti]` and `[anti_off]`: anti-tags;
- `[related]`: related tags ("see also");
- `[tags.<id>]`: names, category and description of a tag.

After editing the file by hand, press **Re-apply my tag rules** on the Sites page.

## Your data

Everything personal lives in the `data` folder next to `Bookkeeper.bat`:

- `library.db`: your library, shelves and notes;
- `downloads\`: books you downloaded;
- `logs\`: what Bookkeeper did, useful if something goes wrong;
- `browser-profile\`: the browser profiles Bookkeeper uses for logins, site tests and Author.Today;
- `accounts\`: your logins and saved passwords, encrypted with your Windows account.

To back up, copy the `data` folder.

## Updating

Download the new ZIP and unpack it over the old folder. Your `data` folder is kept. If you cloned the repository with Git, run `Update.bat` instead.

## Fair use

Bookkeeper is for your personal reading. It reads what the sites show to any visitor, or, when you log in, what your account can read, including chapters you bought. It doesn't get around paywalls. It reads each site slowly. Please don't share the database or the downloaded books.

## Troubleshooting

- **"No usable browser found"** on the Author.Today card: Bookkeeper needs Microsoft Edge (built into Windows) or Google Chrome.
- **Waterfox isn't found**: enter the path to `waterfox.exe` on the Sites page under **Browser**.
- **A login doesn't work**: press **Log in…** and log in yourself in the window; the Account box shows what went wrong.
- **A site shows "Blocked"**: check that the site opens in your normal browser, then press **Try again** on its card. If it's blocked all the time, raise the pause between requests in that site's settings.
- **Nothing happens when I start it a second time**: Bookkeeper is already running, and the second start just opens the page again.
- Anything else: look in `data\logs\bookkeeper.log`.

## For developers

```
uv sync
uv run --group dev pytest          # unit tests
uv run bookkeeper --no-browser     # start without opening a browser
uv run python tools/validate_pov.py
```

Code layout (`src/bookkeeper/`):

- `sites/`: one connector per site. Each one implements `discover`, `details`, `chapters` and `chapter_text`.
- `analysis/pov.py`: the narration detector. `analysis/themes.py`: possible tags from the opening chapters.
- `tags.py`, `tagdata.py`, `tagdocs.py`: the shared tag list (English, Russian and Ukrainian names), synonyms, rules, descriptions and anti-tags.
- `tagquery.py`: the tag search language. `search.py`: library filters, suggestions and tag pages.
- `labels.py`: fixing site labels for every book at once (the Fix site labels page).
- `tagedit.py`: editing tags from their pages (saved in `data/my_tags.toml`).
- `tagai.py`: improving tags with an AI chat (aliases to child tags, links), many at a time.
- `browser.py`: Waterfox (WebDriver BiDi) and Edge (Playwright).
- `accounts.py`, `secret.py`: logins, saved passwords and sessions (encrypted with Windows DPAPI).
- `handoff.py`: picking up books downloaded with a browser extension.
- `matching.py`: matching the same book across sites.
- `crawler.py`: the background workers.
- `export.py`: TXT, FB2 and EPUB files.
- `web/`: the local server and the interface (plain JavaScript, no build step).
