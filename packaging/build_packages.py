#!/usr/bin/env python3
"""Gera dist/zek-download_<versão>_all.deb e dist/zek-download-<versão>-1.noarch.rpm.

Python puro (sem dpkg-deb / rpmbuild), então roda no Linux Mint e no Fedora.
Uso:  python3 packaging/build_packages.py [deb|rpm|all]
"""
import gzip
import hashlib
import io
import os
import re
import struct
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "zekdl"
PKG = ROOT / "packaging"
DIST = ROOT / "dist"
APP_ID = "io.github.aaaiiicerol.ZekDownload"
NAME = "zek-download"
VERSION = re.search(r'__version__ = "([^"]+)"', (SRC / "__init__.py").read_text()).group(1)
RELEASE = "1"
MTIME = int(os.environ.get("SOURCE_DATE_EPOCH", time.time()))
URL = "https://github.com/aaaiiicerol"
MAINTAINER = "aaaiiicerol <aaaiiicerol@users.noreply.github.com>"
SUMMARY = "Baixador de vídeos e músicas de vários sites"
DESCRIPTION = (
    "O Zek Download baixa vídeos e músicas de milhares de sites usando o yt-dlp.\n"
    "Interface simples, com progresso em tempo real e mensagens claras.\n"
    "O motor de download (yt-dlp) é atualizado automaticamente, com verificação\n"
    "SHA-256, para continuar funcionando quando os sites mudam."
)


def collect(fmt):
    """Lista (caminho_destino, bytes, modo) de arquivos regulares do pacote."""
    files = [("/usr/bin/zek-download", (PKG / "zek-download").read_bytes(), 0o755)]
    for py in sorted(SRC.glob("*.py")):
        files.append((f"/usr/lib/zek-download/zekdl/{py.name}", py.read_bytes(), 0o644))
    files += [
        (f"/usr/share/applications/{APP_ID}.desktop", (PKG / f"{APP_ID}.desktop").read_bytes(), 0o644),
        (f"/usr/share/icons/hicolor/scalable/apps/{APP_ID}.svg", (PKG / f"{APP_ID}.svg").read_bytes(), 0o644),
        ("/usr/share/doc/zek-download/README.md", (ROOT / "README.md").read_bytes(), 0o644),
    ]
    lic = (ROOT / "LICENSE").read_bytes()
    if fmt == "deb":
        files.append(("/usr/share/doc/zek-download/copyright", lic, 0o644))
    else:
        files.append(("/usr/share/licenses/zek-download/LICENSE", lic, 0o644))
    return sorted(files)


def parent_dirs(paths, owned_prefixes):
    """Diretórios que o pacote precisa criar/possuir (não os do sistema)."""
    dirs = set()
    for p in paths:
        d = os.path.dirname(p)
        while d and d != "/":
            dirs.add(d)
            d = os.path.dirname(d)
    return sorted(dirs)

# =================================================================== DEB

def _tar_bytes(entries, compress):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:" + compress if compress else "w", format=tarfile.GNU_FORMAT) as tf:
        for name, data, mode, is_dir in entries:
            ti = tarfile.TarInfo(name)
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = "root"
            ti.mtime = MTIME
            ti.mode = mode
            if is_dir:
                ti.type = tarfile.DIRTYPE
                tf.addfile(ti)
            else:
                ti.size = len(data)
                tf.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def _ar(members):
    out = bytearray(b"!<arch>\n")
    for name, data in members:
        out += (f"{name}/"[:16].ljust(16) + f"{MTIME:<12}" + "0     " + "0     " + "100644  "
                + f"{len(data):<10}" + "`\n").encode()
        out += data
        if len(data) % 2:
            out += b"\n"
    return bytes(out)


def build_deb():
    files = collect("deb")
    dirs = parent_dirs([f[0] for f in files], None)
    # dpkg já conhece /usr, /usr/bin, /usr/lib, /usr/share...: ainda assim listar é inofensivo.
    data_entries = [("./", b"", 0o755, True)]
    data_entries += [("." + d + "/", b"", 0o755, True) for d in dirs]
    data_entries += [("." + p, data, mode, False) for p, data, mode in files]
    data_tar = _tar_bytes(data_entries, "xz")

    size_kib = sum(len(d) for _, d, _ in files) // 1024 + 1
    md5s = "".join(f"{hashlib.md5(d).hexdigest()}  {p[1:]}\n" for p, d, _ in files)
    control = (
        f"Package: {NAME}\nVersion: {VERSION}\nArchitecture: all\nMaintainer: {MAINTAINER}\n"
        f"Installed-Size: {size_kib}\n"
        "Depends: python3 (>= 3.8), python3-gi, gir1.2-gtk-3.0, ffmpeg, ca-certificates\n"
        "Recommends: nodejs\n"
        f"Section: video\nPriority: optional\nHomepage: {URL}\n"
        f"Description: {SUMMARY}\n"
        + "".join(f" {l}\n" for l in DESCRIPTION.splitlines())
    )
    ctrl_tar = _tar_bytes([("./", b"", 0o755, True),
                           ("./control", control.encode(), 0o644, False),
                           ("./md5sums", md5s.encode(), 0o644, False)], "gz")
    DIST.mkdir(exist_ok=True)
    out = DIST / f"{NAME}_{VERSION}_all.deb"
    out.write_bytes(_ar([("debian-binary", b"2.0\n"), ("control.tar.gz", ctrl_tar), ("data.tar.xz", data_tar)]))
    return out

# =================================================================== RPM

NULL, CHAR, INT8, INT16, INT32, INT64, STRING, BIN, STRARRAY, I18N = range(10)
ALIGN = {INT16: 2, INT32: 4, INT64: 8}


def _encode(rtype, value):
    if rtype == STRING:
        return value.encode() + b"\0", 1
    if rtype == I18N:
        return value.encode() + b"\0", 1
    if rtype == STRARRAY:
        return b"".join(v.encode() + b"\0" for v in value), len(value)
    if rtype == INT16:
        return struct.pack(">%dH" % len(value), *value), len(value)
    if rtype == INT32:
        return struct.pack(">%dI" % len(value), *value), len(value)
    if rtype == BIN:
        return bytes(value), len(value)
    raise ValueError(rtype)


def make_header(entries, region_tag):
    """entries: [(tag, tipo, valor)] -> bytes de um header RPM com região imutável."""
    index, data = [], bytearray()
    for tag, rtype, value in sorted(entries, key=lambda e: e[0]):
        raw, count = _encode(rtype, value)
        al = ALIGN.get(rtype, 1)
        data += b"\0" * ((-len(data)) % al)
        index.append(struct.pack(">IIII", tag, rtype, len(data), count))
        data += raw
    n = len(entries) + 1
    region_index = struct.pack(">IIII", region_tag, BIN, len(data), 16)
    data += struct.pack(">IIiI", region_tag, BIN, -(n * 16), 16)
    return (b"\x8e\xad\xe8\x01\0\0\0\0" + struct.pack(">II", n, len(data))
            + region_index + b"".join(index) + bytes(data))


def _cpio_newc(items):
    """items: [(caminho_com_./, modo_com_tipo, dados, ino)]"""
    out = bytearray()

    def pad():
        out.extend(b"\0" * ((-len(out)) % 4))

    for path, mode, data, ino in items:
        name = path.encode() + b"\0"
        hdr = "070701" + "".join(f"{v:08X}" for v in (
            ino, mode, 0, 0, 2 if mode & 0o170000 == 0o040000 else 1, MTIME, len(data), 0, 0, 0, 0, len(name), 0))
        out += hdr.encode() + name
        pad()
        out += data
        pad()
    trailer = b"TRAILER!!!\0"
    out += ("070701" + "".join(f"{v:08X}" for v in (0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, len(trailer), 0))).encode() + trailer
    out.extend(b"\0" * ((-len(out)) % 4))
    return bytes(out)


def build_rpm():
    files = collect("rpm")
    dirs = [d for d in parent_dirs([f[0] for f in files], None)
            if d.startswith(("/usr/lib/zek-download", "/usr/share/doc/zek-download", "/usr/share/licenses/zek-download"))]
    nodes = [(d, 0o040755, b"") for d in dirs] + [(p, 0o100000 | m, data) for p, data, m in files]
    nodes.sort(key=lambda n: n[0])

    dirnames, dirindex, basenames = [], [], []
    for path, _, _ in nodes:
        d, b = os.path.split(path)
        d += "/"
        if d not in dirnames:
            dirnames.append(d)
        dirindex.append(dirnames.index(d))
        basenames.append(b)
    is_dir = [m & 0o170000 == 0o040000 for _, m, _ in nodes]

    payload_raw = _cpio_newc([("." + p, m, data, i + 1) for i, (p, m, data) in enumerate(nodes)])
    payload = gzip.compress(payload_raw, 9, mtime=0)

    n = len(nodes)
    RPMLIB_LE = 0x0100000A       # rpmlib(...) <= versão
    requires = [
        ("/usr/bin/python3", 0, ""), ("python3-gobject", 0, ""), ("gtk3", 0, ""),
        ("ca-certificates", 0, ""), ("/usr/bin/ffmpeg", 0, ""),
        ("rpmlib(CompressedFileNames)", RPMLIB_LE, "3.0.4-1"),
        ("rpmlib(PayloadFilesHavePrefix)", RPMLIB_LE, "4.0-1"),
        ("rpmlib(FileDigests)", RPMLIB_LE, "4.6.0-1"),
    ]
    ev = f"{VERSION}-{RELEASE}"
    entries = [
        (100, STRARRAY, ["C"]),
        (1000, STRING, NAME), (1001, STRING, VERSION), (1002, STRING, RELEASE),
        (1004, I18N, SUMMARY), (1005, I18N, DESCRIPTION),
        (1006, INT32, [MTIME]), (1007, STRING, "localhost"),
        (1009, INT32, [sum(len(d) for _, _, d in nodes)]),
        (1014, STRING, "MIT"), (1015, STRING, MAINTAINER), (1016, STRING, "Applications/Multimedia"),
        (1020, STRING, URL), (1021, STRING, "linux"), (1022, STRING, "noarch"),
        (1028, INT32, [len(d) for _, _, d in nodes]),
        (1030, INT16, [m for _, m, _ in nodes]),
        (1033, INT16, [0] * n),
        (1034, INT32, [MTIME] * n),
        (1035, STRARRAY, ["" if is_dir[i] else hashlib.sha256(nodes[i][2]).hexdigest() for i in range(n)]),
        (1036, STRARRAY, [""] * n),
        (1037, INT32, [0] * n),
        (1039, STRARRAY, ["root"] * n), (1040, STRARRAY, ["root"] * n),
        (1045, INT32, [0xFFFFFFFF] * n),
        (1047, STRARRAY, [NAME]), (1112, INT32, [8]), (1113, STRARRAY, [ev]),
        (1048, INT32, [r[1] for r in requires]),
        (1049, STRARRAY, [r[0] for r in requires]),
        (1050, STRARRAY, [r[2] for r in requires]),
        (1064, STRING, "4.19.1"),
        (1095, INT32, [1] * n), (1096, INT32, list(range(1, n + 1))), (1097, STRARRAY, [""] * n),
        (1116, INT32, dirindex), (1117, STRARRAY, basenames), (1118, STRARRAY, dirnames),
        (1124, STRING, "cpio"), (1125, STRING, "gzip"), (1126, STRING, "9"),
        (5011, INT32, [8]),                                # algoritmo dos digests = SHA-256
        (5046, STRARRAY, ["nodejs"]), (5047, STRARRAY, [""]), (5048, INT32, [0x0000000]),  # Recommends
    ]
    header = make_header(entries, 63)
    sig_entries = [
        (269, STRING, hashlib.sha1(header).hexdigest()),
        (273, STRING, hashlib.sha256(header).hexdigest()),
        (1000, INT32, [len(header) + len(payload)]),
        (1004, BIN, hashlib.md5(header + payload).digest()),
        (1007, INT32, [len(payload_raw)]),
    ]
    sig = make_header(sig_entries, 62)
    sig += b"\0" * ((-len(sig)) % 8)
    lead = struct.pack(">IBBhh66shh16s", 0xEDABEEDB, 3, 0, 0, 1,
                       f"{NAME}-{ev}".encode(), 1, 5, b"\0" * 16)
    DIST.mkdir(exist_ok=True)
    out = DIST / f"{NAME}-{VERSION}-{RELEASE}.noarch.rpm"
    out.write_bytes(lead + sig + header + payload)
    return out


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("deb", "all"):
        print("OK", build_deb())
    if what in ("rpm", "all"):
        print("OK", build_rpm())
