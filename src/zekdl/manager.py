"""Orquestra fila de downloads, atualização automática e "autocura" do motor.

Não depende de GTK: a interface passa um `emit(evento, *args)` já seguro para
a thread da UI.
"""
import queue
import threading
import time

from .downloader import Job, Options, detect_js_runtimes, run_job
from .engine import Engine, EngineError

CHECK_INTERVAL = 6 * 3600  # no máximo uma checagem automática a cada 6 h


class Manager:
    def __init__(self, settings, engine: Engine, emit):
        self.settings = settings
        self.engine = engine
        self.emit = emit
        self.jobs = []
        self._q = queue.Queue()
        threading.Thread(target=self._worker, daemon=True, name="zek-download-worker").start()

    # ----------------------------------------------------------- motor
    def _engine_text(self):
        ver = self.engine.version()
        return f"yt-dlp {ver}" if ver else "yt-dlp não instalado"

    def _update_engine(self, silent_if_current=True, reason=""):
        """Atualiza o motor emitindo feedback. Retorna 'installed'|'updated'|'current'|'error'."""
        self.emit("engine", "busy", reason or "Verificando atualizações do motor de download…")

        def progress(done, total):
            if total:
                self.emit("engine", "busy", f"Baixando o motor de download… {done * 100 // total}%")

        try:
            result = self.engine.check_and_update(progress)
        except EngineError as exc:
            self.emit("engine", "error", str(exc))
            return "error"
        self.settings["last_check"] = time.time()
        self.settings.save()
        ver = self.engine.version(refresh=True) or "?"
        msgs = {
            "installed": f"Motor de download instalado (yt-dlp {ver}).",
            "updated": f"Motor de download atualizado para {ver}.",
            "current": f"Motor de download já está na versão mais recente ({ver}).",
        }
        self.emit("engine", "ok", msgs[result])
        return result

    def start(self):
        """Chamado ao abrir o app: instala o motor se faltar e confere atualização."""
        def run():
            self.engine.channel = self.settings["channel"]
            if not self.engine.installed():
                self._update_engine(reason="Preparando o motor de download (só na primeira vez)…")
            else:
                self.emit("engine", "ok", self._engine_text())
                if self.settings["auto_update"] and time.time() - self.settings["last_check"] > CHECK_INTERVAL:
                    self._update_engine()
        threading.Thread(target=run, daemon=True, name="zek-download-engine").start()

    def update_now(self):
        def run():
            self.engine.channel = self.settings["channel"]
            self._update_engine()
        threading.Thread(target=run, daemon=True, name="zek-download-update").start()

    # ------------------------------------------------------------ fila
    def add(self, url: str, opts: Options) -> Job:
        job = Job(url, opts)
        self.jobs.append(job)
        self._q.put(job)
        self.emit("job", job)
        return job

    def retry(self, job: Job):
        if job.active:
            return
        job.reset()
        self._q.put(job)
        self.emit("job", job)

    def cancel(self, job: Job):
        job.cancel()
        self.emit("job", job)

    def cancel_all(self):
        for j in self.jobs:
            if j.active:
                j.cancel()

    def has_active(self):
        return any(j.active for j in self.jobs)

    def forget(self, job: Job):
        if not job.active and job in self.jobs:
            self.jobs.remove(job)

    def _worker(self):
        while True:
            job = self._q.get()
            if job.state == "cancelled" or job.cancelled:
                job.state = "cancelled"
                self.emit("job", job)
                continue
            try:
                self._process(job)
            except Exception as exc:  # nunca derrubar o worker
                job.state, job.message = "error", f"Erro inesperado: {exc}"
            self.emit("job", job)

    def _process(self, job: Job):
        job.state, job.message = "preparing", ""
        self.emit("job", job)
        if not self.engine.command():
            job.message = "Baixando o motor de download pela primeira vez…"
            self.emit("job", job)
            if self._update_engine(reason="Preparando o motor de download…") == "error" or not self.engine.command():
                job.state = "error"
                job.message = "Não consegui obter o motor de download. Verifique a internet e tente de novo."
                return
        healed, no_js = False, False
        while True:
            runtimes = () if no_js else tuple(detect_js_runtimes())
            result = run_job(job, self.engine.command(), lambda j: self.emit("job", j), runtimes)
            if result != "error":
                break
            log = "\n".join(job.log).lower()
            if runtimes and "no such option" in log and "js-runtimes" in log:
                no_js = True
                job.log.clear()
                continue
            if job.heal_hint and not healed:
                # "Autocura": o site provavelmente mudou -> atualiza o motor e tenta de novo.
                healed = True
                original = job.message
                job.state, job.message = "preparing", "O site parece ter mudado — atualizando o motor e tentando de novo…"
                self.emit("job", job)
                if self._update_engine(reason="Um site mudou: procurando correção do yt-dlp…") == "updated":
                    job.log.clear()
                    job.percent, job.part, job._last_bytes, job.files_done = 0.0, 1, 0, 0
                    continue
                job.state = "error"
                job.message = original
                if self.settings["channel"] == "stable":
                    job.message += " (O motor já está atualizado. Se persistir, ative o canal “Nightly” em Configurações.)"
            break
