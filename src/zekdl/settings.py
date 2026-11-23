"""Configurações do usuário (arquivo JSON 0600, validado ao carregar)."""
import json
import os
import tempfile
from pathlib import Path

from .downloader import AUDIO_FORMATS, BROWSERS, QUALITIES


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "zek-download"


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return Path(base) / "zek-download"


def default_download_dir() -> str:
    try:
        import gi
        gi.require_version("GLib", "2.0")
        from gi.repository import GLib
        d = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
        if d:
            return d
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Downloads")


class Settings:
    CHOICES = {
        "mode": ("video", "audio"),
        "quality": tuple(QUALITIES),
        "audio_format": tuple(AUDIO_FORMATS),
        "channel": ("stable", "nightly"),
        "cookies_browser": tuple(BROWSERS),
    }

    def __init__(self, path=None):
        self.path = Path(path) if path else config_dir() / "settings.json"
        self.values = {
            "folder": default_download_dir(),
            "mode": "video",
            "quality": "1080",
            "audio_format": "mp3",
            "playlist": False,
            "channel": "stable",
            "auto_update": True,
            "cookies_browser": "",
            "last_check": 0.0,
        }
        self.load()

    def __getitem__(self, key):
        return self.values[key]

    def __setitem__(self, key, value):
        self.values[key] = value

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        for key, default in list(self.values.items()):
            val = data.get(key, default)
            if key in self.CHOICES and val not in self.CHOICES[key]:
                continue
            if key == "folder" and (not isinstance(val, str) or not val):
                continue
            if key in ("playlist", "auto_update") and not isinstance(val, bool):
                continue
            if key == "last_check" and not isinstance(val, (int, float)):
                continue
            self.values[key] = val

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".settings-")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.values, fh, indent=2)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except OSError:
            pass
