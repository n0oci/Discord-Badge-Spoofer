#!/usr/bin/env python3
"""
ocean's tool.

posts launch_game and running_game_heartbeat events to /api/v9/science.
duration_tracked_ms isn't validated, so any number goes through.

this breaks discord tos. your account, your problem :3.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterator, Sequence

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

# paths - locally relative for portability
ROOT = Path(__file__).resolve().parent
GAMES_FILE = ROOT / "games.json"
STATE_FILE = ROOT / "science_state.json"

ME_URL = "https://discord.com/api/v9/users/@me?with_analytics_token=true"
SCIENCE_URL = "https://discord.com/api/v9/science"
PROPERTIES_URL = "https://cordapi.dolfi.es/api/v2/properties/windows"
GAMES_CDN_URL = "https://cdn.discordapp.com/detectables/games.json"

BATCH_SIZE = 50
BATCH_DELAY = 1
AUTH_MAX_AGE = 12 * 3600

CLIENT_VERSION = "1.0.9253"
CLIENT_BUILD_NUMBER = 594031
NATIVE_BUILD_NUMBER = 88414
OS_VERSION = "10.0.26200"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) discord/1.0.9253 Chrome/148.0.7778.280 "
    "Electron/42.7.1 Safari/537.36"
)


# ──────────────────────────────────────────────
# console
# ──────────────────────────────────────────────

class C:
    RESET = "\x1b[0m"
    WHITE = "\x1b[97m"
    GREY = "\x1b[90m"
    DARK = "\x1b[38;5;236m"
    GREEN = "\x1b[32m"
    YELLOW = "\x1b[33m"
    RED = "\x1b[31m"
    RULE = "═" * 60


def _enable_ansi() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        m = ctypes.c_uint32()
        if k.GetConsoleMode(h, ctypes.byref(m)):
            k.SetConsoleMode(h, m.value | 0x0004)
    except Exception:
        pass


def clear() -> None:
    print("\x1b[2J\x1b[3J\x1b[H", end="")


def log_sys(msg: str) -> None:
    print(f"{C.GREY}[#]{C.RESET} {msg}")


def log_warn(msg: str) -> None:
    print(f"{C.YELLOW}[!]{C.RESET} {msg}")


def log_err(msg: str) -> None:
    print(f"{C.RED}[-]{C.RESET} {msg}")


def log_ok(msg: str) -> None:
    print(f"{C.GREEN}[+]{C.RESET} {msg}")


def rule() -> None:
    print(f"{C.GREY}{C.RULE}{C.RESET}")


def header(sub: str) -> None:
    print()
    rule()
    print(f" {C.WHITE}{sub}{C.RESET}")
    rule()
    print()


def footer() -> None:
    print()
    rule()
    print(f" {C.DARK}ocean's tool{C.RESET} {C.GREY}· discord science spoofer{C.RESET}")
    rule()
    print()


def bar(current: int, total: int, length: int = 30) -> str:
    pct = min(1.0, current / total if total else 0)
    filled = round(length * pct)
    body = f"{C.WHITE}{'█' * filled}{C.DARK}{'░' * (length - filled)}{C.RESET}"
    return f"[{body}] {round(pct * 100):>3}%"


def table(rows: dict[str, str]) -> None:
    width = max(len(k) for k in rows) + 2
    for k, v in rows.items():
        print(f" {C.GREY}{k:<{width}}{C.RESET}{C.WHITE}{v}{C.RESET}")


def done_sound() -> None:
    if not HAS_WINSOUND:
        return
    try:
        winsound.Beep(523, 120)
        winsound.Beep(659, 120)
        winsound.Beep(784, 350)
    except Exception:
        pass


# ──────────────────────────────────────────────
# state
# ──────────────────────────────────────────────

@dataclass
class State:
    token: str = ""
    cookie: str = ""
    analytics_token: str = ""
    fetched_at: int = 0
    used_games: list[str] = None
    total_games_claimed: int = 0
    total_hours_claimed: float = 0.0

    def __post_init__(self) -> None:
        if self.used_games is None:
            self.used_games = []

    @classmethod
    def load(cls) -> "State":
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                state = cls(**{k: data.get(k, v) for k, v in cls().__dict__.items() if k != "used_games"})
                state.used_games = data.get("used_games", [])
                return state
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        except OSError:
            fallback = Path(os.getenv("TEMP", ".")) / "science_state.json"
            try:
                fallback.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
                log_warn(f"state saved to fallback: {fallback}")
            except OSError:
                pass

    @property
    def is_stale(self) -> bool:
        return not self.analytics_token or (time.time() - self.fetched_at) > AUTH_MAX_AGE

    @property
    def has_cookie(self) -> bool:
        return bool(self.cookie.strip())

    @property
    def has_token(self) -> bool:
        return bool(self.token.strip())


# ──────────────────────────────────────────────
# super props + analytics token
# ──────────────────────────────────────────────

def local_props() -> dict:
    return {
        "os": "Windows",
        "browser": "Discord Client",
        "release_channel": "stable",
        "client_version": CLIENT_VERSION,
        "os_version": OS_VERSION,
        "os_arch": "x64",
        "app_arch": "x64",
        "system_locale": "en-GB",
        "has_client_mods": False,
        "browser_user_agent": USER_AGENT,
        "browser_version": "42.7.1",
        "os_sdk_version": "26200",
        "client_build_number": CLIENT_BUILD_NUMBER,
        "native_build_number": NATIVE_BUILD_NUMBER,
        "client_event_source": None,
        "client_app_state": "focused",
    }


def build_super_props(launch_signature: str, heartbeat_session: str) -> str:
    try:
        req = urllib.request.Request(
            PROPERTIES_URL, method="POST", data=b"{}",
            headers={"content-type": "application/json", "user-agent": USER_AGENT},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            props = json.loads(response.read().decode("utf-8"))["properties"]
    except Exception:
        props = local_props()
    props["client_launch_id"] = str(uuid.uuid4())
    props["launch_signature"] = launch_signature
    props["client_heartbeat_session_id"] = heartbeat_session
    raw = json.dumps(props, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _read_analytics_token(auth_token: str, super_props: str) -> str:
    req = urllib.request.Request(ME_URL, headers={
        "authorization": auth_token,
        "user-agent": USER_AGENT,
        "x-super-properties": super_props,
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"token rejected ({exc.code})") from exc
    token = data.get("analytics_token")
    if not token:
        raise RuntimeError("no analytics_token in response")
    return token


def ensure_token(state: State, super_props: str) -> None:
    if not state.is_stale:
        return
    state.analytics_token = _read_analytics_token(state.token, super_props)
    state.fetched_at = int(time.time())
    state.save()


@dataclass(frozen=True)
class Session:
    heartbeat_session: str
    launch_signature: str
    super_props: str

    @classmethod
    def new(cls) -> "Session":
        hb = str(uuid.uuid4())
        sig = str(uuid.uuid4())
        return cls(hb, sig, build_super_props(sig, hb))


# ──────────────────────────────────────────────
# games
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class Game:
    id: str
    name: str
    exe: str


def _win_exe(game: dict) -> str:
    for entry in game.get("executables", []):
        if entry.get("os") == "win32" and entry.get("name"):
            return entry["name"]
    return "game.exe"


def _download_games() -> str:
    request = urllib.request.Request(GAMES_CDN_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")
    try:
        GAMES_FILE.parent.mkdir(parents=True, exist_ok=True)
        GAMES_FILE.write_text(raw, encoding="utf-8")
    except OSError:
        pass
    return raw


def _parse_games(raw: str) -> list[Game]:
    data = json.loads(raw)
    games: list[Game] = []
    seen: set[str] = set()
    for entry in data:
        gid = str(entry.get("id", ""))
        if not gid.isdigit() or gid in seen:
            continue
        if not any(e.get("os") == "win32" and e.get("name") for e in entry.get("executables", [])):
            continue
        seen.add(gid)
        games.append(Game(gid, entry.get("name", "Unknown"), _win_exe(entry)))
    return games


def load_games() -> list[Game]:
    raw = ""
    if GAMES_FILE.exists():
        raw = GAMES_FILE.read_text(encoding="utf-8").strip()
    if raw:
        try:
            games = _parse_games(raw)
            if games:
                return games
        except (json.JSONDecodeError, ValueError):
            pass
    try:
        return _parse_games(_download_games())
    except Exception:
        return []


# ──────────────────────────────────────────────
# science client
# ──────────────────────────────────────────────

class ScienceClient:
    def __init__(self, state: State, session: Session) -> None:
        self.state = state
        self.session = session
        self._seq = 0

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def build_launch(self, game: Game) -> dict:
        now = int(time.time() * 1000)
        props = {
            "client_track_timestamp": now,
            "client_heartbeat_session_id": self.session.heartbeat_session,
            "event_sequence_number": self._next_seq(),
            "game": game.name,
            "game_id": game.id,
            "verified": True,
            "elevated": False,
            "is_launcher": False,
            "game_platform": "desktop",
            "detection_method": "verified_game",
            "is_overlay_enabled": False,
            "is_overlay_game_enabled": True,
            "is_overlay_game_source": "OOP_DEFAULT_DATABASE",
            "fullscreen_type": "UNKNOWN",
            "hardware_display_count": 1,
            "overlay_method": "Disabled",
            "activity_status_enabled": True,
            "activity_status_shared_guilds": [],
            "current_user_status": "online",
            "game_detection_enabled": True,
            "executable_path": game.exe,
            "voice_channel_id": None,
            "voice_channel_type": None,
            "voice_channel_bitrate": None,
            "voice_channel_guild_id": None,
            "hidden_by_distributor": False,
            "game_metadata": None,
            "client_performance_cpu": None,
            "client_performance_memory": None,
            "cpu_core_count": None,
            "accessibility_features": 0,
            "rendered_locale": "en-GB",
            "launch_signature": self.session.launch_signature,
            "client_rtc_state": None,
            "client_app_state": "focused",
            "client_send_timestamp": now,
        }
        return {"type": "launch_game", "properties": props}

    def build_heartbeat(self, game: Game, duration_ms: int, session_id: str,
                        initial: bool, final: bool, ts: int | None = None) -> dict:
        ts = int(time.time() * 1000) if ts is None else ts
        return {
            "type": "running_game_heartbeat",
            "properties": {
                "client_track_timestamp": ts,
                "client_heartbeat_session_id": self.session.heartbeat_session,
                "event_sequence_number": self._next_seq(),
                "game_id": game.id,
                "game_name": game.name,
                "game_metadata": None,
                "game_executable": game.exe,
                "game_detection_enabled": True,
                "initial_heartbeat": initial,
                "final_heartbeat": final,
                "game_session_id": session_id,
                "duration_tracked_ms": duration_ms,
                "rtc_connection_id": None,
                "media_session_id": None,
                "launch_signature": self.session.launch_signature,
                "client_app_state": "focused",
                "client_send_timestamp": ts,
            },
        }

    def build_session(self, game: Game, duration_ms: int) -> list[dict]:
        sid = str(uuid.uuid4())
        now = int(time.time() * 1000)
        start = now - duration_ms
        if start < 0:
            start = now
        return [
            self.build_heartbeat(game, 0, sid, initial=True, final=False, ts=start),
            self.build_launch(game),
            self.build_heartbeat(game, duration_ms, sid, initial=False, final=True, ts=now),
        ]

    def post(self, events: Sequence[dict]) -> int:
        payload = {"token": self.state.analytics_token, "events": list(events)}
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "accept": "*/*",
            "accept-language": "en-GB",
            "authorization": self.state.token,
            "content-type": "application/json",
            "cookie": self.state.cookie,
            "origin": "https://discord.com",
            "referer": "https://discord.com/channels/@me",
            "user-agent": USER_AGENT,
            "x-debug-options": "bugReporterEnabled",
            "x-discord-locale": "en-GB",
            "x-discord-timezone": "Europe/Oslo",
            "x-super-properties": self.session.super_props,
        }
        request = urllib.request.Request(SCIENCE_URL, data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            return exc.code
        except Exception:
            return 0


def _chunked(items: Sequence[Game], size: int) -> Iterator[Sequence[Game]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


class Spoofer:
    def __init__(self, client: ScienceClient) -> None:
        self.client = client

    def run(self, games: Sequence[Game], build_events, hours: float) -> int:
        total = len(games)
        ok = 0
        req_no = 0
        for req_no, chunk in enumerate(_chunked(games, BATCH_SIZE), start=1):
            events = []
            for g in chunk:
                events.extend(build_events(g))
            status = self.client.post(events)

            clear()
            header("progress")
            table({
                "batch": f"{req_no}",
                "games": f"{ok}/{total}",
                "hours": f"{ok * hours:,.0f}h",
            })
            print()
            print(f" {C.GREY}▶{C.RESET} {bar(ok, total)}")
            print()

            if status == 204:
                ok += len(chunk)
                log_ok(f"batch {req_no} accepted · {ok}/{total}")
            elif status in (401, 403):
                log_err(f"batch {req_no} rejected [{status}] · refresh auth")
                return ok
            else:
                log_warn(f"batch {req_no} status {status}")

            time.sleep(BATCH_DELAY)

        clear()
        header("done")
        table({
            "games claimed": f"{ok}",
            "hours claimed": f"{ok * hours:,.0f}h",
            "batches": f"{req_no}",
        })
        print()
        log_ok(f"complete · {ok}/{total} games")
        footer()
        done_sound()
        return ok


# ──────────────────────────────────────────────
# app
# ──────────────────────────────────────────────

class App:
    def __init__(self) -> None:
        self.state = State.load()
        self.session: Session | None = None
        self.client: ScienceClient | None = None
        self.games: list[Game] = []

    def _new_session(self) -> None:
        self.session = Session.new()
        self.client = ScienceClient(self.state, self.session)

    def _prompt_token(self) -> None:
        log_sys("paste your discord account token")
        entered = input(f"  {C.GREY}token:{C.RESET} ").strip()
        if entered:
            self.state.token = entered
            self.state.save()
            log_ok("token saved")

    def _prompt_cookie(self) -> None:
        log_sys("paste your cf_clearance cookie header")
        entered = input(f"  {C.GREY}cookie:{C.RESET} ").strip()
        if entered:
            self.state.cookie = entered
            self.state.save()
            log_ok("cookie saved")

    def _refresh(self) -> None:
        log_sys("paste a fresh cookie header (empty to keep)")
        entered = input(f"  {C.GREY}cookie:{C.RESET} ").strip()
        if entered:
            self.state.cookie = entered
            log_ok("cookie updated")
        log_sys("refreshing analytics token...")
        try:
            self.state.fetched_at = 0
            ensure_token(self.state, self.session.super_props)
        except Exception as exc:
            log_err(str(exc))
            return
        self._new_session()
        log_ok("auth refreshed")

    def _require_ready(self) -> bool:
        if not self.state.has_cookie:
            log_err("cookie not set · option 2 first")
            return False
        if self.state.is_stale:
            try:
                ensure_token(self.state, self.session.super_props)
            except Exception as exc:
                log_err(str(exc))
                return False
            self._new_session()
        return bool(self.state.analytics_token)

    def claim_games(self) -> None:
        if not self._require_ready():
            return
        clear()
        header("claim")
        table({"games available": f"{len(self.games)}"})
        print()

        raw = input(f"  {C.GREY}how many games? [all]:{C.RESET} ").strip()
        try:
            count = int(raw) if raw else len(self.games)
        except ValueError:
            log_err("invalid count")
            return
        count = min(count, len(self.games))

        raw = input(f"  {C.GREY}hours per game? [1]:{C.RESET} ").strip()
        try:
            hours = float(raw) if raw else 1.0
        except ValueError:
            log_err("invalid hours")
            return

        selected = self._select_games(count)
        if not selected:
            log_err("none selected")
            return

        duration_ms = int(hours * 3600 * 1000)
        ok = Spoofer(self.client).run(
            selected,
            lambda g: self.client.build_session(g, duration_ms),
            hours,
        )
        self.state.total_games_claimed += ok
        self.state.total_hours_claimed += ok * hours
        self.state.save()
        input(f"\n  {C.GREY}press enter{C.RESET} ")

    def _select_games(self, count: int) -> list[Game]:
        avail = {g.id for g in self.games}
        unused = [g.id for g in self.games if g.id not in self.state.used_games]
        used = [gid for gid in self.state.used_games if gid in avail]

        if len(unused) >= count:
            chosen = unused[:count]
        else:
            chosen = unused
            if used:
                remain = count - len(chosen)
                rotated = used[remain:] + used[:remain]
                chosen.extend(rotated[:remain])

        self.state.used_games = [g for g in self.state.used_games if g not in chosen] + chosen
        id_map = {g.id: g for g in self.games}
        return [id_map[g] for g in chosen if g in id_map]

    def menu(self) -> None:
        while True:
            clear()
            header("discord science spoofer")
            table({
                "games loaded": f"{len(self.games)}",
                "games claimed": f"{self.state.total_games_claimed}",
                "hours claimed": f"{self.state.total_hours_claimed:,.0f}h",
            })
            print()
            print(f" {C.GREY}1{C.RESET} · claim games")
            print(f" {C.GREY}2{C.RESET} · refresh auth")
            print(f" {C.GREY}3{C.RESET} · exit")
            print()
            footer()
            choice = input(f"  {C.GREY}›{C.RESET} ").strip()
            if choice == "1":
                self.claim_games()
            elif choice == "2":
                self._refresh()
                input(f"\n  {C.GREY}press enter{C.RESET} ")
            elif choice in ("3", ""):
                break

    def start(self) -> None:
        _enable_ansi()
        clear()
        header("boot")

        log_sys("loading state")
        if not self.state.has_token:
            self._prompt_token()
        else:
            log_ok("token loaded")
        if not self.state.has_token:
            log_err("token required")
            return

        if not self.state.has_cookie:
            self._prompt_cookie()
        else:
            log_ok("cookie loaded")
        if not self.state.has_cookie:
            log_err("cookie required")
            return

        log_sys("loading games")
        self.games = load_games()
        if not self.games:
            log_err("could not load games list")
            return
        log_ok(f"{len(self.games)} games loaded")

        log_sys("validating auth")
        self._new_session()
        try:
            ensure_token(self.state, self.session.super_props)
        except Exception as exc:
            log_err(str(exc))
            return
        log_ok("auth ready")

        time.sleep(0.4)
        self.menu()


def main() -> None:
    try:
        App().start()
    except KeyboardInterrupt:
        print()
        log_warn("interrupted")


if __name__ == "__main__":
    main()
