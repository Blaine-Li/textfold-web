"""Single-owner web login. No shared default password, public signup, or browser-side secrets.

Credentials are created at the terminal; only their salted PBKDF2 hash is stored.
Ordinary sessions live in this process. Explicitly saved logins persist as hashes for 30 days.
Both expire and are revoked on logout or account reset.
"""
import collections
import contextlib
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from http.cookies import CookieError, SimpleCookie
from urllib.parse import urlsplit

from . import store

ITERATIONS = 600_000
SESSION_SECONDS = 12 * 60 * 60
IDLE_SECONDS = 2 * 60 * 60
REMEMBER_SECONDS = 30 * 24 * 60 * 60
LOGIN_WINDOW = 5 * 60
LOGIN_ATTEMPTS = 10


def enabled():
    return os.environ.get("TEXTFOLD_AUTH", "").lower() in ("1", "true", "yes")


def public_origin(value):
    """One explicit HTTPS origin, never a wildcard or a value supplied by forwarding headers."""
    if not value:
        return ""
    try:
        u = urlsplit(value)
        port = u.port
        if (u.scheme != "https" or not u.hostname or u.username is not None or u.password is not None
                or u.path not in ("", "/") or u.query or u.fragment or any(c.isspace() for c in value)):
            raise ValueError
        host = u.hostname.encode("idna").decode("ascii").lower()
        if not re.fullmatch(r"[a-z0-9.-]+|[a-f0-9:]+", host) or "*" in host:
            raise ValueError
        host = f"[{host}]" if ":" in host else host
        return f"https://{host}" + (f":{port}" if port and port != 443 else "")
    except (ValueError, UnicodeError):
        raise ValueError("TEXTFOLD_PUBLIC_ORIGIN must be one HTTPS origin, e.g. https://read.example.com") from None


def safe_next(value):
    value = value if isinstance(value, str) else "/"
    if (not value.startswith("/") or value.startswith("//") or "\\" in value or len(value) > 2048
            or any(ord(c) < 32 or ord(c) == 127 for c in value) or urlsplit(value).path == "/login"):
        return "/"
    return value


def credential_path():
    return store.HOME / "web-auth.json"


@contextlib.contextmanager
def saved_sessions(create=False):
    """Persist only hashes of explicitly remembered logins, alongside the private account file."""
    path = store.HOME / "web-sessions.sqlite3"
    if not create and not path.exists():
        yield None
        return
    connection = None
    try:
        if create:
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
            os.close(descriptor)
            os.chmod(path, 0o600)
        connection = sqlite3.connect(str(path), timeout=5)
        with connection:
            connection.execute("CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, account_hash TEXT NOT NULL, expires REAL NOT NULL)")
            yield connection
    except sqlite3.Error as error:
        raise OSError("Saved login storage is unavailable") from error
    finally:
        if connection is not None:
            connection.close()


def set_account(username, password, replace=False):
    username = username.strip()
    if not username or len(username) > 100 or any(ord(c) < 32 for c in username):
        raise ValueError("Account name must contain 1–100 characters without control characters")
    if len(password) < 12 or len(password.encode("utf-8")) > 1024:
        raise ValueError("Use a password of at least 12 characters and at most 1024 UTF-8 bytes")
    target = credential_path()
    if target.exists() and not replace:
        raise ValueError("An account already exists. Use 'account reset' to replace it")
    salt = secrets.token_bytes(32)
    record = {"version": 1, "username": username, "iterations": ITERATIONS, "salt": salt.hex(),
              "digest": hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS).hex()}
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{secrets.token_hex(8)}.tmp")
    try:
        descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(record, output, ensure_ascii=False)
        if replace:
            os.replace(temporary, target)
        else:
            # Atomic no-clobber creation even when two setup commands race.
            os.link(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return username


def account_command(args):
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m textfold account")
    parser.add_argument("action", choices=("init", "reset"))
    parser.add_argument("--username", required=True)
    options = parser.parse_args(args)
    if options.action == "init" and credential_path().exists():
        parser.error("An account already exists; use 'account reset' to replace it")
    password = getpass.getpass("Password (at least 12 characters): ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        parser.error("Passwords do not match")
    try:
        username = set_account(options.username, password, replace=options.action == "reset")
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(f"Account '{username}' saved. Existing sessions are revoked on their next request.")


class Access:
    def __init__(self, required=None, origin=None):
        self.required = enabled() if required is None else required
        self.origin = public_origin(os.environ.get("TEXTFOLD_PUBLIC_ORIGIN", "") if origin is None else origin)
        if self.origin and not self.required:
            raise ValueError("Public access requires authentication: use --auth")
        self.authority = urlsplit(self.origin).netloc
        self.sessions = collections.OrderedDict()
        self.attempts = collections.OrderedDict()
        self.global_attempts = collections.deque()
        self.lock = threading.RLock()
        self.verifying = threading.BoundedSemaphore(2)
        self.fingerprint = None

    def remote_host(self, host):
        return bool(self.authority) and (host or "").lower() == self.authority

    def allowed_origin(self, host, origin):
        expected = self.origin if self.remote_host(host) else f"http://{host}"
        return isinstance(origin, str) and hmac.compare_digest(origin.encode(), expected.encode())

    def credentials(self):
        try:
            raw = credential_path().read_bytes()
        except FileNotFoundError:
            raw = b""
        fingerprint = hashlib.sha256(raw).digest()
        with self.lock:
            if fingerprint != self.fingerprint:
                self.sessions.clear()
                self.fingerprint = fingerprint
        if not raw:
            return None
        try:
            value = json.loads(raw)
            if (value.get("version") != 1 or not isinstance(value.get("username"), str) or not value["username"]
                    or type(value.get("iterations")) is not int or not 100_000 <= value["iterations"] <= 5_000_000
                    or len(bytes.fromhex(value["salt"])) < 16 or len(bytes.fromhex(value["digest"])) != 32):
                raise ValueError
            return value
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ValueError("Web account configuration is invalid; reset it at the server terminal") from None

    def cookie_name(self, host):
        return "__Host-textfold_session" if self.remote_host(host) else "textfold_session"

    def token(self, headers):
        cookie = SimpleCookie()
        try:
            cookie.load(headers.get("Cookie", ""))
        except CookieError:
            return ""
        morsel = cookie.get(self.cookie_name(headers.get("Host")))
        value = morsel.value if morsel else ""
        return value if re.fullmatch(r"[A-Za-z0-9_-]{43}", value) else ""

    def cookie(self, token, host, remember=False):
        cookie = SimpleCookie()
        name = self.cookie_name(host)
        cookie[name] = token
        cookie[name]["path"] = "/"
        cookie[name]["httponly"] = True
        cookie[name]["samesite"] = "Lax"
        if not token:
            cookie[name]["max-age"] = 0
        elif remember:
            cookie[name]["max-age"] = REMEMBER_SECONDS
        if self.remote_host(host):
            cookie[name]["secure"] = True
        return cookie[name].OutputString()

    def session(self, headers):
        record = self.credentials()
        token = self.token(headers)
        if not record or not token:
            return None
        key, now = hashlib.sha256(token.encode()).digest(), time.time()
        with self.lock:
            value = self.sessions.get(key)
            if not value:
                with saved_sessions() as saved:
                    row = saved.execute("SELECT expires FROM sessions WHERE token_hash = ? AND account_hash = ?",
                                        (key.hex(), self.fingerprint.hex())).fetchone() if saved else None
                return {"username": record["username"]} if row and row[0] > now else None
            if value["expires"] <= now or value["seen"] + IDLE_SECONDS <= now:
                self.sessions.pop(key, None)
                return None
            value["seen"] = now
            self.sessions.move_to_end(key)
        return {"username": record["username"]}

    def login(self, username, password, peer, remember=False):
        """Return (token, error, retry seconds). Failed attempts are bounded across peers as well."""
        record = self.credentials()
        if record is None:
            return "", "account-not-configured", 0
        now = time.time()
        with self.lock:
            recent = self.attempts.setdefault(peer, collections.deque())
            self.attempts.move_to_end(peer)
            while recent and recent[0] <= now - LOGIN_WINDOW:
                recent.popleft()
            while self.global_attempts and self.global_attempts[0] <= now - LOGIN_WINDOW:
                self.global_attempts.popleft()
            if len(recent) >= LOGIN_ATTEMPTS or len(self.global_attempts) >= 100:
                return "", "rate-limited", LOGIN_WINDOW
            recent.append(now)
            self.global_attempts.append(now)
            while len(self.attempts) > 1024:
                self.attempts.popitem(last=False)
        if not self.verifying.acquire(blocking=False):
            return "", "rate-limited", 2
        try:
            supplied = password.encode("utf-8") if isinstance(password, str) else b""
            if len(supplied) > 1024:
                supplied = b""
            digest = hashlib.pbkdf2_hmac("sha256", supplied, bytes.fromhex(record["salt"]), record["iterations"])
            password_ok = hmac.compare_digest(digest, bytes.fromhex(record["digest"]))
            username_ok = isinstance(username, str) and hmac.compare_digest(username.encode(), record["username"].encode())
        finally:
            self.verifying.release()
        if not (username_ok and password_ok):
            return "", "invalid-credentials", 0
        token = secrets.token_urlsafe(32)
        key = hashlib.sha256(token.encode()).digest()
        with self.lock:
            # Do not mint a session if the account was reset while verification ran.
            if self.credentials() != record:
                return "", "invalid-credentials", 0
            self.attempts.pop(peer, None)
            if remember:
                with saved_sessions(create=True) as saved:
                    saved.execute("DELETE FROM sessions WHERE expires <= ? OR account_hash != ?", (now, self.fingerprint.hex()))
                    saved.execute("INSERT INTO sessions VALUES (?, ?, ?)", (key.hex(), self.fingerprint.hex(), now + REMEMBER_SECONDS))
                    saved.execute("DELETE FROM sessions WHERE token_hash IN (SELECT token_hash FROM sessions ORDER BY expires DESC LIMIT -1 OFFSET 256)")
            else:
                self.sessions[key] = {"expires": now + SESSION_SECONDS, "seen": now}
                while len(self.sessions) > 256:
                    self.sessions.popitem(last=False)
        return token, "", 0

    def logout(self, headers):
        key = hashlib.sha256(self.token(headers).encode()).digest()
        with self.lock:
            self.sessions.pop(key, None)
            with saved_sessions() as saved:
                if saved:
                    saved.execute("DELETE FROM sessions WHERE token_hash = ?", (key.hex(),))
