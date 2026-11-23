"""Interface gráfica do Zek Download (GTK 3)."""
import os
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from . import APP_ID, APP_NAME, __version__  # noqa: E402
from .downloader import (AUDIO_FORMATS, BROWSERS, QUALITIES, Options,  # noqa: E402
                         extract_urls, status_text)
from .engine import Engine  # noqa: E402
from .manager import Manager  # noqa: E402
from .settings import Settings, data_dir  # noqa: E402
from .style import CSS  # noqa: E402

QUALITY_LABELS = {
    "best": "Melhor disponível", "2160": "4K (2160p)", "1440": "2K (1440p)",
    "1080": "Full HD (1080p)", "720": "HD (720p)", "480": "480p", "360": "360p",
}
AUDIO_LABELS = {
    "mp3": "MP3 — funciona em tudo", "m4a": "M4A (AAC) — ótima qualidade",
    "opus": "Opus — arquivo menor", "flac": "FLAC — sem perdas (arquivo grande)",
}
BROWSER_LABELS = {
    "": "Nenhum (padrão)", "firefox": "Firefox", "chrome": "Google Chrome", "chromium": "Chromium",
    "brave": "Brave", "edge": "Microsoft Edge", "opera": "Opera", "vivaldi": "Vivaldi",
}


def ui_call(fn, *args):
    """Executa fn(*args) na thread da interface (seguro chamar de qualquer thread)."""
    def run():
        fn(*args)
        return False
    GLib.idle_add(run)


def css_class(widget, *names):
    ctx = widget.get_style_context()
    for n in names:
        ctx.add_class(n)
    return widget


def label(text="", css=None, xalign=0.0, wrap=False, selectable=False):
    lb = Gtk.Label(label=text)
    lb.set_xalign(xalign)
    if wrap:
        lb.set_line_wrap(True)
        lb.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    lb.set_selectable(selectable)
    if css:
        css_class(lb, css)
    return lb


def open_uri(uri):
    try:
        Gio.AppInfo.launch_default_for_uri(uri, None)
    except GLib.Error:
        pass


def icon_button(icon, tip, callback):
    b = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
    b.set_relief(Gtk.ReliefStyle.NONE)
    b.set_tooltip_text(tip)
    b.set_valign(Gtk.Align.CENTER)
    css_class(b, "fx-icon")
    b.connect("clicked", lambda *_: callback())
    b.set_no_show_all(True)
    return b


# ===================================================================== linha

class JobRow(Gtk.ListBoxRow):
    def __init__(self, job, win):
        super().__init__()
        self.job, self.win = job, win
        self.last_state = None
        self._pulse_id = 0
        self.set_selectable(False)
        self.set_activatable(False)
        css_class(self, "fx-row")

        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        outer.set_border_width(14)
        self.add(outer)

        badge = css_class(Gtk.Box(), "fx-icon-badge")
        badge.set_size_request(46, 46)
        badge.set_valign(Gtk.Align.CENTER)
        icon_name = "audio-x-generic-symbolic" if job.opts.mode == "audio" else "video-x-generic-symbolic"
        self.icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.LARGE_TOOLBAR)
        self.icon.set_hexpand(True)
        badge.pack_start(self.icon, True, True, 0)
        outer.pack_start(badge, False, False, 0)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        col.set_hexpand(True)
        self.title = css_class(label("", wrap=False), "fx-row-title")
        self.title.set_ellipsize(Pango.EllipsizeMode.END)
        self.bar = css_class(Gtk.ProgressBar(), "fx-progress")
        self.status = css_class(label("", wrap=True), "fx-row-status")
        col.pack_start(self.title, False, False, 0)
        col.pack_start(self.bar, False, False, 0)
        col.pack_start(self.status, False, False, 0)
        outer.pack_start(col, True, True, 0)

        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        btns.set_valign(Gtk.Align.CENTER)
        self.b_play = icon_button("media-playback-start-symbolic", "Abrir o arquivo", self.open_file)
        self.b_folder = icon_button("folder-open-symbolic", "Mostrar na pasta", self.open_folder)
        self.b_retry = icon_button("view-refresh-symbolic", "Tentar de novo", lambda: win.manager.retry(job))
        self.b_details = icon_button("dialog-information-symbolic", "Ver detalhes técnicos", self.show_details)
        self.b_cancel = icon_button("window-close-symbolic", "Cancelar", lambda: win.manager.cancel(job))
        for b in (self.b_play, self.b_folder, self.b_retry, self.b_details, self.b_cancel):
            btns.pack_start(b, False, False, 0)
        outer.pack_start(btns, False, False, 0)

        self.connect("destroy", lambda *_: self._stop_pulse())
        self.show_all()
        self.refresh()

    # -- ações
    def open_file(self):
        if self.job.filepath and os.path.exists(self.job.filepath):
            open_uri(Gio.File.new_for_path(self.job.filepath).get_uri())
        else:
            self.open_folder()

    def open_folder(self):
        path = os.path.dirname(self.job.filepath) if self.job.filepath else self.job.opts.folder
        if not os.path.isdir(path):
            path = self.job.opts.folder
        open_uri(Gio.File.new_for_path(path).get_uri())

    def show_details(self):
        DetailsDialog(self.win, self.job).run_and_close()

    # -- animação de "trabalhando…"
    def _start_pulse(self):
        if not self._pulse_id:
            def tick():
                self.bar.pulse()
                return self.job.state in ("preparing", "processing")
            self._pulse_id = GLib.timeout_add(110, lambda: self._tick(tick))

    def _tick(self, fn):
        keep = fn()
        if not keep:
            self._pulse_id = 0
        return keep

    def _stop_pulse(self):
        if self._pulse_id:
            GLib.source_remove(self._pulse_id)
            self._pulse_id = 0

    def refresh(self):
        j, st = self.job, self.job.state
        shown = j.title or j.url
        self.title.set_text(shown)
        self.title.set_tooltip_text(shown)
        text = status_text(j)
        self.status.set_text(text)
        self.status.set_tooltip_text(text)

        ctx = self.get_style_context()
        ctx.remove_class("fx-done")
        ctx.remove_class("fx-error")
        if st == "done":
            ctx.add_class("fx-done")
        elif st == "error":
            ctx.add_class("fx-error")

        if st in ("preparing", "processing"):
            self._start_pulse()
        else:
            self._stop_pulse()
            self.bar.set_fraction(0.0 if st == "queued" else max(0.0, min(1.0, j.percent / 100.0)))

        self.b_cancel.set_visible(j.active)
        self.b_retry.set_visible(st in ("error", "cancelled"))
        self.b_play.set_visible(st == "done")
        self.b_folder.set_visible(st == "done")
        self.b_details.set_visible(st == "error")


# ================================================================== diálogos

class DetailsDialog(Gtk.Dialog):
    def __init__(self, parent, job):
        super().__init__(title="Detalhes técnicos", transient_for=parent, modal=True)
        self.set_default_size(640, 380)
        self.add_button("Copiar", Gtk.ResponseType.APPLY)
        self.add_button("Fechar", Gtk.ResponseType.CLOSE)
        box = self.get_content_area()
        box.set_border_width(14)
        box.set_spacing(8)
        box.pack_start(label("Mensagem do yt-dlp (útil para pedir ajuda ou reportar um problema):", wrap=True),
                       False, False, 0)
        self.text = "Link: " + job.url + "\n\n" + ("\n".join(job.log) or "(sem detalhes adicionais)")
        view = Gtk.TextView()
        view.set_editable(False)
        view.set_monospace(True)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.get_buffer().set_text(self.text)
        sw = Gtk.ScrolledWindow()
        sw.set_shadow_type(Gtk.ShadowType.IN)
        sw.set_vexpand(True)
        sw.add(view)
        box.pack_start(sw, True, True, 0)
        self.show_all()

    def run_and_close(self):
        while True:
            resp = self.run()
            if resp == Gtk.ResponseType.APPLY:
                Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(self.text, -1)
                continue
            break
        self.destroy()


class SettingsDialog(Gtk.Dialog):
    def __init__(self, parent, settings):
        super().__init__(title="Configurações", transient_for=parent, modal=True)
        self.settings = settings
        self.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        self.add_button("Salvar", Gtk.ResponseType.OK)
        grid = Gtk.Grid(column_spacing=16, row_spacing=14)
        grid.set_border_width(20)
        self.get_content_area().add(grid)

        def add(row, title, widget, help_text):
            t = label(title, "fx-h2")
            t.set_valign(Gtk.Align.START)
            grid.attach(t, 0, row, 1, 1)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            widget.set_halign(Gtk.Align.START)
            box.pack_start(widget, False, False, 0)
            box.pack_start(css_class(label(help_text, wrap=True), "fx-hint"), False, False, 0)
            box.set_size_request(380, -1)
            grid.attach(box, 1, row, 1, 1)

        self.folder = Gtk.FileChooserButton.new("Escolha a pasta", Gtk.FileChooserAction.SELECT_FOLDER)
        if os.path.isdir(settings["folder"]):
            self.folder.set_filename(settings["folder"])
        add(0, "Pasta de downloads", self.folder, "Onde os vídeos e músicas serão salvos.")

        self.cookies = Gtk.ComboBoxText()
        for b in BROWSERS:
            self.cookies.append(b or "none", BROWSER_LABELS[b])
        self.cookies.set_active_id(settings["cookies_browser"] or "none")
        add(1, "Usar login do navegador", self.cookies,
            "Só se o site pedir login ou confirmação de idade. O Zek Download lê os cookies do navegador escolhido "
            "apenas durante o download e não os guarda.")

        self.auto = Gtk.Switch()
        self.auto.set_active(settings["auto_update"])
        add(2, "Atualizar o motor sozinho", self.auto,
            "Confere a cada poucas horas se há uma versão nova do yt-dlp. Recomendado: é o que mantém o "
            "Zek Download funcionando quando os sites mudam.")

        self.channel = Gtk.ComboBoxText()
        self.channel.append("stable", "Estável (recomendado)")
        self.channel.append("nightly", "Nightly — correções chegam primeiro")
        self.channel.set_active_id(settings["channel"])
        add(3, "Canal de atualização", self.channel,
            "O canal Nightly recebe as correções dias antes, mas pode ter mais imprevistos.")
        self.show_all()

    def apply(self):
        folder = self.folder.get_filename()
        if folder:
            self.settings["folder"] = folder
        self.settings["cookies_browser"] = "" if self.cookies.get_active_id() == "none" else self.cookies.get_active_id()
        self.settings["auto_update"] = self.auto.get_active()
        self.settings["channel"] = self.channel.get_active_id() or "stable"
        self.settings.save()


# ===================================================================== janela

class ZekWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=APP_NAME)
        self.set_default_size(920, 720)
        self.set_size_request(760, 580)
        css_class(self, "fx-window")
        self.settings = Settings()
        self.engine = Engine(data_dir(), self.settings["channel"])
        self.rows = {}
        self._last_clip = ""
        self._banner_timer = 0
        self._mode_guard = False
        self.manager = Manager(self.settings, self.engine, lambda *a: ui_call(self.on_event, *a))

        self._build_header()
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_border_width(22)
        root.pack_start(content, True, True, 0)
        self._build_banner(content)
        self._build_card(content)
        self._build_list_area(content)
        self._build_footer(root)

        self.connect("delete-event", self.on_delete)
        self.connect("notify::is-active", self.on_active)
        self.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.drag_dest_add_text_targets()
        self.connect("drag-data-received", self.on_drop)

        self._sync_mode_ui()
        self.show_all()
        self.banner_rev.set_reveal_child(False)
        self.entry.grab_focus()
        self.manager.start()

    # ------------------------------------------------------------ montagem
    def _build_header(self):
        hb = css_class(Gtk.HeaderBar(), "fx-header")
        hb.set_show_close_button(True)
        hb.set_title(APP_NAME)
        hb.set_subtitle("Vídeos e músicas, de qualquer site")
        menu = Gio.Menu()
        menu.append("Configurações", "app.settings")
        menu.append("Verificar atualização do motor", "app.update")
        menu.append("Sobre o Zek Download", "app.about")
        menu.append("Sair", "app.quit")
        mb = Gtk.MenuButton()
        mb.set_menu_model(menu)
        mb.set_image(Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON))
        hb.pack_end(mb)
        self.set_titlebar(hb)

    def _build_banner(self, parent):
        self.banner_rev = Gtk.Revealer()
        self.banner_rev.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        box = css_class(Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12), "fx-banner")
        box.set_border_width(12)
        self.spinner = Gtk.Spinner()
        self.banner_lbl = label("", wrap=True)
        box.pack_start(self.spinner, False, False, 0)
        box.pack_start(self.banner_lbl, True, True, 0)
        self.banner_rev.add(box)
        parent.pack_start(self.banner_rev, False, False, 0)

    def _build_card(self, parent):
        card = css_class(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14), "fx-card")
        card.set_border_width(20)
        parent.pack_start(card, False, False, 0)
        card.pack_start(label("Novo download", "fx-h1"), False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.entry = css_class(Gtk.Entry(), "fx-entry")
        self.entry.set_hexpand(True)
        self.entry.set_placeholder_text("Cole aqui o link do vídeo ou da música (YouTube, SoundCloud, Vimeo, X…)")
        self.entry.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "insert-link-symbolic")
        self.entry.connect("activate", self.on_download)
        paste = css_class(Gtk.Button(label="Colar"), "fx-secondary")
        paste.connect("clicked", self.on_paste)
        self.go_btn = css_class(Gtk.Button(label="Baixar"), "fx-primary")
        self.go_btn.connect("clicked", self.on_download)
        row.pack_start(self.entry, True, True, 0)
        row.pack_start(paste, False, False, 0)
        row.pack_start(self.go_btn, False, False, 0)
        card.pack_start(row, False, False, 0)

        opts = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        seg = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.btn_video = css_class(Gtk.ToggleButton(label="Vídeo"), "fx-seg", "fx-seg-left")
        self.btn_audio = css_class(Gtk.ToggleButton(label="Áudio"), "fx-seg", "fx-seg-right")
        self.btn_video.connect("toggled", self.on_mode_toggled, "video")
        self.btn_audio.connect("toggled", self.on_mode_toggled, "audio")
        seg.pack_start(self.btn_video, False, False, 0)
        seg.pack_start(self.btn_audio, False, False, 0)
        opts.pack_start(seg, False, False, 0)

        self.opt_stack = Gtk.Stack()
        self.q_combo = css_class(Gtk.ComboBoxText(), "fx-combo")
        for q in QUALITIES:
            self.q_combo.append(q, QUALITY_LABELS[q])
        self.q_combo.set_active_id(self.settings["quality"])
        self.q_combo.connect("changed", self.on_opts_changed)
        self.a_combo = css_class(Gtk.ComboBoxText(), "fx-combo")
        for f in AUDIO_FORMATS:
            self.a_combo.append(f, AUDIO_LABELS[f])
        self.a_combo.set_active_id(self.settings["audio_format"])
        self.a_combo.connect("changed", self.on_opts_changed)
        self.opt_stack.add_named(self.q_combo, "video")
        self.opt_stack.add_named(self.a_combo, "audio")
        opts.pack_start(self.opt_stack, False, False, 0)

        self.playlist = css_class(Gtk.CheckButton(label="Baixar a playlist inteira"), "fx-check")
        self.playlist.set_active(self.settings["playlist"])
        self.playlist.connect("toggled", self.on_opts_changed)
        opts.pack_start(self.playlist, False, False, 6)
        card.pack_start(opts, False, False, 0)

        frow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        frow.pack_start(label("Salvar em", "fx-dim"), False, False, 0)
        self.folder_btn = css_class(Gtk.FileChooserButton.new("Escolha a pasta", Gtk.FileChooserAction.SELECT_FOLDER), "fx-file")
        os.makedirs(self.settings["folder"], exist_ok=True)
        self.folder_btn.set_filename(self.settings["folder"])
        self.folder_btn.connect("file-set", self.on_folder_set)
        frow.pack_start(self.folder_btn, True, True, 0)
        card.pack_start(frow, False, False, 0)

        self.hint = css_class(label("", wrap=True), "fx-hint")
        card.pack_start(self.hint, False, False, 0)

    def _build_list_area(self, parent):
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        parent.pack_start(self.stack, True, True, 0)

        # --- tela inicial: "como funciona"
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        empty.pack_start(label("Como funciona", "fx-h1"), False, False, 0)
        steps = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        steps.set_homogeneous(True)
        data = [
            ("1", "Cole o link", "Copie o endereço do vídeo ou da música em qualquer site e cole no campo acima."),
            ("2", "Escolha o formato", "Vídeo na qualidade que quiser, ou só o áudio em MP3, M4A, Opus ou FLAC."),
            ("3", "Clique em Baixar", "O progresso aparece aqui. Quando acabar, abra o arquivo ou a pasta com um clique."),
        ]
        for num, title, text in data:
            c = css_class(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8), "fx-step-card")
            c.set_border_width(16)
            n = css_class(label(num, xalign=0.5), "fx-step-num")
            n.set_halign(Gtk.Align.START)
            c.pack_start(n, False, False, 0)
            c.pack_start(label(title, "fx-h2"), False, False, 0)
            c.pack_start(css_class(label(text, wrap=True), "fx-text"), False, False, 0)
            steps.pack_start(c, True, True, 0)
        empty.pack_start(steps, False, False, 0)
        empty.pack_start(css_class(label(
            "Dica: você pode arrastar um link para esta janela, colar vários links de uma vez (separados por espaço "
            "ou linha) e acompanhar tudo na fila. O Zek Download atualiza sozinho o motor de download (yt-dlp), então "
            "continua funcionando quando os sites mudam.", wrap=True), "fx-hint"), False, False, 0)
        self.stack.add_named(empty, "empty")

        # --- lista de downloads
        lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        head.pack_start(label("Downloads", "fx-h1"), False, False, 0)
        clear = css_class(Gtk.Button(label="Limpar finalizados"), "fx-secondary")
        clear.connect("clicked", self.on_clear)
        head.pack_end(clear, False, False, 0)
        lst.pack_start(head, False, False, 0)
        self.listbox = css_class(Gtk.ListBox(), "fx-list")
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.add(self.listbox)
        lst.pack_start(sw, True, True, 0)
        self.stack.add_named(lst, "list")
        self.stack.set_visible_child_name("empty")

    def _build_footer(self, parent):
        foot = css_class(Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8), "fx-footer")
        foot.set_border_width(10)
        self.status_lbl = label("Pronto. Cole um link acima para começar.")
        self.status_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        foot.pack_start(self.status_lbl, True, True, 8)
        self.dot = css_class(label("●"), "fx-dot-busy")
        self.engine_lbl = label("yt-dlp: verificando…")
        foot.pack_end(self.engine_lbl, False, False, 8)
        foot.pack_end(self.dot, False, False, 0)
        parent.pack_start(foot, False, False, 0)
        if self.engine.installed():
            self._set_dot("fx-dot-ok")
            self.engine_lbl.set_text("yt-dlp instalado")
        else:
            self._set_dot("fx-dot-busy")
            self.engine_lbl.set_text("yt-dlp: ainda não instalado")

    # ------------------------------------------------------------- helpers
    def _set_dot(self, cls):
        ctx = self.dot.get_style_context()
        for c in ("fx-dot-ok", "fx-dot-busy", "fx-dot-err"):
            ctx.remove_class(c)
        ctx.add_class(cls)

    def set_status(self, text):
        self.status_lbl.set_text(text)

    def show_banner(self, text, busy=True, hide_after=0):
        if self._banner_timer:
            GLib.source_remove(self._banner_timer)
            self._banner_timer = 0
        self.banner_lbl.set_text(text)
        if busy:
            self.spinner.start()
            self.spinner.show()
        else:
            self.spinner.stop()
            self.spinner.hide()
        self.banner_rev.set_reveal_child(True)
        if hide_after:
            def hide():
                self.banner_rev.set_reveal_child(False)
                self._banner_timer = 0
                return False
            self._banner_timer = GLib.timeout_add_seconds(hide_after, hide)

    def current_mode(self):
        return "audio" if self.btn_audio.get_active() else "video"

    def _sync_mode_ui(self):
        self._mode_guard = True
        self.btn_video.set_active(self.settings["mode"] == "video")
        self.btn_audio.set_active(self.settings["mode"] == "audio")
        self._mode_guard = False
        self._update_hint()

    def _update_hint(self):
        mode = self.current_mode()
        self.opt_stack.set_visible_child_name(mode)
        if mode == "video":
            q = self.q_combo.get_active_id() or "1080"
            qual = "na melhor qualidade disponível" if q == "best" else f"em até {QUALITY_LABELS[q]}"
            txt = f"Vídeo {qual}, com som. Salvo em MP4 quando o site permite (ou MKV)."
        else:
            f = (self.a_combo.get_active_id() or "mp3").upper()
            txt = f"Somente o áudio, em {f}, na melhor qualidade. Inclui capa e dados da música quando o site oferece."
        if self.playlist.get_active():
            txt += " Se o link for de uma playlist, todos os itens entram na fila (numerados, em uma pasta)."
        else:
            txt += " Se o link for de uma playlist, só o item indicado será baixado."
        self.hint.set_text(txt)

    def build_options(self):
        return Options(
            mode=self.current_mode(), quality=self.q_combo.get_active_id() or "1080",
            audio_format=self.a_combo.get_active_id() or "mp3", playlist=self.playlist.get_active(),
            folder=self.folder_btn.get_filename() or self.settings["folder"],
            cookies_browser=self.settings["cookies_browser"])

    # ------------------------------------------------------------- eventos UI
    def on_mode_toggled(self, btn, mode):
        if self._mode_guard:
            return
        self._mode_guard = True
        other = self.btn_audio if mode == "video" else self.btn_video
        if btn.get_active():
            other.set_active(False)
        elif not other.get_active():
            btn.set_active(True)  # nunca deixar os dois desligados
        self._mode_guard = False
        self.settings["mode"] = self.current_mode()
        self.settings.save()
        self._update_hint()

    def on_opts_changed(self, *_):
        self.settings["quality"] = self.q_combo.get_active_id() or "1080"
        self.settings["audio_format"] = self.a_combo.get_active_id() or "mp3"
        self.settings["playlist"] = self.playlist.get_active()
        self.settings.save()
        self._update_hint()

    def on_folder_set(self, btn):
        folder = btn.get_filename()
        if folder:
            self.settings["folder"] = folder
            self.settings.save()
            self.set_status(f"Os próximos downloads serão salvos em: {folder}")

    def on_paste(self, *_):
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).request_text(self._paste_cb, True)

    def _paste_cb(self, clipboard, text, manual):
        if text and text.strip():
            self.entry.set_text(text.strip())
            self.entry.grab_focus()
            self.set_status("Link colado. Escolha o formato e clique em Baixar.")
        elif manual:
            self.set_status("A área de transferência está vazia. Copie um link primeiro.")

    def on_active(self, *_):
        if self.is_active() and not self.entry.get_text():
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).request_text(self._auto_clip_cb)

    def _auto_clip_cb(self, clipboard, text):
        t = (text or "").strip()
        if t and t != self._last_clip and t.lower().startswith(("http://", "https://")) \
                and not self.entry.get_text() and extract_urls(t)[0]:
            self._last_clip = t
            self.entry.set_text(t)
            self.set_status("Detectei um link na área de transferência e já colei para você. Clique em Baixar.")

    def on_drop(self, widget, ctx, x, y, data, info, time):
        text = data.get_text()
        if text and text.strip():
            self.set_entry_text(text.strip())
        Gtk.drag_finish(ctx, True, False, time)

    def set_entry_text(self, text):
        self.entry.set_text(text)
        self.entry.grab_focus()
        self.set_status("Link recebido. Escolha o formato e clique em Baixar.")

    def on_download(self, *_):
        urls, errors = extract_urls(self.entry.get_text())
        if not urls:
            self.set_status("⚠ " + (errors[0] if errors else "Cole um link para começar."))
            self.entry.grab_focus()
            return
        opts = self.build_options()
        try:
            os.makedirs(opts.folder, exist_ok=True)
        except OSError:
            self.set_status("⚠ Não consegui criar/usar a pasta de destino. Escolha outra pasta.")
            return
        for u in urls:
            self.manager.add(u, opts)
        self.entry.set_text("")
        msg = f"{len(urls)} link(s) adicionado(s) à fila."
        if errors:
            msg += f" {len(errors)} item(ns) inválido(s) ignorado(s)."
        self.set_status(msg)

    def on_clear(self, *_):
        for jid, row in list(self.rows.items()):
            if not row.job.active:
                self.listbox.remove(row)
                self.manager.forget(row.job)
                del self.rows[jid]
        if not self.rows:
            self.stack.set_visible_child_name("empty")

    def on_delete(self, *_):
        if self.manager.has_active():
            dlg = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
                                    buttons=Gtk.ButtonsType.NONE, text="Há downloads em andamento")
            dlg.format_secondary_text("Se você sair agora, eles serão cancelados. Depois, ao tentar de novo, "
                                      "o download continua de onde parou.")
            dlg.add_button("Continuar baixando", Gtk.ResponseType.CANCEL)
            dlg.add_button("Sair e cancelar", Gtk.ResponseType.OK)
            resp = dlg.run()
            dlg.destroy()
            if resp != Gtk.ResponseType.OK:
                return True
            self.manager.cancel_all()
        return False

    # ---------------------------------------------------- eventos do Manager
    def on_event(self, kind, *args):
        if kind == "job":
            self.on_job(args[0])
        elif kind == "engine":
            self.on_engine(*args)

    def on_job(self, job):
        row = self.rows.get(job.id)
        if row is None:
            row = JobRow(job, self)
            self.rows[job.id] = row
            self.listbox.insert(row, 0)
            self.stack.set_visible_child_name("list")
        prev = row.last_state
        row.last_state = job.state
        row.refresh()
        active = sum(1 for r in self.rows.values() if r.job.active)
        if job.state != prev:
            if job.state == "done":
                self.set_status(f"✔ Concluído: {job.title or job.url}")
                self._notify(job, "Download concluído", job.title or job.url)
            elif job.state == "error":
                self.set_status("✖ Falhou: " + (job.title or job.url) + " — veja a mensagem no item.")
                self._notify(job, "O download falhou", job.message)
            elif job.state == "cancelled":
                self.set_status("Download cancelado.")
            elif job.state == "downloading" and prev in (None, "queued", "preparing"):
                self.set_status(f"Baixando… ({active} na fila/em andamento)")

    def _notify(self, job, title, body):
        if self.is_active():
            return
        try:
            n = Gio.Notification.new(title)
            n.set_body(body[:200])
            self.get_application().send_notification(f"job-{job.id}", n)
        except Exception:
            pass

    def on_engine(self, state, text):
        if state == "busy":
            self.show_banner(text, busy=True)
            self._set_dot("fx-dot-busy")
            self.engine_lbl.set_text("yt-dlp: atualizando…")
        elif state == "ok":
            ver = self.engine._version
            self.engine_lbl.set_text(f"yt-dlp {ver}" if ver else "yt-dlp pronto")
            self._set_dot("fx-dot-ok")
            if text.startswith("Motor"):
                self.show_banner("✔ " + text, busy=False, hide_after=6)
                self.set_status(text)
            else:
                self.banner_rev.set_reveal_child(False)
        else:
            self._set_dot("fx-dot-err")
            self.engine_lbl.set_text("yt-dlp: sem atualização")
            self.show_banner("⚠ " + text, busy=False, hide_after=12)
            self.set_status(text)


# ================================================================ aplicação

class ZekApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.win = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)
        Gtk.Window.set_default_icon_name(APP_ID)
        prov = Gtk.CssProvider()
        try:
            prov.load_from_data(CSS)
        except GLib.Error:
            pass  # um trecho de CSS recusado pelo GTK não deve impedir o app de abrir
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        for name, cb in (("settings", self.on_settings), ("update", self.on_update),
                         ("about", self.on_about), ("quit", lambda *_: self.on_quit())):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", cb)
            self.add_action(act)
        self.set_accels_for_action("app.quit", ["<Primary>q"])
        self.set_accels_for_action("app.settings", ["<Primary>comma"])

    def _window(self):
        if self.win is None:
            self.win = ZekWindow(self)
        return self.win

    def do_activate(self):
        self._window().present()

    def do_open(self, files, n_files, hint):
        win = self._window()
        uris = [f.get_uri() for f in files if f.get_uri() and f.get_uri().lower().startswith(("http://", "https://"))]
        win.present()
        if uris:
            win.set_entry_text(" ".join(uris))

    def on_settings(self, *_):
        win = self._window()
        dlg = SettingsDialog(win, win.settings)
        if dlg.run() == Gtk.ResponseType.OK:
            dlg.apply()
            win.engine.channel = win.settings["channel"]
            if win.settings["folder"] and os.path.isdir(win.settings["folder"]):
                win.folder_btn.set_filename(win.settings["folder"])
            win.set_status("Configurações salvas.")
        dlg.destroy()

    def on_update(self, *_):
        win = self._window()
        win.manager.update_now()

    def on_about(self, *_):
        dlg = Gtk.AboutDialog(transient_for=self._window(), modal=True)
        dlg.set_program_name(APP_NAME)
        dlg.set_version(__version__)
        dlg.set_logo_icon_name(APP_ID)
        dlg.set_comments("Baixe vídeos e músicas de vários sites.\nUsa o yt-dlp, que o Zek Download mantém atualizado "
                         "sozinho (com verificação SHA-256).")
        dlg.set_website("https://github.com/aaaiiicerol")
        dlg.set_license_type(Gtk.License.MIT_X11)
        dlg.set_authors(["aaaiiicerol"])
        dlg.run()
        dlg.destroy()

    def on_quit(self):
        if self.win is not None:
            self.win.close()
        else:
            self.quit()


def main():
    GLib.set_prgname(APP_ID)
    GLib.set_application_name(APP_NAME)
    return ZekApp().run(sys.argv)
