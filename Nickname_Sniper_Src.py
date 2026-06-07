#!/usr/bin/env python3
import itertools
import string
import threading
import time
import os
import sys
import signal
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("Brakuje biblioteki 'requests'. Zainstaluj: pip install requests")
    sys.exit(1)


class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    GREEN   = "\033[92m"
    RED     = "\033[91m"
    YELLOW  = "\033[93m"
    CYAN    = "\033[96m"
    MAGENTA = "\033[95m"
    BLUE    = "\033[94m"
    WHITE   = "\033[97m"
    GRAY    = "\033[90m"

    @staticmethod
    def supports_color() -> bool:
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

if not C.supports_color():
    for _a in list(vars(C)):
        if not _a.startswith("_") and isinstance(getattr(C, _a), str):
            setattr(C, _a, "")


def _http_check(url, headers, available_on, session, timeout=8):
    try:
        r = session.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if r.status_code == available_on:
            return True
        if r.status_code in (200, 201, 301, 302):
            return False
        return None
    except Exception:
        return None


def check_github(username, session, cfg):
    return _http_check(
        f"https://api.github.com/users/{username}",
        {"Accept": "application/vnd.github+json"},
        404, session,
    )


def check_npm(username, session, cfg):
    return _http_check(f"https://registry.npmjs.org/~{username}", {}, 404, session)


def check_pypi(username, session, cfg):
    return _http_check(f"https://pypi.org/user/{username}/", {}, 404, session)


def check_crates(username, session, cfg):
    return _http_check(
        f"https://crates.io/api/v1/users/{username}",
        {"User-Agent": "username-checker/2.2"},
        404, session,
    )


def check_youtube(username, session, cfg):
    if len(username) < 3:
        return None
    return _http_check(
        f"https://www.youtube.com/@{username}",
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
        404, session,
    )


def check_twitter(username, session, cfg):
    if len(username) > 15:
        return None
    try:
        r = session.get(
            f"https://x.com/{username}",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=10,
            allow_redirects=True,
        )
        if r.status_code == 404:
            return True
        if r.status_code == 200:
            body = r.text
            if "This account doesn" in body or "caution" in body.lower():
                return True
            return False
        return None
    except Exception:
        return None


def check_discord(username, session, cfg):
    if len(username) < 2 or len(username) > 32:
        return None
    allowed = set(string.ascii_lowercase + string.digits + "_.")
    if not all(c in allowed for c in username):
        return None
    try:
        r = session.post(
            "https://discord.com/api/v9/unique-username/username-attempt-unauthed",
            json={"username": username},
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Origin": "https://discord.com",
                "Referer": "https://discord.com/register",
            },
            timeout=8,
        )
        if r.status_code == 200:
            taken = r.json().get("taken", None)
            return None if taken is None else not taken
        if r.status_code == 400:
            try:
                if "USERNAME_ALREADY_TAKEN" in str(r.json().get("errors", {})):
                    return False
            except Exception:
                pass
            return None
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After", 2)))
            return None
        return None
    except Exception:
        return None


_twitch_token_lock = threading.Lock()
_twitch_token: dict = {"access_token": None, "expires_at": 0}


def _get_twitch_token(client_id, client_secret):
    global _twitch_token
    with _twitch_token_lock:
        now = time.time()
        if _twitch_token["access_token"] and now < _twitch_token["expires_at"] - 60:
            return _twitch_token["access_token"]
        try:
            r = requests.post(
                "https://id.twitch.tv/oauth2/token",
                data={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                _twitch_token["access_token"] = data["access_token"]
                _twitch_token["expires_at"] = now + data.get("expires_in", 3600)
                return _twitch_token["access_token"]
            return None
        except Exception:
            return None


def check_twitch(username, session, cfg):
    if len(username) < 4 or len(username) > 25:
        return None
    client_id = cfg.get("twitch_client_id", "")
    client_secret = cfg.get("twitch_client_secret", "")
    if not client_id or not client_secret:
        return None
    token = _get_twitch_token(client_id, client_secret)
    if not token:
        return None
    try:
        r = session.get(
            f"https://api.twitch.tv/helix/users?login={username}",
            headers={"Client-ID": client_id, "Authorization": f"Bearer {token}"},
            timeout=8,
        )
        if r.status_code == 200:
            return len(r.json().get("data", [])) == 0
        if r.status_code == 401:
            with _twitch_token_lock:
                _twitch_token["access_token"] = None
            return None
        return None
    except Exception:
        return None


def check_minecraft(username, session, cfg):
    if len(username) < 3 or len(username) > 16:
        return None
    if not all(c in set(string.ascii_letters + string.digits + "_") for c in username):
        return None
    try:
        r = session.get(
            f"https://api.mojang.com/users/profiles/minecraft/{username}",
            headers={"Accept": "application/json"},
            timeout=8,
        )
        if r.status_code == 200:
            return False
        if r.status_code in (404, 204):
            return True
        if r.status_code == 429:
            time.sleep(10)
            return None
        return None
    except Exception:
        return None


def check_roblox(username, session, cfg):
    if len(username) < 3 or len(username) > 20:
        return None
    if not all(c in set(string.ascii_letters + string.digits + "_") for c in username):
        return None
    if username.startswith("_") or username.endswith("_") or "__" in username:
        return None
    try:
        r = session.post(
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [username], "excludeBannedUsers": False},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=8,
        )
        if r.status_code == 200:
            return len(r.json().get("data", [])) == 0
        if r.status_code == 429:
            time.sleep(5)
            return None
        return None
    except Exception:
        return None


def check_steam(username, session, cfg):
    if len(username) < 2 or len(username) > 32:
        return None
    if not all(c in set(string.ascii_letters + string.digits + "_-") for c in username):
        return None
    try:
        r = session.get(
            f"https://steamcommunity.com/id/{username}?xml=1",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/xml,application/xml",
            },
            timeout=10,
        )
        if r.status_code == 200:
            if "<error>" in r.text and "could not be found" in r.text:
                return True
            if "<steamID64>" in r.text:
                return False
            return None
        if r.status_code == 429:
            time.sleep(5)
            return None
        return None
    except Exception:
        return None


def check_epic(username, session, cfg):
    if len(username) < 3 or len(username) > 16:
        return None
    try:
        r = session.get(
            f"https://fortnite-api.com/v2/stats/br/v2?name={username}",
            headers={"User-Agent": "username-checker/2.2", "Accept": "application/json"},
            timeout=10,
        )
        if r.status_code == 200:
            return False
        if r.status_code == 404:
            try:
                err = r.json().get("error", "").lower()
                if "not found" in err or "player" in err:
                    return True
            except Exception:
                pass
            return True
        if r.status_code == 403:
            return False
        if r.status_code == 429:
            time.sleep(3)
            return None
        return None
    except Exception:
        return None


def check_gmail(username, session, cfg):
    if len(username) < 6 or len(username) > 30:
        return None
    allowed = set(string.ascii_lowercase + string.digits + ".")
    if not all(c in allowed for c in username.lower()):
        return None
    if username.startswith(".") or username.endswith(".") or ".." in username:
        return None
    try:
        r = session.post(
            "https://accounts.google.com/_/signin/sl/lookup",
            data={
                "f.req": f'["{username}@gmail.com",null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null]',
                "flowName": "GlifWebSignIn",
                "flowEntry": "ServiceLogin",
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://accounts.google.com/",
                "Origin": "https://accounts.google.com",
            },
            timeout=10,
        )
        if r.status_code == 200:
            text = r.text
            if "noAccount" in text or "identifierMissing" in text:
                return True
            if "accountLookup" in text or "profileInformation" in text:
                return False
            return None
        r2 = session.get(
            f"https://mail.google.com/mail/gxlu?email={username}@gmail.com",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"},
            timeout=8,
            allow_redirects=False,
        )
        if r2.status_code in (302, 301):
            if "GMAIL_AT" in r2.headers.get("Set-Cookie", "") or "account" in r2.headers.get("Location", "").lower():
                return False
            return True
        return None
    except Exception:
        return None


PLATFORMS = {
    "github":    {"name": "GitHub",      "checker": check_github,    "rate_limit": 0.5, "note": "Bez klucza API. Limit: ~60 req/h.",             "needs_key": False},
    "npm":       {"name": "npm",         "checker": check_npm,       "rate_limit": 0.3, "note": "Publiczne API – bez limitu.",                    "needs_key": False},
    "pypi":      {"name": "PyPI",        "checker": check_pypi,      "rate_limit": 0.5, "note": "Publiczne API – bez limitu.",                    "needs_key": False},
    "crates":    {"name": "crates.io",   "checker": check_crates,    "rate_limit": 1.0, "note": "Publiczne API – 1 req/s.",                       "needs_key": False},
    "youtube":   {"name": "YouTube",     "checker": check_youtube,   "rate_limit": 1.0, "note": "Profil @handle. Min. 3 znaki.",                  "needs_key": False},
    "twitter":   {"name": "X / Twitter", "checker": check_twitter,   "rate_limit": 2.0, "note": "Profil publiczny. Max 15 znaków.",               "needs_key": False},
    "discord":   {"name": "Discord",     "checker": check_discord,   "rate_limit": 1.5, "note": "Pomelo API. Działa z domowego IP. 2–32 znaki.",  "needs_key": False},
    "twitch":    {"name": "Twitch",      "checker": check_twitch,    "rate_limit": 0.5, "note": "Wymaga klucza z dev.twitch.tv. 4–25 znaków.",    "needs_key": True},
    "minecraft": {"name": "Minecraft",   "checker": check_minecraft, "rate_limit": 1.0, "note": "Mojang API. Bez klucza. 3–16 znaków.",           "needs_key": False},
    "roblox":    {"name": "Roblox",      "checker": check_roblox,    "rate_limit": 0.8, "note": "Publiczne API. Bez klucza. 3–20 znaków.",        "needs_key": False},
    "steam":     {"name": "Steam",       "checker": check_steam,     "rate_limit": 1.5, "note": "Vanity URL profilu. Bez klucza. 2–32 znaki.",    "needs_key": False},
    "epic":      {"name": "Epic Games",  "checker": check_epic,      "rate_limit": 1.0, "note": "fortnite-api.com. Bez klucza. 3–16 znaków.",     "needs_key": False},
    "gmail":     {"name": "Gmail",       "checker": check_gmail,     "rate_limit": 3.0, "note": "⚠ NIEDOKŁADNE – Google chroni prywatność. 6–30 znaków.", "needs_key": False},
}


class Stats:
    def __init__(self):
        self._lock      = threading.Lock()
        self.checked    = 0
        self.available  = 0
        self.errors     = 0
        self.skipped    = 0
        self.start_time = time.monotonic()

    def inc(self, field):
        with self._lock:
            setattr(self, field, getattr(self, field) + 1)

    def snapshot(self):
        with self._lock:
            elapsed = time.monotonic() - self.start_time
            return {
                "checked":   self.checked,
                "available": self.available,
                "errors":    self.errors,
                "skipped":   self.skipped,
                "elapsed":   elapsed,
                "speed":     self.checked / elapsed if elapsed > 0 else 0,
            }


_session_local = threading.local()

def get_session():
    if not hasattr(_session_local, "session"):
        s = requests.Session()
        retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("https://", adapter)
        s.mount("http://",  adapter)
        _session_local.session = s
    return _session_local.session


def generate_usernames(min_len, max_len, use_lower, use_upper, use_digits):
    charset = (
        (string.ascii_lowercase if use_lower  else "") +
        (string.ascii_uppercase if use_upper  else "") +
        (string.digits          if use_digits else "")
    )
    if not charset:
        return
    for length in range(min_len, max_len + 1):
        for combo in itertools.product(charset, repeat=length):
            yield "".join(combo)

def count_combinations(min_len, max_len, use_lower, use_upper, use_digits):
    size = (26 if use_lower else 0) + (26 if use_upper else 0) + (10 if use_digits else 0)
    return sum(size ** l for l in range(min_len, max_len + 1)) if size else 0


_print_lock = threading.Lock()

def fmt_time(s):
    return str(timedelta(seconds=int(s)))

def fmt_num(n):
    return f"{n:,}".replace(",", " ")

def print_progress(snap, total, current, width=38):
    checked = snap["checked"]
    pct     = checked / total * 100 if total > 0 else 0
    filled  = int(width * checked / total) if total > 0 else 0
    bar     = "█" * filled + "░" * (width - filled)
    speed   = snap["speed"]
    eta     = (total - checked) / speed if speed > 0 else 0
    with _print_lock:
        sys.stdout.write("\r" + " " * 130 + "\r")
        sys.stdout.write(
            f"{C.CYAN}[{bar}]{C.RESET} "
            f"{C.BOLD}{pct:5.1f}%{C.RESET} | "
            f"{C.WHITE}{fmt_num(checked)}{C.RESET}/{fmt_num(total)} | "
            f"{C.GREEN}✓{snap['available']}{C.RESET} | "
            f"{C.RED}✗{snap['errors']}{C.RESET} | "
            f"{C.YELLOW}{speed:.1f}/s{C.RESET} | "
            f"ETA {fmt_time(eta)} | "
            f"{C.GRAY}{current[:18]:<18}{C.RESET}"
        )
        sys.stdout.flush()

def print_found(username, platform):
    with _print_lock:
        sys.stdout.write("\r" + " " * 130 + "\r")
        print(
            f"  {C.GREEN}{C.BOLD}✔ DOSTĘPNA:{C.RESET} "
            f"{C.WHITE}{C.BOLD}{username:<20}{C.RESET}"
            f"{C.GRAY} [{platform}]{C.RESET}"
        )

def print_discord_blocked():
    with _print_lock:
        sys.stdout.write("\r" + " " * 130 + "\r")
        print(f"  {C.YELLOW}⚠  Discord: blokada IP centrum danych. Wyniki mogą być niedokładne.{C.RESET}")


class ResultWriter:
    def __init__(self, path):
        self.path  = path
        self._lock = threading.Lock()
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Dostępne nazwy użytkownika\n")
            f.write(f"# Wygenerowano: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Format: nazwa | platforma\n\n")

    def write(self, username, platform):
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(f"{username} | {platform}\n")


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def print_banner():
    print(f"""
{C.CYAN}{C.BOLD}╔═════════════════════════════════════════════════════╗
║     USERNAME AVAILABILITY CHECKER  v2.2             ║
║     Wyszukiwarka dostępnych nazw użytkownika         ║
╚═════════════════════════════════════════════════════╝{C.RESET}
""")

def ask_int(prompt, min_v, max_v, default):
    while True:
        try:
            raw = input(f"  {prompt} [{default}]: ").strip()
            val = int(raw) if raw else default
            if min_v <= val <= max_v:
                return val
            print(f"    {C.RED}Podaj wartość od {min_v} do {max_v}.{C.RESET}")
        except ValueError:
            print(f"    {C.RED}Nieprawidłowa wartość.{C.RESET}")

def ask_bool(prompt, default):
    dstr = "T/n" if default else "t/N"
    while True:
        raw = input(f"  {prompt} [{dstr}]: ").strip().lower()
        if raw == "":                          return default
        if raw in ("t", "tak", "y", "yes"):   return True
        if raw in ("n", "nie", "no"):          return False
        print(f"    {C.RED}Wpisz T lub N.{C.RESET}")

def ask_str(prompt, default=""):
    raw = input(f"  {prompt}{f' [{default}]' if default else ''}: ").strip()
    return raw if raw else default

def choose_platform():
    keys = list(PLATFORMS.keys())
    print(f"\n  {C.BOLD}Dostępne platformy:{C.RESET}")
    for i, k in enumerate(keys, 1):
        p = PLATFORMS[k]
        key_marker = f" {C.YELLOW}[wymaga klucza]{C.RESET}" if p["needs_key"] else ""
        print(f"    {C.CYAN}{i}.{C.RESET} {C.BOLD}{p['name']:<14}{C.RESET} {C.GRAY}{p['note']}{C.RESET}{key_marker}")
    while True:
        raw = input(f"\n  Wybierz platformę [1]: ").strip()
        try:
            idx = int(raw) - 1 if raw else 0
            if 0 <= idx < len(keys):
                return keys[idx]
        except ValueError:
            pass
        print(f"    {C.RED}Nieprawidłowy wybór.{C.RESET}")

def configure():
    clear_screen()
    print_banner()
    print(f"{C.BOLD}── KONFIGURACJA ──────────────────────────────────────{C.RESET}\n")

    min_len = ask_int("Minimalna długość nazwy", 1, 16, 1)
    max_len = ask_int("Maksymalna długość nazwy", min_len, 16, min(4, 16))

    print(f"\n  {C.BOLD}Zestawy znaków:{C.RESET}")
    use_lower  = ask_bool("  Małe litery (a-z)", True)
    use_upper  = ask_bool("  Wielkie litery (A-Z)", False)
    use_digits = ask_bool("  Cyfry (0-9)", True)

    if not any([use_lower, use_upper, use_digits]):
        print(f"\n  {C.RED}Musisz wybrać co najmniej jeden zestaw znaków!{C.RESET}")
        sys.exit(1)

    platform = choose_platform()

    twitch_client_id = ""
    twitch_client_secret = ""
    if platform == "twitch":
        print(f"\n  {C.YELLOW}Twitch wymaga darmowego klucza API.{C.RESET}")
        print(f"  {C.GRAY}Utwórz aplikację na: https://dev.twitch.tv/console{C.RESET}")
        print(f"  {C.GRAY}Typ aplikacji: 'Chat Bot' lub 'Application Integration'{C.RESET}\n")
        twitch_client_id     = ask_str("Client ID")
        twitch_client_secret = ask_str("Client Secret")
        if not twitch_client_id or not twitch_client_secret:
            print(f"\n  {C.RED}Klucze Twitch są wymagane!{C.RESET}")
            sys.exit(1)
        print(f"\n  {C.GRAY}Weryfikacja klucza Twitch…{C.RESET}", end="", flush=True)
        token = _get_twitch_token(twitch_client_id, twitch_client_secret)
        if token:
            print(f" {C.GREEN}OK{C.RESET}")
        else:
            print(f" {C.RED}BŁĄD – sprawdź Client ID i Client Secret.{C.RESET}")
            sys.exit(1)

    print()
    threads  = ask_int("Liczba wątków", 1, 20, 3)
    out_file = ask_str("Plik wyników", "available_names.txt")

    total     = count_combinations(min_len, max_len, use_lower, use_upper, use_digits)
    chars_str = ("a-z " if use_lower else "") + ("A-Z " if use_upper else "") + ("0-9" if use_digits else "")

    print(f"""
{C.BOLD}── PODSUMOWANIE ──────────────────────────────────────{C.RESET}
  Zakres długości  : {C.WHITE}{min_len} – {max_len}{C.RESET}
  Zestaw znaków    : {C.WHITE}{chars_str.strip()}{C.RESET}
  Platforma        : {C.WHITE}{PLATFORMS[platform]['name']}{C.RESET}
  Łączne kombinacje: {C.YELLOW}{fmt_num(total)}{C.RESET}
  Wątki            : {C.WHITE}{threads}{C.RESET}
  Plik wyników     : {C.WHITE}{out_file}{C.RESET}
""")

    if platform == "discord":
        print(f"  {C.YELLOW}⚠  Discord: jeśli używasz VPS/chmury, wyniki mogą być niedokładne.{C.RESET}")
    if platform == "twitter":
        print(f"  {C.YELLOW}⚠  X/Twitter: wolne tempo wymagane, może blokować przy zbyt wielu zapytaniach.{C.RESET}")
    if platform == "gmail":
        print(f"  {C.YELLOW}⚠  Gmail: Google chroni prywatność – wyniki mogą być NIEDOKŁADNE.{C.RESET}")
        print(f"  {C.YELLOW}   Zbyt wiele zapytań wywoła CAPTCHA i blokadę IP.{C.RESET}")
    if platform == "steam":
        print(f"  {C.YELLOW}⚠  Steam: sprawdza Vanity URL profilu, nie nazwę konta.{C.RESET}")
    if platform == "epic":
        print(f"  {C.YELLOW}⚠  Epic Games: wymaga publicznego profilu Fortnite. Prywatne = zajęte.{C.RESET}")
    if total > 500_000:
        print(f"  {C.YELLOW}⚠  {fmt_num(total)} kombinacji – skanowanie może zająć wiele godzin.{C.RESET}")

    print()
    if not ask_bool("Rozpocząć skanowanie?", True):
        print("  Anulowano.")
        sys.exit(0)

    return {
        "min_len":              min_len,
        "max_len":              max_len,
        "use_lower":            use_lower,
        "use_upper":            use_upper,
        "use_digits":           use_digits,
        "platform":             platform,
        "threads":              threads,
        "out_file":             out_file,
        "total":                total,
        "twitch_client_id":     twitch_client_id,
        "twitch_client_secret": twitch_client_secret,
    }


_stop_event = threading.Event()
_discord_blocked_warned = False

def signal_handler(sig, frame):
    print(f"\n\n  {C.YELLOW}Zatrzymywanie… poczekaj chwilę.{C.RESET}")
    _stop_event.set()

def worker(username, platform_key, stats, writer, rate_sleep, cfg):
    global _discord_blocked_warned
    if _stop_event.is_set():
        return
    result = PLATFORMS[platform_key]["checker"](username, get_session(), cfg)
    stats.inc("checked")
    if result is True:
        stats.inc("available")
        writer.write(username, PLATFORMS[platform_key]["name"])
        print_found(username, PLATFORMS[platform_key]["name"])
    elif result is None:
        stats.inc("errors")
        if platform_key == "discord" and not _discord_blocked_warned:
            _discord_blocked_warned = True
            print_discord_blocked()
    time.sleep(rate_sleep)

def run_scan(cfg):
    signal.signal(signal.SIGINT, signal_handler)

    stats  = Stats()
    writer = ResultWriter(cfg["out_file"])
    total  = cfg["total"]
    pkey   = cfg["platform"]
    rate_per_thread = max(0.05, PLATFORMS[pkey]["rate_limit"] / cfg["threads"])

    gen = generate_usernames(
        cfg["min_len"], cfg["max_len"],
        cfg["use_lower"], cfg["use_upper"], cfg["use_digits"],
    )

    print(f"\n{C.BOLD}── SKANOWANIE ──────────────────────────────────────{C.RESET}")
    print(f"  {C.GRAY}Ctrl+C aby przerwać i zobaczyć statystyki{C.RESET}\n")

    last_name = ""
    last_upd  = time.monotonic()
    futures   = {}

    with ThreadPoolExecutor(max_workers=cfg["threads"]) as executor:
        for username in gen:
            if _stop_event.is_set():
                break
            while len(futures) >= cfg["threads"] * 6:
                done = [f for f in list(futures) if f.done()]
                for f in done:
                    futures.pop(f, None)
                if len(futures) >= cfg["threads"] * 6:
                    time.sleep(0.05)

            futures[executor.submit(worker, username, pkey, stats, writer, rate_per_thread, cfg)] = username
            last_name = username

            now = time.monotonic()
            if now - last_upd >= 0.25:
                print_progress(stats.snapshot(), total, last_name)
                last_upd = now

        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception:
                pass

    snap = stats.snapshot()
    print_progress(snap, total, "zakończono")
    print(f"\n\n{C.BOLD}── WYNIKI ──────────────────────────────────────────{C.RESET}")
    print(f"  Sprawdzono nazw  : {C.WHITE}{fmt_num(snap['checked'])}{C.RESET}")
    print(f"  Dostępne         : {C.GREEN}{C.BOLD}{fmt_num(snap['available'])}{C.RESET}")
    print(f"  Zajęte/błędy     : {C.RED}{fmt_num(snap['errors'])}{C.RESET}")
    print(f"  Czas działania   : {C.CYAN}{fmt_time(snap['elapsed'])}{C.RESET}")
    print(f"  Śr. szybkość     : {C.YELLOW}{snap['speed']:.2f} nazw/s{C.RESET}")
    print(f"  Wyniki zapisano  : {C.WHITE}{os.path.abspath(cfg['out_file'])}{C.RESET}")
    print()


def main():
    cfg = configure()
    run_scan(cfg)

if __name__ == "__main__":
    main()
