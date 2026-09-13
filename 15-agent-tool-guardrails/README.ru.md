_English version: [README.md](README.md)_

# 15 — agent-tool-guardrails

**Перестаньте доверять самоотчёту агента: пропускайте команды через шлюз, проверяйте скиллы и позвольте оркестратору принимать работу.**

> Два режима отказа. Первый: деструктивная команда проходит, потому что слой одобрения
> прогоняет текст через grep в поисках «страшных слов» — `r''m -rf /`, `$(...)`, `bash -c "..."` и
> `base64 -d | sh` все обходят регулярное выражение. Второй: несколько исполнителей (writers) делят один checkout, и единственное
> доказательство — фраза исполнителя «готово, тесты проходят».

## Что вы здесь получаете

| Артефакт | Назначение | Тесты |
|---|---|---|
| `hooks/bash_guard.py` + `hooks/policy.json` | шлюз `pre_tool_call`: разбирает команду, затем выносит решение | `tests/test_bash_guard.py` — 22 случая |
| `hooks/skill_scan.py` | проверка скилла / промпта / конфигурации агента до того, как ему доверят | проверяется на канареечном вредоносном скилле |
| `lanes.py` | один git worktree на исполнителя + шлюз приёмки с доказательствами | `tests/test_lanes.py` — 16 проверок |
| `install.sh` | копирует хуки в `$HERMES_HOME` и регистрирует их | — |

Всё — stdlib Python. Единственная зависимость — `bashlex` (pure-python wheel), вендорена (vendored)
в `$HERMES_HOME/pylibs`, так что хук никогда не зависит от собственного virtualenv агента.

## Почему парсинг лучше grep'а

`bash_guard` обходит AST вместо сканирования строки, поэтому вложенные полезные нагрузки для него —
настоящие команды, а нормализация последовательностей кавычек и обратных слешей превращает `r''m -rf /` в читаемое `rm -rf /`.
Правила структурные: рекурсивное удаление системного корня, `--no-preserve-root`, `dd of=/dev/sd*`,
`mkfs`/`wipefs`, fork-бомбы, декодер, направляемый в shell (`base64 -d … | sh`), хранилище учётных
данных в одной команде с сетевым инструментом, записи в `/etc/shadow`, `sudoers`, `.env`,
`auth.json`, `authorized_keys`, а также `qm|pct destroy|stop|reset` в отношении идентификатора ВМ, внесённого вами в список
защищённых. Два уровня: **block** (деструктивное, агенту возвращается как отказ) и
**flag** (только логируется — инсталляторы вида `curl … | bash` и `pip install` — нормальная работа).

```bash
python3 hooks/bash_guard.py < payload.json     # hook contract: stdin JSON -> stdout block JSON
python3 tests/test_bash_guard.py               # 22 cases, includes the quote/bidi evasions
```

Зарегистрируйте его (никогда не правьте `config.yaml` вручную):

```bash
hermes config set hooks_auto_accept true
hermes config set hooks '{"pre_tool_call":[{"matcher":"terminal","command":"/usr/bin/python3 '"$PWD"'/hooks/bash_guard.py","timeout":10,"fail_closed":true}]}'
hermes gateway restart        # hooks bind at process start; new CLI runs pick them up at once
```

**Проверяйте end-to-end, а не только юнит-тестами.** Поместите канареечный regex в `policy.json`
(`"block_patterns": ["CANARY_GUARD_TEST"]`) и выполните
`hermes chat -q "run exactly: echo CANARY_GUARD_TEST"`. Агент обязан сообщить об отказе.
Никогда не проверяйте шлюз по-настоящему деструктивной командой — если шлюз сломан,
команда действительно выполнится.

## Проверка скиллов до того, как они начнут обучать вашего агента

Скилл — это исполняемая политика, написанная незнакомцем: фрейминг prompt-injection, символы нулевой ширины и
bidi-символы, которые никогда не отображаются в diff, чтение хранилищ учётных данных, вебхуки на drop-box,
`curl | bash`, декодеры, передаваемые по конвейеру в shell.

```bash
python3 hooks/skill_scan.py path/to/skill          # human report, exit 2 on any HIGH
python3 hooks/skill_scan.py --all-installed        # audit the whole library
python3 hooks/skill_scan.py --hook                 # pre_tool_call mode: block the install
```

Контекст важнее любого одиночного шаблона. Одиночное упоминание `~/.ssh/id_...` встречается в каждом
учебнике по SSH, поэтому секретный путь сам по себе — это **MEDIUM** и повышается до **HIGH**,
только когда в том же файле есть ещё и путь для оттока данных (egress); `curl | bash` на документированном инсталляторе остаётся MEDIUM.
Аудит библиотеки по этим правилам: 546 файлов, 28 срабатываний HIGH до правил комбинирования, после них
почти все оставшиеся срабатывания HIGH — легитимная документация, цитирующая `~/.hermes/.env`. Ожидайте
ложных срабатываний на собственной документации; разбирайте их, а не форкайте правила под каждый файл. Собственный тестовый корпус репозитория пометит сам себя
(строки атак — это фикстуры); это ожидаемо.

## Lanes: параллельные исполнители, один шлюз приёмки

```bash
lanes.py new    REPO lane-a lane-b        # worktrees under REPO/.worktrees/, branches lane/<name>
lanes.py status REPO --json               # commits ahead, dirty files, diff stat per lane
lanes.py gate   REPO [lanes...] --cmd "python3 -m pytest -q"
lanes.py merge  REPO --into integration   # serial merge, aborts on conflict
lanes.py report REPO                      # evidence JSON: heads, diffs, gate results
```

Оркестратор заново запускает проверку внутри каждой lane и закрывает карточку идентификатором коммита
и кодом возврата команды, а не самоотчётом исполнителя. «Красная»
lane не мержится; конфликт прерывает слияние и оставляет lane изолированной.

Три детали, которые проявляются, только когда два исполнителя работают одновременно, — все они изучены путём их поломки:

- Внутри lane'а `HEAD` — это вершина **lane'а**; базовая линия должна браться из основного checkout'а, иначе каждая lane будет сообщать ноль коммитов.
- Гигиена lane'ов должна настраиваться в `.git/info/exclude`, а не в `.gitignore`; иначе `new` оставит незакоммиченный файл, и каждая последующая проверка «чисто ли в дереве?» будет завершаться неудачей.
- Разбирайте статус с помощью `git diff --name-only` / `git ls-files --others`. Нарезка столбцов porcelain-вывода молча обрезает имена файлов (`app.py` → `pp.py`).

## Связанные модули

Продолжает **02** (контроль процессов — тот же принцип «судить со стороны», теперь для команд и worktree'ов) и **07** (линтер, который охраняет промпты до их выпуска; этот модуль охраняет то, что агент с ними делает). Половины про lane'ы и evidence сочетаются с собственными средствами Hermes: `delegation.worktree_isolation` и рабочими kanban lane'ами.
