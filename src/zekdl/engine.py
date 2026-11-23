"""Gerenciador do yt-dlp (o "motor" de download).

O Zek Download NÃO embute o yt-dlp. Ele baixa o executável oficial das releases do
yt-dlp no GitHub, confere o SHA-256 contra o arquivo SHA2-256SUMS publicado na
mesma release e guarda em ~/.local/share/zek-download/bin (sem precisar de root).
Quando os sites mudam e o yt-dlp lança correção, o Zek Download se atualiza sozinho.
"""
import hashlib
import hmac
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__

REPOS = {
    "stable": "yt-dlp/yt-dlp",
    "nightly": "yt-dlp/yt-dlp-nightly-builds",
}
MAX_SUMS_BYTES = 256 * 1024
MAX_BINARY_BYTES = 250 * 1024 * 1024
VERSION_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}")


class EngineError(Exception):
    """Erro com mensagem já pronta para o usuário (pt-BR)."""


class _HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            raise urllib.error.URLError("redirecionamento inseguro bloqueado")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _default_opener():
    return urllib.request.build_opener(_HttpsOnlyRedirect)


def parse_sums(text: str) -> dict:
    """Interpreta o conteúdo do SHA2-256SUMS -> {arquivo: sha256}."""
    sums = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            sums[parts[1].lstrip("*")] = parts[0].lower()
    return sums


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def primary_asset() -> str:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "yt-dlp_linux"
    if machine in ("aarch64", "arm64"):
        return "yt-dlp_linux_aarch64"
    if machine.startswith("armv7"):
        return "yt-dlp_linux_armv7l"
    return "yt-dlp"  # zipapp, roda com o Python do sistema


class Engine:
    def __init__(self, data_dir, channel="stable", opener=None):
        self.dir = Path(data_dir) / "bin"
        self.path = self.dir / "yt-dlp"
        self.meta_path = self.dir / "engine.json"
        self.channel = channel if channel in REPOS else "stable"
        self.opener = opener or _default_opener()
        self.lock = threading.RLock()
        self._version = None

    # ------------------------------------------------------------ rede
    def _request(self, url):
        if not url.lower().startswith("https://"):
            raise EngineError("Endereço de atualização inválido.")
        req = urllib.request.Request(url, headers={"User-Agent": f"Zek Download/{__version__}"})
        try:
            return self.opener.open(req, timeout=30)
        except urllib.error.HTTPError as exc:
            raise EngineError(f"O servidor de atualização respondeu com erro {exc.code}.") from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise EngineError("Sem conexão com a internet (não consegui falar com o GitHub).") from exc

    def _get_bytes(self, url, limit):
        with self._request(url) as resp:
            data = resp.read(limit + 1)
        if len(data) > limit:
            raise EngineError("Resposta inesperadamente grande do servidor de atualização.")
        return data

    def _download_file(self, url, dest, limit, on_progress=None):
        h = hashlib.sha256()
        total_read = 0
        try:
            with self._request(url) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o700)
                with os.fdopen(fd, "wb") as out:
                    while True:
                        chunk = resp.read(1 << 16)
                        if not chunk:
                            break
                        total_read += len(chunk)
                        if total_read > limit:
                            raise EngineError("Arquivo maior do que o esperado; download abortado.")
                        h.update(chunk)
                        out.write(chunk)
                        if on_progress:
                            on_progress(total_read, total)
        except EngineError:
            raise
        except (OSError, TimeoutError) as exc:
            raise EngineError("A conexão caiu durante o download da atualização.") from exc
        return h.hexdigest()

    # ----------------------------------------------------------- estado
    def _meta(self) -> dict:
        try:
            data = json.loads(self.meta_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write_meta(self, meta: dict):
        tmp = self.meta_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta), encoding="utf-8")
        os.replace(tmp, self.meta_path)

    def _prefix(self, path, asset):
        return [sys.executable, str(path)] if asset == "yt-dlp" else [str(path)]

    def command(self):
        """Prefixo do comando para rodar o yt-dlp, ou None se não houver."""
        if self.path.exists():
            return self._prefix(self.path, self._meta().get("asset"))
        system = shutil.which("yt-dlp")
        return [system] if system else None

    def installed(self) -> bool:
        return self.path.exists()

    def version(self, refresh=False):
        if self._version and not refresh:
            return self._version
        cmd = self.command()
        if not cmd:
            return None
        try:
            out = subprocess.run(cmd + ["--version"], capture_output=True, text=True, timeout=90)
            ver = out.stdout.strip().splitlines()[0] if out.returncode == 0 and out.stdout.strip() else None
        except (OSError, subprocess.SubprocessError):
            ver = None
        self._version = ver
        return ver

    # -------------------------------------------------------- atualizar
    def _selftest(self, path, asset) -> str:
        try:
            out = subprocess.run(self._prefix(path, asset) + ["--version"],
                                 capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.SubprocessError):
            raise EngineError("O yt-dlp baixado não executou neste sistema.")
        ver = out.stdout.strip()
        if out.returncode != 0 or not VERSION_RE.match(ver):
            raise EngineError("O yt-dlp baixado não passou no teste de execução.")
        return ver

    def _install(self, base, asset, expected, on_progress):
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.dir, 0o700)
        tmp = self.dir / ".yt-dlp.download"
        try:
            got = self._download_file(base + asset, tmp, MAX_BINARY_BYTES, on_progress)
            if not hmac.compare_digest(got, expected):
                raise EngineError("Falha de segurança: o SHA-256 do yt-dlp baixado não confere. "
                                  "A atualização foi descartada.")
            os.chmod(tmp, 0o700)
            ver = self._selftest(tmp, asset)
            os.replace(tmp, self.path)
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass
        self._write_meta({"asset": asset, "channel": self.channel, "sha256": expected,
                          "version": ver, "installed_at": time.time()})
        self._version = ver

    def check_and_update(self, on_progress=None) -> str:
        """Retorna 'installed', 'updated' ou 'current'. Levanta EngineError."""
        with self.lock:
            base = f"https://github.com/{REPOS[self.channel]}/releases/latest/download/"
            sums = parse_sums(self._get_bytes(base + "SHA2-256SUMS", MAX_SUMS_BYTES).decode("utf-8", "replace"))
            if not sums:
                raise EngineError("Lista de verificação (SHA2-256SUMS) vazia ou inválida.")
            meta = self._meta()
            if self.path.exists() and meta.get("channel") == self.channel:
                asset = meta.get("asset")
                if asset in sums and hmac.compare_digest(sha256_file(self.path), sums[asset]):
                    return "current"
            had = self.path.exists()
            candidates = [a for a in dict.fromkeys([primary_asset(), "yt-dlp"]) if a in sums]
            last = EngineError("Nenhum arquivo compatível com este sistema na release do yt-dlp.")
            for asset in candidates:
                try:
                    self._install(base, asset, sums[asset], on_progress)
                    return "updated" if had else "installed"
                except EngineError as exc:
                    last = exc
            raise last
