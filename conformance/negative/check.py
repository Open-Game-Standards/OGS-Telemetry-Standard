#!/usr/bin/env python3
"""check.py — verify the negative corpus is what its manifest says.

Independently of the generator, decodes every negative vector with
pycapnp and checks the property that makes it negative: the envelope is
foreign or short, the message does not decode, a union discriminant is
one the schema does not declare, a page index is out of range, and so
on. Exit 0 = every vector verified.

Usage: python conformance/negative/check.py   (from the repo root)
"""
import json
import math
import pathlib
import struct
import sys

import capnp  # pycapnp

HERE = pathlib.Path(__file__).parent
SCHEMA = capnp.load(str(HERE.parent.parent / "ogs_telemetry.capnp"))
FRAMES = {0: SCHEMA.DiscoveryFrame, 1: SCHEMA.MotionFrame, 2: SCHEMA.EventFrame}
PASS = FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    PASS, FAIL = PASS + ok, FAIL + (not ok)
    print(f"{'PASS' if ok else 'FAIL'} {name}{' — ' + detail if detail and not ok else ''}")


def load(vec_id):
    return bytes.fromhex("".join((HERE / "vectors" / f"{vec_id}.hex").read_text().split()))


def decode(blob):
    return FRAMES[blob[4]].from_bytes(blob[8:])


def raw_which(reader):
    """The union discriminant as stored, even when undeclared."""
    try:
        return reader.which
    except capnp.KjException:
        return "undeclared"


def main():
    manifest = json.loads((HERE / "manifest.json").read_text())
    ids = [v["id"] for v in manifest["vectors"]]
    check("fourteen negative vectors", len(ids) == 14, str(ids))
    for v in manifest["vectors"]:
        vid, blob = v["id"], load(v["id"])
        if v["expect"] == "skip":
            ok = len(blob) < 8 or blob[:4] != b"OMT1" or blob[4] > 2
            check(f"{vid} is skipped before decoding", ok)
            continue
        if v["expect"] == "decode-error":
            try:
                with decode(blob) as m:
                    _ = m.objects[0].name
                check(f"{vid} fails to decode", False, "decoded")
            except (capnp.KjException, ValueError, IndexError):
                check(f"{vid} fails to decode", True)
            continue
        with decode(blob) as m:
            if vid == "multi-segment":
                segs = struct.unpack_from("<I", blob, 8)[0] + 1
                o = m.objects[0]
                check(vid, segs > 1 and o.name == "obj" and o.position.x == 1.5 and o.orientation.w == 1,
                      f"{segs} segments")
            elif vid == "non-canonical-null-text":
                check(vid, m.gameName == "" and m.objects[0].name == "obj" and m.objects[0].typeLabel == "")
            elif vid == "unknown-dynamics-variant":
                o = m.objects[0]
                check(vid, raw_which(o) == "undeclared" and o.name == "obj")
            elif vid == "unknown-drivepoint-variant":
                p = list(m.objects[0].drivePoints)
                check(vid, len(p) == 4 and raw_which(p[1]) == "undeclared" and p[1].id == 1
                      and raw_which(p[0]) == "wheel" and p[2].which == "jet")
            elif vid == "unknown-wheel-measurement-variant":
                w = m.objects[0].drivePoints[0].wheel
                check(vid, raw_which(w.rpm) == "undeclared" and w.torque.value == 850)
            elif vid == "page-index-out-of-range":
                check(vid, m.page >= m.pageCount > 1, f"page {m.page} of {m.pageCount}")
            elif vid == "type-mismatch-value":
                c = m.objects[0].channels[0]
                check(vid, c.id == 2 and c.which == "number")
            elif vid == "undeclared-channel":
                check(vid, m.objects[0].channels[0].id == 99)
            elif vid == "nonfinite-pose":
                p = m.objects[0].position
                check(vid, math.isnan(p.x) and math.isinf(p.y))
            else:
                check(vid, False, "no check for this vector")
    print(f"negative corpus: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
