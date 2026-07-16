# Purrductivity 🐱

A cat-themed macOS menu-bar productivity app. Cats live in your menu bar, remind you about your tasks, and nag you (adorably) when you snooze them.

## Features

- Recurring reminders: daily, weekly, monthly, quarterly, or one-time
- Snooze with escalating cat popup reminders
- Weekly and quarterly goal tracking with on-track / behind status
- EOS-style "rock report" export
- Menu-bar badge showing what's due

## Requirements

- **macOS only** (uses the native menu bar via `rumps`/`pyobjc`)
- Python 3.13+

## Install & Run

```bash
pip install -r requirements.txt
python main.py
```

## Architecture

Two-process design: `rumps` owns the main thread of the main process (a macOS requirement for menu-bar apps), while the Tkinter UI runs in a spawned child process, communicating over `multiprocessing.Queue`. Scheduling is handled by APScheduler; tasks persist in TinyDB (JSON) at `data/tasks.db`.

## Tests

```bash
pytest
```

## License

MIT — see [LICENSE](LICENSE).
