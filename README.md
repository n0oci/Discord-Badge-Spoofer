<div align="center">

# Discord Badge Spoofer 🌐

*Inflates playtime and games-played badges with a sleek, live terminal interface.*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-informational.svg)]()
[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB.svg)](https://www.python.org/)

</div>

---

### *Working on the first releases!*

---

## ⚠️ Disclaimer

This uses internal and undocumented Discord APIs. It may break after updates. Use at your own risk. This is for educational and personal use only. I am not responsible for any account actions taken against you.

## ✨ Features

- [x] **Live Terminal UI:** A dark-themed console panel with progress bars, tables, and a clean summary — no spam, no noise.
- [x] **Native Audio:** Plays a short three-note chime when the run finishes, right on Windows.
- [x] **Batch Engine:** Sends `launch_game` and `running_game_heartbeat` events to Discord's `/science` endpoint in configurable batches.
- [x] **Persistent State:** Remembers your token, cookie, and claimed games across runs — no re-pasting every time.
- [x] **Zero External Dependencies:** Pure Python standard library. No `pip install`, no binaries, no token pasted into a web form.

## 🚀 How to Use

1. Make sure **Python 3.9+** is installed on Windows.
2. Grab your **account token** and your **cookie**.
3. Run the script or execute the .exe if u want.

    ```bash
    python tool.py
    ```

4. Paste your token on first run, then your cookie.
5. Pick **1 · claim games**, choose how many games and how many hours per game.
6. Wait for the progress bar. The chime means it's done.
7. Give Discord **24–48 hours** to sync the badges.

> **Note:** The badges do not update instantly. Check the **Badge Directory** in your profile after a day or two.

## 🛠️ Supported Badges

| Badge | How it's inflated |
| :--- | :--- |
| **Game Time** | Sends heartbeat events with a forged `duration_tracked_ms`. |
| **Game Variety** | Sends `launch_game` events for distinct game IDs (fingerprint recommended for best results). |

## ⚙️ How It Works

The script builds the same event payloads the real Discord client posts to `/api/v9/science` when you play a game. It wraps them in the same `x-super-properties` header, uses fresh `heartbeat_session_id` and `launch_signature` UUIDs per run, and posts them in batches. **Your Discord token stays on your machine — it is never sent anywhere except Discord's own API.**

Optionally, it can generate a real `executable_fingerprint` from a game's PE metadata and your machine GUID, the same way the desktop client does. That fingerprint helps the **Game Variety** badge, but is not required for **Game Time**.

## 📜 License

Distributed under the MIT License. Feel free to use, modify, and share.
