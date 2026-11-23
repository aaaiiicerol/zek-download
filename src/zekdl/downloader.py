"""Validação de links, montagem dos argumentos do yt-dlp, execução e progresso.

Segurança: o yt-dlp é sempre executado SEM shell, com lista de argumentos,
ignorando arquivos de configuração do usuário (--ignore-config) e com o link
depois de "--" (nunca interpretado como opção).
"""
import itertools
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from urllib.parse import urlsplit

QUALITIES = ["best", "2160", "1440", "1080", "720", "480", "360"]
AUDIO_FORMATS = ["mp3", "m4a", "opus", "flac"]
BROWSERS = ["", "firefox", "chrome", "chromium", "brave", "edge", "opera", "vivaldi"]

# --------------------------------------------------------------- links

def validate_url(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        raise ValueError("Cole um link para começar.")
    if len(s) > 2048:
        raise ValueError("O link é grande demais.")
    if any(ord(c) < 32 or ord(c) == 127 or c.isspace() for c in s):
        raise ValueError("O link contém espaços ou caracteres inválidos.")
    if "://" not in s and re.match(r"^[\w-]+(\.[\w-]+)+([/?#]|$)", s):
        s = "https://" + s
    try:
        parts = urlsplit(s)
        host = parts.hostname
    except ValueError:
        raise ValueError("Esse link não parece válido.")
    if parts.scheme.lower() not in ("http", "https"):
        raise ValueError("Use um link que comece com http:// ou https://.")
    if not host:
        raise ValueError("O link está sem o endereço do site.")
    return s


def extract_urls(text: str):
    """Aceita vários links separados por espaço/linha. Retorna (urls, erros)."""
    urls, errors = [], []
    for token in re.split(r"\s+", (text or "").strip()):
        if not token:
            continue
        try:
            u = validate_url(token)
            if u not in urls:
                urls.append(u)
        except ValueError as exc:
            errors.append(str(exc))
    if not urls and not errors:
        errors.append("Cole um link para começar.")
    return urls, errors

# -------------------------------------------------------------- opções

@dataclass(frozen=True)
class Options:
    mode: str = "video"          # video | audio
    quality: str = "1080"        # ver QUALITIES
    audio_format: str = "mp3"    # ver AUDIO_FORMATS
    playlist: bool = False
    folder: str = ""
    cookies_browser: str = ""


def detect_js_runtimes():
    """O YouTube exige um interpretador JS externo (deno/node/bun) no yt-dlp."""
    return [r for r in ("deno", "node", "bun") if shutil.which(r)]


def build_args(url: str, opts: Options, js_runtimes=()):
    if opts.mode not in ("video", "audio") or opts.quality not in QUALITIES \
            or opts.audio_format not in AUDIO_FORMATS or opts.cookies_browser not in BROWSERS:
        raise ValueError("Opções inválidas.")
    url = validate_url(url)
    args = [
        "--ignore-config", "--newline", "-q", "--progress", "--no-simulate",
        "--no-warnings", "--socket-timeout", "30", "--retries", "10",
        "--fragment-retries", "10", "--concurrent-fragments", "4",
        "--embed-metadata", "--no-mtime",
        "--progress-template",
        "download:FLX|%(progress.status)s|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|"
        "%(progress.total_bytes_estimate)s|%(progress.speed)s|%(progress.eta)s|"
        "%(info.playlist_index)s|%(info.n_entries)s|%(info.title)s",
        "--progress-template", "postprocess:FLXPP|%(progress.status)s|%(progress.postprocessor)s",
        "--print", "after_move:FLXDONE|%(filepath)s",
        "-P", opts.folder,
    ]
    if opts.playlist:
        args += ["--yes-playlist", "-o",
                 "%(playlist_title,uploader|Playlist).100B/%(playlist_index)02d - %(title).150B.%(ext)s"]
    else:
        args += ["--no-playlist", "-o", "%(title).150B.%(ext)s"]
    if opts.mode == "audio":
        args += ["-f", "bestaudio/best", "-x", "--audio-format", opts.audio_format, "--audio-quality", "0"]
        if opts.audio_format in ("mp3", "m4a"):
            args += ["--embed-thumbnail", "--convert-thumbnails", "jpg"]
    else:
        sort = "res,vcodec:h264,acodec:aac,ext" if opts.quality == "best" \
            else f"res:{opts.quality},vcodec:h264,acodec:aac,ext"
        args += ["-S", sort]
    if opts.cookies_browser:
        args += ["--cookies-from-browser", opts.cookies_browser]
    for rt in js_runtimes:
        args += ["--js-runtimes", rt]
    return args + ["--", url]

# ----------------------------------------------------------------- job

_ids = itertools.count(1)


class Job:
    def __init__(self, url: str, opts: Options):
        self.id = next(_ids)
        self.url = url
        self.opts = opts
        self.reset()

    def reset(self):
        self.state = "queued"  # queued preparing downloading processing done error cancelled
        self.title = ""
        self.percent = 0.0
        self.speed = None
        self.eta = None
        self.index = None
        self.count = None
        self.part = 1
        self._last_bytes = 0
        self.message = ""
        self.filepath = ""
        self.files_done = 0
        self.heal_hint = False
        self.log = deque(maxlen=500)
        self.proc = None
        self.cancelled = False
        self._lock = threading.Lock()

    @property
    def active(self):
        return self.state in ("queued", "preparing", "downloading", "processing")

    def cancel(self):
        self.cancelled = True
        with self._lock:
            proc = self.proc
        if proc and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except OSError:
                pass
            threading.Timer(4.0, _force_kill, args=(proc,)).start()
        if self.state == "queued":
            self.state = "cancelled"


def _force_kill(proc):
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass

# ------------------------------------------------------------ parsing

def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


PP_NAMES = {
    "Merger": "Juntando vídeo e áudio…",
    "VideoConvertor": "Convertendo o vídeo…",
    "VideoRemuxer": "Ajustando o formato do vídeo…",
    "ExtractAudio": "Convertendo o áudio…",
    "EmbedThumbnail": "Adicionando a capa…",
    "Metadata": "Gravando título e artista…",
    "FFmpegMetadata": "Gravando título e artista…",
    "ThumbnailsConvertor": "Preparando a capa…",
    "MoveFiles": "Salvando o arquivo…",
}


def parse_line(job: Job, line: str) -> bool:
    """Atualiza o job a partir de uma linha do yt-dlp. True se algo mudou."""
    line = line.rstrip("\r\n")
    if not line:
        return False
    if line.startswith("FLX|"):
        p = line.split("|", 9)
        if len(p) < 10:
            return False
        status, done, total, est, speed, eta, idx, n, title = p[1:10]
        done_f, total_f = _num(done), _num(total) or _num(est)
        if done_f is not None and done_f + 1 < job._last_bytes:
            job.part += 1  # recomeçou: agora é o outro "pedaço" (ex.: áudio)
        job._last_bytes = done_f or 0
        if title and title != "NA":
            job.title = title
        job.index = int(idx) if idx.isdigit() else None
        job.count = int(n) if n.isdigit() else None
        pct = (done_f / total_f * 100.0) if (done_f is not None and total_f) else job.percent
        job.percent = max(0.0, min(100.0, pct))
        job.speed, job.eta = _num(speed), _num(eta)
        job.state = "downloading"
        if status == "finished":
            job.percent, job.speed, job.eta = 100.0, None, None
        return True
    if line.startswith("FLXPP|"):
        p = line.split("|", 2)
        if len(p) == 3 and p[1] == "started":
            job.state = "processing"
            job.message = PP_NAMES.get(p[2], "Finalizando o arquivo…")
            return True
        return False
    if line.startswith("FLXDONE|"):
        job.filepath = line.split("|", 1)[1]
        job.files_done += 1
        return True
    job.log.append(line)
    return False

# -------------------------------------------------------------- erros

ERROR_RULES = [
    # (trecho em minúsculas, mensagem, tentar atualizar o motor?)
    ("no such option", "O motor de download está desatualizado para esta versão do app.", True),
    ("ffmpeg not found", "O ffmpeg não está instalado. Instale o pacote “ffmpeg” e tente de novo.", False),
    ("ffprobe not found", "O ffmpeg não está instalado. Instale o pacote “ffmpeg” e tente de novo.", False),
    ("postprocessing: ffmpeg", "O ffmpeg não está instalado ou falhou. Instale o pacote “ffmpeg”.", False),
    ("no space left", "O disco está cheio. Libere espaço ou escolha outra pasta.", False),
    ("permission denied", "Sem permissão para salvar nessa pasta. Escolha outra pasta.", False),
    ("sign in to confirm", "O site pediu verificação/login. Em Configurações, escolha o navegador onde você está logado.", False),
    ("confirm your age", "Conteúdo com restrição de idade. Em Configurações, escolha o navegador onde você está logado.", False),
    ("login required", "Este conteúdo exige login. Em Configurações, escolha o navegador onde você está logado.", False),
    ("private video", "Este vídeo é privado.", False),
    ("members-only", "Conteúdo exclusivo para membros/assinantes.", False),
    ("not available in your country", "Este conteúdo não está disponível na sua região.", False),
    ("geo restrict", "Este conteúdo não está disponível na sua região.", False),
    ("video unavailable", "O vídeo não está mais disponível.", False),
    ("has been removed", "O vídeo foi removido.", False),
    ("http error 429", "O site limitou os pedidos (muitos acessos). Aguarde alguns minutos e tente de novo.", False),
    ("temporary failure in name resolution", "Sem internet. Verifique a conexão e tente de novo.", False),
    ("network is unreachable", "Sem internet. Verifique a conexão e tente de novo.", False),
    ("timed out", "A conexão demorou demais. Tente novamente.", False),
    ("unsupported url", "O site mudou ou este link não tem um vídeo compatível.", True),
    ("requested format is not available", "O formato pedido não está disponível (o site pode ter mudado).", True),
    ("http error 403", "O site bloqueou o acesso (provavelmente mudou de forma).", True),
    ("unable to extract", "Não consegui ler esta página (o site mudou).", True),
    ("nsig", "O YouTube mudou o sistema de proteção. Atualização necessária.", True),
    ("failed to extract", "Não consegui ler esta página (o site mudou).", True),
    ("javascript runtime", "Para o YouTube é preciso ter o Node.js instalado (pacote “nodejs”).", False),
]


def friendly_error(log_text: str, returncode=None):
    low = log_text.lower()
    for needle, msg, heal in ERROR_RULES:
        if needle in low:
            return msg, heal
    errs = [l for l in log_text.splitlines() if l.startswith("ERROR")]
    if errs:
        detail = re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*)?", "", errs[-1])[:160]
        return f"Não foi possível baixar: {detail}", True
    return f"O download terminou com erro (código {returncode}).", False

# ---------------------------------------------------------- formatação

def human_size(n):
    if n is None:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def fmt_eta(sec):
    if sec is None:
        return ""
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def status_text(job: Job) -> str:
    st = job.state
    if st == "queued":
        return "Na fila — começa em instantes…"
    if st == "preparing":
        return job.message or "Preparando e lendo as informações do link…"
    if st == "downloading":
        bits = []
        if job.count and job.count > 1:
            bits.append(f"Item {job.index or '?'} de {job.count}")
        bits.append(f"Baixando {job.percent:.0f}%" + (f" (parte {job.part})" if job.part > 1 else ""))
        if job.speed:
            bits.append(human_size(job.speed) + "/s")
        if job.eta is not None:
            bits.append(f"faltam {fmt_eta(job.eta)}")
        return " · ".join(bits)
    if st == "processing":
        return job.message or "Finalizando o arquivo…"
    if st == "done":
        name = os.path.basename(job.filepath) if job.filepath else ""
        extra = f" ({job.files_done} arquivos)" if job.files_done > 1 else ""
        return f"Concluído{extra}" + (f" — {name}" if name and job.files_done <= 1 else "")
    if st == "cancelled":
        return "Cancelado. Se tentar de novo, o download continua de onde parou."
    return job.message or "Ocorreu um erro."

# ----------------------------------------------------------- execução

def run_job(job: Job, cmd_prefix, on_update, js_runtimes=()):
    """Roda o yt-dlp para o job. Retorna 'done', 'error' ou 'cancelled'."""
    try:
        args = build_args(job.url, job.opts, js_runtimes)
    except ValueError as exc:
        job.state, job.message = "error", str(exc)
        return "error"
    os.makedirs(job.opts.folder, exist_ok=True)
    env = dict(os.environ, NO_COLOR="1", PYTHONIOENCODING="utf-8")
    job.state, job.message = "preparing", ""
    on_update(job)
    try:
        proc = subprocess.Popen(cmd_prefix + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                                errors="replace", bufsize=1, env=env, start_new_session=True)
    except OSError:
        job.state, job.message = "error", "Não consegui iniciar o yt-dlp neste sistema."
        return "error"
    with job._lock:
        job.proc = proc
    if job.cancelled:
        job.cancel()
    last_emit = 0.0
    for line in proc.stdout:
        if parse_line(job, line):
            now = time.monotonic()
            if now - last_emit > 0.15 or job.state == "processing" or job.speed is None:
                last_emit = now
                on_update(job)
    proc.stdout.close()
    proc.wait()
    with job._lock:
        job.proc = None
    if job.cancelled:
        job.state = "cancelled"
        return "cancelled"
    if proc.returncode == 0:
        job.state, job.percent = "done", 100.0
        return "done"
    text = "\n".join(job.log)
    job.message, job.heal_hint = friendly_error(text, proc.returncode)
    job.state = "error"
    return "error"
