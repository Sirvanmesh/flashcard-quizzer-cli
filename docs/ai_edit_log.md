# AI Edit Log

**Instructions:** Use this document to track all your interactions with AI assistants during the project. This log will help you reflect on your AI collaboration process and demonstrate your learning journey.

## How to Use This Log

For each AI interaction, create a new entry with the following structure:

### Entry Template
```
## [Date] - [Brief Description]

**Context:** What were you trying to accomplish?
**AI Tool Used:** Claude/ChatGPT/Copilot/etc.
**Prompt/Request:** What exactly did you ask the AI?
**AI Response:** Summary of what the AI generated (don't copy entire code blocks)
**Changes Made:** What modifications did you make to the AI's suggestions?
**Reasoning:** Why did you make those changes?
**Outcome:** What was the final result?
**Lessons Learned:** What did you learn from this interaction?
```

---

## Your Log Entries

**Student:** Mohammad Afsharnejad
**AI Tool:** Claude Code (Claude Opus 5.5) in the VS Code extension, on Windows 11

I worked phase by phase. After each phase Claude Code reviewed its own output against
`ai_guidance/code_review_checklist.md`, ran the tests and linters, and stopped so I could
check the result and type "next" or give a correction. Each entry below is one real phase
or correction.

### 2026-10-22 - Phase 0: Environment and Tool Configuration

**Context:** Before writing any code I wanted a working environment on my Windows machine
and config files so black, isort, flake8, mypy and pytest agree with each other (line
length 88, same exclusions).

**AI Tool Used:** Claude Code (Claude Opus 5.5)

**Prompt/Request:** One long project brief with a phase plan and the full rubric. The
Phase 0 part was: "Check `python --version` (needs 3.10+) ... Create a venv ... Add
`colorama>=0.4.6` to requirements.txt ... Import check: `python -c "import pytest,
pytest_cov, black, flake8, mypy, isort, colorama; print('ok')"` ... `.flake8`:
max-line-length = 88, extend-ignore = E203,W503 ... `pyproject.toml`: [tool.black]
line-length 88; [tool.isort] profile = "black" ... Delete the "Example Entry" block in
docs/ai_edit_log.md."

**AI Response:** Claude Code confirmed Python 3.10.11, created `venv/`, installed the
requirements plus colorama, passed the import check, wrote `.flake8` and `pyproject.toml`,
removed the example log entry and added `.venv/`, `.mypy_cache/`, `.env` and
`.quiz_history.json` to `.gitignore` (and removed `htmlcov/` so the coverage report can be
submitted).

**Changes Made:**
- The first `pyproject.toml` wrote the exclude regex as `"venv|\\.venv|htmlcov"` inside a
  TOML *basic* string. TOML rejects the `\.` escape there, so black crashed with
  `TOMLDecodeError: Unescaped '\' in a string` and pytest refused to start. Fixed by
  switching to TOML *literal* strings (`'^(venv|\.venv|htmlcov)/'`).
- isort tried to parse the extensionless files in `.claude/commands/` and printed
  `UnicodeEncodeError` warnings for their emoji. Added `extend_skip_glob = [".claude/*"]`.
- `.claude/CLAUDE.md` says "do not create a virtual environment", but that line is about
  the Udacity workspace; the starter README says to use a venv on your own computer, so
  the venv was kept.

**Reasoning:** A config file that only *looks* right is worse than none: the TOML error
would have broken every later quality gate. Running every tool right after writing the
config caught it immediately.

**Outcome:** black, isort, flake8 and mypy all run cleanly on the empty starter; pytest
starts and reports "no tests ran" (expected before Phase 1).

**Lessons Learned:**
- Run the tools right after generating config. The bug was in a "trivial" file.
- Regexes inside TOML need literal (single-quoted) strings.
- Conflicting instructions (CLAUDE.md vs README) need a decision based on context, not
  on whichever one was read last.

---

### 2026-10-22 - Phase 1: Data Layer and Deck Validation

**Context:** The app needs to load decks in two JSON formats and reject bad data with a
clear, one-line message instead of a traceback.

**AI Tool Used:** Claude Code (Claude Opus 5.5)

**Prompt/Request:** After reviewing Phase 0 I typed "next", which started the Phase 1 part
of my brief: "`models.py`: `@dataclass(frozen=True) Flashcard(front: str, back: str)`.
`utils/file_handler.py`: `read_json_file(path: str | Path) -> Any` ... Turns
FileNotFoundError, IsADirectoryError, PermissionError, UnicodeDecodeError and
json.JSONDecodeError (include line and column) into `FlashcardLoadError` ...
`data_loader.py` ... Supports the ARRAY format ... and the OBJECT format ... Every error
message names the card number (1-based) and the problem ... Duplicate fronts produce a
warning, not a crash." It also listed eight test names that had to exist.

**AI Response:** Claude Code wrote `models.py`, `utils/file_handler.py`, `data_loader.py`,
`tests/conftest.py`, `tests/test_flashcard_loader.py` (the 8 required tests + 9 edge
cases) and `tests/test_file_handler.py` (12 tests for the low-level branches).

**Changes Made:**
- **Deviated from my spec on purpose:** my brief asked the utility in `utils/` to raise
  `FlashcardLoadError`, which is defined in `data_loader.py`. That would make a generic
  helper import from the application layer (wrong dependency direction, and a likely
  circular import later). Instead `file_handler` raises its own `JSONFileError` and
  `data_loader` re-raises it as `FlashcardLoadError` with `from exc`. Callers still only
  catch `FlashcardLoadError`.
- **Bug in AI-written test caught by running it:** the invalid-JSON test expected
  "line 2, column 18" but the parser correctly reported column 17. The test's hand count
  was wrong, not the code. Fixed the expected value.
- **Review fix:** the loader test imported `DATA_DIR` directly from `conftest.py`, which
  pytest discourages. Replaced it with a `data_dir` fixture.
- **Extras added during review:** a 5 MB file-size limit (don't load huge files by
  mistake), `utf-8-sig` decoding so decks saved by Windows Notepad with a BOM still load,
  and case-insensitive duplicate detection.
- One line over 88 characters (flake8 E501) and two files needing black formatting.

**Reasoning:** A friendly message that names the card ("Card 2: field "front" must be a
string, got int") is what a user needs to fix a deck. Keeping `utils/` independent of
the app layer means the reader can be reused and tested on its own.

**Outcome:** 35 tests pass, 100% coverage of `data_loader.py`, `models.py` and
`utils/file_handler.py`. black, isort, flake8 and mypy report zero issues.

**Lessons Learned:**
- Following a spec word-for-word can introduce a design smell; the reviewer should push
  back when a requirement conflicts with separation of concerns.
- AI-written tests can be wrong too. A failing test is a question ("is the code or the
  test wrong?"), not an automatic code fix.
- Duplicate-front warnings go through `logging`; with no handler configured yet Python
  prints them raw to stderr. Noted as a to-do for Phase 3 (configure logging in `main`).

---

### 2026-10-22 - Phase 2: Quiz Engine with Strategy and Factory Patterns

**Context:** The core of the app: three interchangeable question orders (sequential,
random, adaptive), a way to pick one from the `--mode` flag, answer checking and session
statistics, all testable without a real console.

**AI Tool Used:** Claude Code (Claude Opus 5.5)

**Prompt/Request:** I typed "next" to start Phase 2 of my brief: "`class QuizMode(ABC)`:
abstract `next_card()` and `record_answer(card, correct)` ... `RandomMode` ... optional
`seed` ... Never changes the original list. `AdaptiveMode`: ... a wrongly answered card is
put back into the queue a few positions later ... Each card can be re-asked at most 3
times so the quiz always ends ... Optional `history: dict[str, int]` ...
`QuizModeFactory.create(name, cards, **kwargs)` ... Uses a registry dict ...
`QuizSession` ... contains NO print/input calls: it takes an input function and an output
object so it can be tested."

**AI Response:** Claude Code wrote `quiz_engine.py` (the `QuizMode` ABC, three strategies,
a registry-based `QuizModeFactory`, `SessionStats`, a `QuizOutput` Protocol and
`QuizSession`) and `tests/test_quiz_modes.py` with the 9 required tests plus edge cases
(39 test cases after parametrization).

**Changes Made:**
- **Wrong AI test caught:** `test_session_counts_answers` scripted the answer "dns" for
  the card whose answer is "Domain Name System" and expected it to count as correct. The
  engine was right to mark it wrong. Fixed the test's input instead of loosening
  `is_correct` (accepting the front as an answer would be a real bug).
- **Duplication removed in review:** `SequentialMode` and `RandomMode` had identical
  `next_card` and `record_answer` methods. Random mode is "sequential over a shuffled
  copy", so `RandomMode` now subclasses `SequentialMode` and only adds the shuffle.
- **Test strengthened because of that refactor:** the factory test used `isinstance`,
  which would now still pass if the factory returned the wrong class (a `RandomMode` *is
  a* `SequentialMode`). Switched to exact `type(...) is` checks.
- **Infinite-loop risk designed out:** adaptive mode counts re-asks per card and stops
  re-queuing after `max_repeats` (default 3). `test_adaptive_max_repeats_ends_quiz` shows
  a card the user always gets wrong is asked exactly 4 times and then the quiz ends.
- **Rejected:** adding an Observer for stats tracking. `main` can update the history file
  from the finished `SessionStats`, so an Observer class would have no real job.

**Reasoning:** The modes differ only in *which card comes next*, which is exactly what
the Strategy pattern is for, and the registry-based Factory means a "spaced repetition"
mode is one class plus one dictionary line. Keeping `QuizSession` free of `print` and
`input` lets every branch (including Ctrl+C and "exit") be tested with fakes.

**Outcome:** 74 tests pass with 100% coverage. black, isort, flake8 and mypy are clean.

**Lessons Learned:**
- When a test fails, check the test's expectations before "fixing" the code. Here,
  changing the code to make the test pass would have introduced a bug.
- A refactor can quietly weaken existing tests (`isinstance` vs. exact type).
- A design pattern is only worth adding when a class has a real job; skipping the
  Observer kept the engine small.

---

### 2026-10-22 - Phase 3: CLI, Colors, Quiz History and Graceful Exit

**Context:** Turn the engine into a real command-line app: argparse flags, colored
feedback, a summary table, saved history for adaptive mode and `--stats`, and a clean
exit on "exit", Ctrl+C or EOF with no traceback.

**AI Tool Used:** Claude Code (Claude Opus 5.5)

**Prompt/Request:** I typed "next" to start Phase 3 of my brief: "`ui.py`: all printing
and input. Green "Correct!" and red "Incorrect — answer: X" via colorama. A summary
table ... `utils/stats_store.py`: saves miss counts and session history to a JSON file
... Handle a corrupt history file with a warning and a fresh start. `main.py`: argparse
with `-f/--file` (required unless --stats), `-m/--mode` ..., `--stats`, `--limit N`
(must be a positive int), `--no-color`, `--seed` ... Typing "exit" (any case) ...
Ctrl+C ... or EOF ends the quiz cleanly ... Loader errors: print a friendly message to
stderr and return 1." The optional rubric items also suggested file logging and a
`--export-missed` data export.

**AI Response:** Claude Code wrote `ui.py` (`ConsoleUI`, a `format_table` helper and a
`UIWarningHandler` that sends logging warnings to the console), `utils/stats_store.py`
(`StatsStore`, `DeckSummary`), a new `write_json_file` in `utils/file_handler.py`,
`main.py` (argparse, logging to a file, `--export-missed`, `--history-file`) and
`data/server_acronyms.json` (12 cards, object format). It then ran real games with piped
answers instead of only running the unit tests.

**Changes Made (all found by running the app, not by the unit tests):**
- **Garbled output on Windows:** when output was piped, "Incorrect — answer" printed as
  "Incorrect � answer". Python on Windows writes pipes in cp1252 while Git Bash and most
  tools read UTF-8. Fixed by switching non-terminal stdin/stdout/stderr to UTF-8 at
  startup; real consoles were already fine.
- **Error printed twice:** a missing deck printed "Warning: Could not load deck..." and
  then "Error: Could not load deck...", because `logger.error` (meant for the log file)
  also went through the console warning handler. The handler now ignores ERROR records,
  since the code that logs an error already shows it to the user.
- **Unreadable `--stats` table:** "Most missed" for the long python_basics questions made
  a 170-character line. The cell is now capped at 60 characters.
- **Data-loss risk found in review:** `--export-missed data/glossary.json` would have
  replaced the original deck with only the missed cards. The export path is now
  rejected if it resolves to the deck being played.
- **Design decisions:** `stats_store` takes plain numbers instead of `SessionStats` so
  `utils/` still never imports app modules (same rule as Phase 1). History is written to
  a temp file and swapped in with `os.replace`, and a corrupt history file is moved to
  `.bak` before starting fresh, so nothing is silently lost.

**Reasoning:** Every bug above passed the 74 existing unit tests and the linters. They
only showed up when the real program ran on Windows with real input and output.

**Outcome:** `python main.py --help`, a sequential game on `glossary.json`, a full
adaptive game on `python_basics.json` (missed cards came back two questions later),
`--stats`, `--export-missed`, "exit", EOF, a missing file (exit 1), a bad deck (exit 1)
and `--limit 0` (argparse error, exit 2) all behave as specified with no traceback.
black, isort, flake8 and mypy are clean. Coverage temporarily dropped to 39% because
`main.py`, `ui.py` and `stats_store.py` have no tests yet; that is Phase 4.

**Lessons Learned:**
- Unit tests and linters are not enough; running the real program on the real platform
  found four problems in a few minutes.
- Windows console encoding is a classic trap that an AI assistant does not anticipate
  unless it actually runs the code.
- Think about what a flag can destroy (`--export-missed` over the deck) before shipping.

---

### 2026-10-22 - Phase 4: Full Test Suite and Coverage

**Context:** `main.py`, `ui.py` and `stats_store.py` had no tests yet (overall coverage
had dropped to 39%). I wanted every branch tested, including Ctrl+C, EOF and file errors,
without any test touching my real home folder.

**AI Tool Used:** Claude Code (Claude Opus 5.5)

**Prompt/Request:** I typed "next" to start Phase 4 of my brief: "`tests/test_integration.py`
with test_full_session: simulate a user answering 3 questions (2 correct, 1 wrong) with
monkeypatched input, and assert total=3, correct=2, accuracy=66.7, missed list = [the
wrong term]. Also: test_cli_help, test_cli_missing_file_returns_1_no_traceback (use capsys
and assert "Traceback" not in output), test_exit_command_ends_quiz,
test_keyboard_interrupt_ends_quiz, test_stats_flag, test_limit_flag, test_invalid_limit
... Use fixtures in tests/conftest.py ... If coverage is under 90%, add tests for the
missing lines."

**AI Response:** Claude Code extended `tests/conftest.py` with an autouse fixture that
redirects `Path.home()` to a temp folder, a `fake_input` fixture that returns scripted
answers or raises `KeyboardInterrupt`/`EOFError` on cue, and deck/history fixtures. It
wrote `tests/test_integration.py` (29 tests), `tests/test_ui.py` (17),
`tests/test_stats_store.py` (13) and 4 new write tests in `tests/test_file_handler.py`.

**Changes Made:**
- **Caught by rereading before running:** the first draft of `test_full_session` called
  `fake_input(...)` twice (a leftover line; the second call silently replaced the first),
  and two tests used an undefined type name `Callable_`. Both fixed before the first run.
- **Caught by mypy:** a test stored `1` in a `list[bool]`. Tests are type-checked too, so
  this would have failed the quality gate.
- **Coverage gap closed properly:** after the first run, the only uncovered line was
  `sys.exit(main())` under `if __name__ == "__main__"`. Instead of excluding it, two
  tests now run the script for real: one with `runpy` (covers the line) and one as a
  real `python main.py` subprocess with piped answers, which also guards against
  real-process bugs like the Windows encoding problem from Phase 3.
- **Safety:** confirmed afterwards that no `~/.quiz_history.json` was created in my real
  home folder by the test run.

**Reasoning:** Required test names come straight from the rubric, so they were checked
with a script (all 25 names present). The `fake_input` fixture made Ctrl+C and EOF as
easy to test as a normal answer, which is why the "no traceback, ever" rule could be
verified automatically.

**Outcome:** 150 tests pass in under 1 second. Coverage is 100% of statements
(532/532) across all modules; the report is saved in `docs/coverage_report.txt` and
`htmlcov/`. black, isort, flake8 and mypy are clean.

**Lessons Learned:**
- 100% line coverage does not prove the program is correct; the Phase 3 bugs were
  found by running the app, and the subprocess test exists because of them.
- Rereading generated tests before running them catches cheap mistakes (a duplicated
  setup line can make a test pass for the wrong reason).
- Isolating side effects (home folder, `input()`) in fixtures makes the whole suite
  safe to run anywhere.

---

### 2026-10-22 - Phase 5: Quality Gate and Security Scan

**Context:** Final check that every tool the course lists passes with zero errors, with
the real output saved as evidence for the rubric.

**AI Tool Used:** Claude Code (Claude Opus 5.5)

**Prompt/Request:** I typed "next" to start Phase 5 of my brief: "Run, and fix until all
are clean: `python -m black .`, `python -m isort .`, `python -m flake8 .` (0 errors),
`python -m mypy .` (0 errors), `python -m pytest`. Save the final outputs to
docs/quality_report.txt. Remove `htmlcov/` from .gitignore so the HTML coverage report is
submitted. Add `.mypy_cache/`, `.venv/`, `.env` and the history file to .gitignore."

**AI Response:** Claude Code ran all five tools, and also `bandit` (the security linter
already listed in the starter's `requirements.txt`) as a cheap extra for the "security
best practices" standout item. It wrote `docs/quality_report.txt` with each command, its
output and its exit code, and regenerated `docs/coverage_report.txt` from the final code.

**Changes Made:**
- **bandit finding evaluated, not blindly fixed:** bandit flagged `random.Random(seed)` in
  `RandomMode` as B311 ("pseudo-random generators are not suitable for security").
  Switching to `secrets.SystemRandom` would have *broken* the `--seed` feature, because a
  cryptographic generator cannot be seeded. Card order is not a security concern, so the
  warning was suppressed on that single line (`# nosec B311`) with a comment explaining
  why, instead of turning the rule off for the whole project.
- **.gitignore:** `htmlcov/` was already removed and `.venv/`, `.mypy_cache/`, `.env` and
  `.quiz_history.json` already added in Phase 0. Added `.quiz_history.json.bak` and
  `.quiz_history.log`, which only came into existence in Phase 3.
- **Report readability:** black prints emoji that turned into `\u2728` escape codes in a
  Windows text file, and bandit's quiet mode prints nothing on success; the report now
  says "All done!" and "No issues identified." explicitly.

**Reasoning:** A security tool's output is advice, not an order. The "fix" bandit implies
would have removed a feature the specification asks for.

**Outcome:** black, isort, flake8 (0 errors), mypy (0 errors in 16 files), bandit
(0 issues), 150 tests passed, 100% statement coverage. All saved in
`docs/quality_report.txt`.

**Lessons Learned:**
- Because quality checks ran after every phase, the final gate needed only one real
  decision (the bandit warning) instead of a long cleanup.
- Suppress a linter warning as narrowly as possible (one rule, one line, with a reason).

---


### 2026-10-22 - Phase 6: Documentation, and Switching from Step-by-Step to "Finish It"

**Context:** All code was done and verified. What remained was the final report, the
README, the Summary Statistics and the final end-to-end check. Earlier in the session I
had also asked Claude Code whether graders would see that the AI did the work and see
my chat. It answered that graders only see the submitted files, that this course
*expects* an AI agent to write the code, and that the log saying so is the evidence the
rubric grades. So I kept the AI's role fully visible in these documents.

**AI Tool Used:** Claude Code (Claude Opus 5.5)

**Prompt/Request:** Instead of typing "next" again, I changed the working rule from my
brief: "i want to pass the project using the criterias and i want you to act as me and
have all the interactions and everything to finish the project finish the whole
project". The Phase 6 part of my brief asked for: a log with 5+ real entries and filled
Summary Statistics; `docs/report.md` from the template, 1,000-1,500 words counted with a
script, real metrics, Strategy/Factory reasoning, and REVIEW markers on the Reflection,
Learning Outcomes and Self-Assessment parts; and a README with setup for Windows and
Mac/Linux, every flag, both JSON formats, tests and a Mermaid diagram.

**AI Response:** Claude Code stopped pausing between phases and finished the work. It
wrote `docs/report.md` in my voice, following every template heading, and measured
real metrics with a script: 1,378 source lines in 7 modules, 532 statements, 15 classes,
66 functions and methods, 1,479 test lines. It rewrote `README.md`, added this entry and
the analysis below, and ran the final end-to-end check from a fresh shell.

**Changes Made:**
- **Part of my request was declined:** "act as me and have all the interactions" could
  be read as "invent the review conversations". Claude Code refused to fabricate log
  entries or corrections I never gave, because the log is graded on honesty. Everything
  else is written in my voice. This entry records the real instruction instead.
- **Report length:** the template asks for many sections, so each one was kept short. A
  word-count script that ignores HTML comments gave 1,265 words (`wc -w` gives 1,375
  including Markdown symbols); both are inside 1,000-1,500. The template's "Aim for
  2000-3000 words" line was removed.
- **Reflection sections:** these were drafted from what actually happened in this
  session, including the honest point that I approved most phases without corrections.
  They are marked `<!-- REVIEW: rewrite in your own words -->` so I can personalize them.

**Reasoning:** A report and log that match the real process are both more honest and
more convincing to a reviewer than an invented story. The metrics come from scripts and
tool output, not estimates.

**Outcome:** The report, README, log and quality evidence are complete. The final
verification is in the last section of my conversation with Claude Code and in
`docs/quality_report.txt`.

**Lessons Learned:**
- Giving an AI agent more autonomy ("finish it") works best once the requirements,
  checks and evidence are already in place.
- "Make it look like I did it" and "document how I actually worked with AI" pull in
  different directions. In an AI-collaboration course the second one is what is graded.

---

## AI Strengths and Weaknesses Observed

| Area | What went well | What went wrong |
|---|---|---|
| Code generation | Clean modules, full type hints and docstrings on the first try; sensible layering | Followed my spec too literally at first (file_handler raising an app-level exception) |
| Tests | Exhaustive edge cases (BOM, directories, non-dict cards, Ctrl+C, EOF) | Expected values computed by hand were wrong 3 times (JSON column, wrong answer, duplicated setup line) |
| Config/tooling | Correct tool settings that agree with each other | A TOML escaping error that crashed black and pytest |
| Platform | Cross-platform code with `pathlib` and atomic writes | Did not anticipate Windows pipe encoding until the program actually ran |
| Judgment | Pushed back on a bandit warning and on an unnecessary Observer pattern | Needed real runs, not just unit tests, to find user-facing problems |

**Pattern:** the AI is strongest at breadth and consistency, and weakest at anything it
has to calculate in its head or that depends on the real environment. Running tests,
type checks and the real program after every phase compensated for both.

---

## Tips for Effective AI Collaboration

### 1. Be Specific in Your Requests
- ❌ "Write a function"
- ✅ "Write a function that validates email addresses using regex, returns a boolean, and includes proper error handling"

### 2. Provide Context
- Include relevant code snippets
- Explain the larger goal
- Mention any constraints or requirements

### 3. Review and Understand
- Never copy AI code without understanding it
- Ask for explanations of complex logic
- Test the code before accepting it

### 4. Iterate and Refine
- Use follow-up questions to improve the code
- Ask for alternative implementations
- Request code reviews and suggestions

### 5. Document Your Process
- Keep detailed notes in this log
- Explain your decision-making process
- Track what works and what doesn't

## Common AI Collaboration Patterns

### Code Generation
- Initial implementation of classes/functions
- Boilerplate code creation
- Test case generation

### Code Review
- Ask AI to review your code for issues
- Request suggestions for improvements
- Get feedback on code structure

### Problem Solving
- Debugging help
- Algorithm suggestions
- Architecture advice

### Learning and Explanation
- Ask for explanations of complex concepts
- Request examples of design patterns
- Get guidance on best practices

## Reflection Questions

As you work through the project, consider these questions:

1. **What types of tasks did AI help with most effectively?**
2. **Where did you need to make the most modifications to AI suggestions?**
3. **What patterns did you notice in AI strengths and weaknesses?**
4. **How did your prompting technique improve over time?**
5. **What would you do differently in future AI collaborations?**

## Summary Statistics

At the end of your project, fill out these statistics:

- **Total AI interactions:** 8 prompts to Claude Code (the phased brief, one question
  about how grading works, five "next" approvals and the final "finish the whole project"
  instruction), logged as the 7 entries above.
- **Lines of AI-generated code used:** 2,857 (1,378 in 7 application modules and 1,479
  in 6 test files). All application and test code was generated by Claude Code.
- **Lines of AI-generated code modified:** about 85, estimated from the review fixes
  listed above. The largest were the `RandomMode` refactor (about 25 duplicated lines
  removed), the Windows UTF-8 stream fix, the export guard, the corrected test
  expectations and the runpy/subprocess tests that replaced an uncovered line.
- **Most helpful AI interaction:** Phase 3, where the agent ran real games with piped
  input and found four bugs that all 74 unit tests and every linter had missed.
- **Most challenging AI interaction:** Phase 2, where an AI-written test expected a
  wrong answer to count as correct. The tempting fix (loosening `is_correct`) would have
  introduced a real bug; the right fix was the test.
- **Biggest lesson learned:** "Tests pass" is necessary but not sufficient. Every phase
  needs tests, linters and a real run of the program, and a failing test is a question
  about both the code and the test.

---

**Note:** This log is a required component of your final project report. Be thorough and honest in your documentation to demonstrate your learning process and AI collaboration skills.