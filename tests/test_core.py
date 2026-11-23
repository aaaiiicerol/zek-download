import hashlib
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from zekdl import downloader as dl            # noqa: E402
from zekdl.engine import Engine, EngineError, parse_sums, primary_asset  # noqa: E402
from zekdl.manager import Manager             # noqa: E402
from zekdl.settings import Settings           # noqa: E402

FAKE_V1 = """#!/usr/bin/env python3
import sys
if "--version" in sys.argv:
    print("2025.01.01"); sys.exit(0)
sys.stderr.write("ERROR: [generic] Unsupported URL: x\\n"); sys.exit(1)
"""

FAKE_V2 = """#!/usr/bin/env python3
import sys, os
if "--version" in sys.argv:
    print("2025.02.02"); sys.exit(0)
folder = sys.argv[sys.argv.index("-P") + 1]
print("FLX|downloading|1000|10000|NA|500|18|NA|NA|Meu | Titulo", flush=True)
print("FLX|downloading|10000|10000|NA|900|0|NA|NA|Meu | Titulo", flush=True)
print("FLX|finished|10000|10000|NA|NA|NA|NA|NA|Meu | Titulo", flush=True)
print("FLXPP|started|Merger", flush=True)
out = os.path.join(folder, "Meu | Titulo.mp4")
open(out, "w").write("x")
print("FLXDONE|" + out, flush=True)
"""


class FakeResp:
    def __init__(self, data):
        self.data, self.pos = data, 0
        self.headers = {"Content-Length": str(len(data))}

    def read(self, n=-1):
        if n is None or n < 0:
            n = len(self.data)
        chunk = self.data[self.pos:self.pos + n]
        self.pos += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    """Simula o GitHub: serve SHA2-256SUMS e o binário."""
    def __init__(self):
        self.files, self.sums_override = {}, None
        self.requested = []

    def publish(self, content: str):
        asset = primary_asset()
        data = content.encode()
        self.files[asset] = data
        self.sums = f"{hashlib.sha256(data).hexdigest()}  {asset}\n"

    def open(self, req, timeout=0):
        url = req.full_url
        self.requested.append(url)
        name = url.rsplit("/", 1)[1]
        if name == "SHA2-256SUMS":
            return FakeResp((self.sums_override or self.sums).encode())
        if name in self.files:
            return FakeResp(self.files[name])
        raise urllib.error.HTTPError(url, 404, "nf", {}, None)


class UrlTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(dl.validate_url(" https://youtu.be/abc "), "https://youtu.be/abc")
        self.assertEqual(dl.validate_url("youtube.com/watch?v=1"), "https://youtube.com/watch?v=1")

    def test_invalid(self):
        for bad in ["", "   ", "--exec=rm -rf ~", "file:///etc/passwd", "javascript:alert(1)",
                    "ftp://x.com/a", "https://", "http://a.com/ b", "-o /etc/x", "https://a.com/\x00"]:
            with self.assertRaises(ValueError, msg=bad):
                dl.validate_url(bad)

    def test_extract_many(self):
        urls, errs = dl.extract_urls("https://a.com/1\nhttps://a.com/1 https://b.com/2 lixo://x")
        self.assertEqual(urls, ["https://a.com/1", "https://b.com/2"])
        self.assertEqual(len(errs), 1)


class ArgsTests(unittest.TestCase):
    def test_url_after_double_dash_and_no_shell_options(self):
        a = dl.build_args("https://a.com/v", dl.Options(folder="/tmp/x"), ["node"])
        self.assertEqual(a[-2:], ["--", "https://a.com/v"])
        self.assertIn("--ignore-config", a)
        self.assertNotIn("--exec", a)
        self.assertIn("--no-playlist", a)

    def test_audio(self):
        a = dl.build_args("https://a.com/v", dl.Options(mode="audio", audio_format="mp3", folder="/t"))
        self.assertIn("-x", a)
        self.assertIn("mp3", a)

    def test_bad_options(self):
        with self.assertRaises(ValueError):
            dl.build_args("https://a.com", dl.Options(quality="9999", folder="/t"))
        with self.assertRaises(ValueError):
            dl.build_args("https://a.com", dl.Options(cookies_browser="--exec", folder="/t"))


class ParseTests(unittest.TestCase):
    def test_progress_and_title_with_pipe(self):
        j = dl.Job("https://a.com", dl.Options(folder="/t"))
        dl.parse_line(j, "FLX|downloading|2500|10000|NA|1048576|7|NA|NA|A | B")
        self.assertEqual(j.title, "A | B")
        self.assertAlmostEqual(j.percent, 25.0)
        self.assertIn("25%", dl.status_text(j))
        self.assertIn("1.0 MB/s", dl.status_text(j))
        dl.parse_line(j, "FLX|downloading|100|5000|NA|10|1|NA|NA|A | B")
        self.assertEqual(j.part, 2)

    def test_estimate_and_playlist(self):
        j = dl.Job("https://a.com", dl.Options(folder="/t"))
        dl.parse_line(j, "FLX|downloading|500|NA|1000|NA|NA|3|12|T")
        self.assertEqual((j.index, j.count), (3, 12))
        self.assertAlmostEqual(j.percent, 50.0)
        self.assertIn("Item 3 de 12", dl.status_text(j))

    def test_garbage_ignored(self):
        j = dl.Job("https://a.com", dl.Options(folder="/t"))
        self.assertFalse(dl.parse_line(j, "FLX|broken"))
        self.assertFalse(dl.parse_line(j, ""))

    def test_errors(self):
        self.assertEqual(dl.friendly_error("ERROR: [generic] Unsupported URL: x")[1], True)
        self.assertEqual(dl.friendly_error("ERROR: ffmpeg not found")[1], False)
        msg, heal = dl.friendly_error("ERROR: coisa estranha")
        self.assertTrue(heal)
        self.assertIn("coisa estranha", msg)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.op = FakeOpener()
        self.op.publish(FAKE_V1)
        self.engine = Engine(self.tmp.name, opener=self.op)

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_then_current_then_update(self):
        self.assertEqual(self.engine.check_and_update(), "installed")
        self.assertEqual(self.engine.version(), "2025.01.01")
        self.assertEqual(oct(self.engine.path.stat().st_mode & 0o777), "0o700")
        self.assertEqual(self.engine.check_and_update(), "current")
        self.op.publish(FAKE_V2)
        self.assertEqual(self.engine.check_and_update(), "updated")
        self.assertEqual(self.engine.version(refresh=True), "2025.02.02")

    def test_tampered_binary_rejected(self):
        self.op.files[primary_asset()] = b"#!/bin/sh\necho 2099.01.01\n"  # hash não confere
        with self.assertRaises(EngineError) as cm:
            self.engine.check_and_update()
        self.assertIn("SHA-256", str(cm.exception))
        self.assertFalse(self.engine.path.exists())

    def test_tamper_keeps_old_version(self):
        self.engine.check_and_update()
        self.op.publish(FAKE_V2)
        self.op.files[primary_asset()] = b"#!/bin/sh\necho 2099.01.01\n"
        with self.assertRaises(EngineError):
            self.engine.check_and_update()
        self.assertEqual(self.engine.version(refresh=True), "2025.01.01")

    def test_broken_binary_fails_selftest(self):
        self.op.publish("#!/bin/sh\nexit 3\n")
        with self.assertRaises(EngineError):
            self.engine.check_and_update()
        self.assertFalse(self.engine.path.exists())

    def test_http_only_blocked(self):
        with self.assertRaises(EngineError):
            self.engine._request("http://github.com/x")

    def test_parse_sums(self):
        h = "a" * 64
        self.assertEqual(parse_sums(f"{h}  yt-dlp\n{h} *yt-dlp_linux\nlixo"), {"yt-dlp": h, "yt-dlp_linux": h})


class RunnerAndHealTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.op = FakeOpener()
        self.op.publish(FAKE_V2)
        self.engine = Engine(self.tmp.name + "/data", opener=self.op)
        self.out = self.tmp.name + "/out"

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_job_success(self):
        self.engine.check_and_update()
        job = dl.Job("https://a.com/v", dl.Options(folder=self.out))
        updates = []
        res = dl.run_job(job, self.engine.command(), lambda j: updates.append(j.state))
        self.assertEqual(res, "done")
        self.assertEqual(job.title, "Meu | Titulo")
        self.assertTrue(job.filepath.endswith("Meu | Titulo.mp4"))
        self.assertIn("downloading", updates)
        self.assertIn("processing", updates)

    def test_self_healing_flow(self):
        # motor instalado = v1 (quebrado p/ o "site novo"); o "GitHub" já tem a v2.
        self.op.publish(FAKE_V1)
        self.engine.check_and_update()
        self.op.publish(FAKE_V2)
        events, done = [], threading.Event()

        def emit(kind, *a):
            events.append((kind, a))
            if kind == "job" and a[0].state in ("done", "error"):
                done.set()

        st = Settings(self.tmp.name + "/s.json")
        mgr = Manager(st, self.engine, emit)
        job = mgr.add("https://site-que-mudou.com/v", dl.Options(folder=self.out))
        self.assertTrue(done.wait(60))
        self.assertEqual(job.state, "done", job.message)
        self.assertEqual(self.engine.version(refresh=True), "2025.02.02")
        msgs = [a[1] for k, a in events if k == "engine"]
        self.assertTrue(any("atualizado" in m or "Verificando" in m or "procurando" in m for m in msgs))

    def test_heal_when_already_latest_gives_friendly_error(self):
        self.op.publish(FAKE_V1)
        self.engine.check_and_update()
        done = threading.Event()
        mgr = Manager(Settings(self.tmp.name + "/s.json"), self.engine,
                      lambda k, *a: done.set() if k == "job" and a[0].state == "error" else None)
        job = mgr.add("https://x.com/v", dl.Options(folder=self.out))
        self.assertTrue(done.wait(60))
        time.sleep(0.3)
        self.assertEqual(job.state, "error")
        self.assertIn("Nightly", job.message)

    def test_cancel_queued(self):
        job = dl.Job("https://a.com", dl.Options(folder=self.out))
        job.cancel()
        self.assertEqual(job.state, "cancelled")


class SettingsTests(unittest.TestCase):
    def test_roundtrip_and_validation(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            s = Settings(p)
            s["quality"] = "720"
            s.save()
            self.assertEqual(oct(p.stat().st_mode & 0o777), "0o600")
            self.assertEqual(Settings(p)["quality"], "720")
            p.write_text('{"quality": "evil", "cookies_browser": "--exec", "playlist": "yes"}')
            s2 = Settings(p)
            self.assertEqual(s2["quality"], "1080")
            self.assertEqual(s2["cookies_browser"], "")
            self.assertEqual(s2["playlist"], False)
            p.write_text("not json")
            Settings(p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
