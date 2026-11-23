"""Leitor independente de .rpm: confere lead, headers, digests, regiões e payload."""
import gzip, hashlib, struct, sys

TAGS = {1000:"NAME",1001:"VERSION",1002:"RELEASE",1022:"ARCH",1117:"BASENAMES",1118:"DIRNAMES",1116:"DIRINDEXES",
        1028:"FILESIZES",1030:"FILEMODES",1035:"FILEDIGESTS",1049:"REQUIRENAME",5046:"RECOMMENDNAME",1124:"PAYLOADFORMAT"}

def read_header(buf, off, region):
    assert buf[off:off+4] == b"\x8e\xad\xe8\x01", "magic do header"
    n, dl = struct.unpack(">II", buf[off+8:off+16])
    idx = [struct.unpack(">IIII", buf[off+16+i*16: off+32+i*16]) for i in range(n)]
    ds = off + 16 + n*16
    data = buf[ds:ds+dl]
    assert idx[0][0] == region and idx[0][1] == 7 and idx[0][3] == 16, "região primeiro"
    tr = struct.unpack(">IIiI", data[idx[0][2]:idx[0][2]+16])
    assert tr == (region, 7, -(n*16), 16), f"trailer da região {tr}"
    assert idx[0][2] + 16 == dl, "trailer no fim dos dados"
    assert [i[0] for i in idx] == sorted(i[0] for i in idx), "índice ordenado"
    vals, last = {}, -1
    for tag, typ, o, cnt in idx[1:]:
        assert o >= last, "offsets crescentes"
        al = {3:2, 4:4, 5:8}.get(typ, 1)
        assert o % al == 0, f"alinhamento tag {tag}"
        if typ == 6 or typ == 9:
            end = data.index(b"\0", o); v = data[o:end].decode(); last = end+1
        elif typ == 8:
            v, p = [], o
            for _ in range(cnt):
                e = data.index(b"\0", p); v.append(data[p:e].decode()); p = e+1
            last = p
        elif typ == 4:
            v = list(struct.unpack(">%dI" % cnt, data[o:o+4*cnt])); last = o+4*cnt
        elif typ == 3:
            v = list(struct.unpack(">%dH" % cnt, data[o:o+2*cnt])); last = o+2*cnt
        elif typ == 7:
            v = data[o:o+cnt]; last = o+cnt
        else:
            raise AssertionError(f"tipo {typ}")
        vals[tag] = v
    return vals, off + 16 + n*16 + dl

def main(path):
    b = open(path, "rb").read()
    magic, major, minor, typ, arch, name, osn, sigt, _ = struct.unpack(">IBBhh66shh16s", b[:96])
    assert magic == 0xEDABEEDB and major == 3 and sigt == 5
    print("lead ok:", name.rstrip(b"\0").decode())
    sig, end = read_header(b, 96, 62)
    end += (-end) % 8
    hdr, hend = read_header(b, end, 63)
    header_bytes, payload = b[end:hend], b[hend:]
    assert sig[269] == hashlib.sha1(header_bytes).hexdigest(), "SHA1 do header"
    assert sig[273] == hashlib.sha256(header_bytes).hexdigest(), "SHA256 do header"
    assert sig[1004] == hashlib.md5(header_bytes + payload).digest(), "MD5"
    assert sig[1000][0] == len(header_bytes) + len(payload), "SIZE"
    raw = gzip.decompress(payload)
    assert sig[1007][0] == len(raw), "PAYLOADSIZE"
    print("assinaturas/digests ok; payload", len(raw), "bytes")
    # cpio
    pos, found = 0, []
    while True:
        assert raw[pos:pos+6] == b"070701"
        f = [int(raw[pos+6+i*8:pos+14+i*8], 16) for i in range(13)]
        ino, mode, _, _, nl, mt, fs, _, _, _, _, ns, _ = f
        nm = raw[pos+110:pos+110+ns-1].decode()
        pos += 110 + ns; pos += (-pos) % 4
        if nm == "TRAILER!!!": break
        found.append((nm, mode, raw[pos:pos+fs])); pos += fs; pos += (-pos) % 4
    dn, bn, di = hdr[1118], hdr[1117], hdr[1116]
    expect = [dn[di[i]] + bn[i] for i in range(len(bn))]
    assert [n[1:] for n,_,_ in found] == expect, "ordem/nomes payload == header"
    assert [len(d) for _,_,d in found] == hdr[1028], "tamanhos"
    assert [m for _,m,_ in found] == hdr[1030], "modos"
    for (nm, mode, data), dg in zip(found, hdr[1035]):
        if mode & 0o170000 == 0o100000:
            assert hashlib.sha256(data).hexdigest() == dg, nm
    assert expect == sorted(expect)
    print("payload == header: %d entradas, digests SHA-256 ok" % len(found))
    for p in expect: print("  ", p)
    print("NAME-VER-REL:", hdr[1000], hdr[1001], hdr[1002], hdr[1022])
    print("Requires:", hdr[1049]); print("Recommends:", hdr[5046])

main(sys.argv[1])
