#!/usr/bin/env python3
"""generate.py — build the negative conformance corpus.

Each vector is a datagram a receiver must survive: malformed, foreign,
or valid in a shape senders never produce (non-canonical, multi-segment,
unknown union variants from a future schema). They are derived
deterministically from the positive corpus (../vectors) by mutating
known fields, located through the schema with pycapnp, so the bytes are
a function of the positive corpus alone. manifest.json says what a
receiver must do with each (README.md).

Usage: python conformance/negative/generate.py   (from the repo root)
"""
import json
import pathlib
import struct

import capnp  # pycapnp

HERE = pathlib.Path(__file__).parent
CORPUS = HERE.parent
SCHEMA = capnp.load(str(CORPUS.parent / "ogs_telemetry.capnp"))
ENVELOPE = 8


def positive(vec_id):
    return bytes.fromhex("".join((CORPUS / "vectors" / f"{vec_id}.hex").read_text().split()))


def write_hex(path, blob):
    h = blob.hex()
    path.write_text("".join(h[i:i + 64] + "\n" for i in range(0, len(h), 64)))


# ---- locating structs in a single-segment canonical message ----

def word(buf, at):
    return struct.unpack_from("<Q", buf, at)[0]


def struct_at(buf, ptr_at):
    """Follow a struct pointer at byte offset ptr_at; returns (data_at, data_words, ptr_words)."""
    p = word(buf, ptr_at)
    assert p & 3 == 0, "not a struct pointer"
    off = (p >> 2) & 0x3FFFFFFF
    if off & 0x20000000:
        off -= 0x40000000
    data_words = (p >> 32) & 0xFFFF
    ptr_words = (p >> 48) & 0xFFFF
    return ptr_at + 8 + off * 8, data_words, ptr_words


def list_element(buf, ptr_at, index):
    """Element `index` of a composite (struct) list pointer at ptr_at."""
    p = word(buf, ptr_at)
    assert p & 3 == 1 and (p >> 32) & 7 == 7, "not a composite list pointer"
    off = (p >> 2) & 0x3FFFFFFF
    if off & 0x20000000:
        off -= 0x40000000
    tag_at = ptr_at + 8 + off * 8
    tag = word(buf, tag_at)
    data_words = (tag >> 32) & 0xFFFF
    ptr_words = (tag >> 48) & 0xFFFF
    elem_at = tag_at + 8 + index * (data_words + ptr_words) * 8
    return elem_at, data_words, ptr_words


def pointer_slot(data_at, data_words, index):
    return data_at + data_words * 8 + index * 8


def root(buf):
    """(data_at, data_words, ptr_words) of the root struct; buf is the datagram."""
    seg_count = struct.unpack_from("<I", buf, ENVELOPE)[0] + 1
    assert seg_count == 1, "derive from single-segment vectors"
    seg_at = ENVELOPE + 8
    return struct_at(buf, seg_at)


def ptr_index(schema, field):
    return schema.fields[field].proto.slot.offset


def set_u16(buf, data_at, u16_index, value):
    struct.pack_into("<H", buf, data_at + u16_index * 2, value)


# ---- mutations ----

def motion_object(buf, index=0):
    data_at, dw, pw = root(buf)
    return list_element(buf, pointer_slot(data_at, dw, ptr_index(SCHEMA.MotionFrame.schema, "objects")), index)


def unknown_dynamics():
    buf = bytearray(positive("motion-bodydynamics"))
    at, dw, pw = motion_object(buf)
    disc = SCHEMA.MotionObject.schema.node.struct.discriminantOffset
    set_u16(buf, at, disc, 9)  # no such dynamics variant
    return bytes(buf)


def drive_point(buf, obj, index):
    at, dw, pw = obj
    return list_element(buf, pointer_slot(at, dw, ptr_index(SCHEMA.MotionObject.schema, "drivePoints")), index)


def unknown_drivepoint_variant():
    buf = bytearray(positive("motion-drivepoints"))
    at, dw, pw = drive_point(buf, motion_object(buf), 1)  # the propeller
    disc = SCHEMA.DrivePoint.schema.node.struct.discriminantOffset
    set_u16(buf, at, disc, 99)  # a future drive-point kind
    return bytes(buf)


def unknown_wheel_measurement():
    buf = bytearray(positive("motion-wheel"))
    dp = drive_point(buf, motion_object(buf), 0)
    w_at, w_dw, w_pw = struct_at(buf, pointer_slot(dp[0], dp[1], SCHEMA.DrivePoint.schema.fields["wheel"].proto.slot.offset))
    disc = SCHEMA.WheelState.schema.fields["rpm"].schema.node.struct.discriminantOffset
    set_u16(buf, w_at, disc, 5)  # a future variant of the rpm optionality union
    return bytes(buf)


def nonfinite_pose():
    buf = bytearray(positive("motion-pose"))
    at, dw, pw = motion_object(buf)
    pos_at, _, _ = struct_at(buf, pointer_slot(at, dw, ptr_index(SCHEMA.MotionObject.schema, "position")))
    struct.pack_into("<f", buf, pos_at, float("nan"))
    struct.pack_into("<f", buf, pos_at + 4, float("inf"))
    return bytes(buf)


def page_index_out_of_range():
    buf = bytearray(positive("discovery-paged-p1"))
    at, dw, pw = root(buf)
    off = SCHEMA.DiscoveryFrame.schema.fields["page"].proto.slot.offset  # in UInt16 units
    set_u16(buf, at, off, 2)  # page 2 of pageCount 2
    return bytes(buf)


def truncated():
    blob = positive("motion-pose")
    return blob[:len(blob) - 24]


def segment_size_overflow():
    buf = bytearray(positive("motion-pose"))
    words = struct.unpack_from("<I", buf, ENVELOPE + 4)[0]
    struct.pack_into("<I", buf, ENVELOPE + 4, words + 64)  # claims more words than the datagram has
    return bytes(buf)


def foreign_magic():
    return b"XXXX" + positive("motion-pose")[4:]


def unknown_frame_type():
    buf = bytearray(positive("motion-pose"))
    buf[4] = 0x07
    return bytes(buf)


def runt():
    return b"OMT1\x01"


def envelope(frame_type, message_bytes):
    return b"OMT1" + bytes([frame_type, 0, 0, 0]) + message_bytes


def multi_segment():
    mb = capnp._MallocMessageBuilder(2)
    m = mb.init_root(SCHEMA.MotionFrame)
    m.timestamp = 1.25
    o = m.init("objects", 1)[0]
    o.name = "obj"
    o.position.x = 1.5
    o.position.y = 0.25
    o.position.z = -3.75
    o.orientation.w = 1
    segments = [bytes(seg) for seg in mb.get_segments_for_output()]
    assert len(segments) > 1, "expected several segments"
    # standard stream framing: segment count - 1, each segment's size in
    # words, padding to a word, then the segments
    table = struct.pack("<I", len(segments) - 1) + b"".join(
        struct.pack("<I", len(seg) // 8) for seg in segments)
    table += bytes(-len(table) % 8)
    return envelope(0x01, table + b"".join(segments))


def non_canonical_null_text():
    # pycapnp leaves unset Text fields as null pointers, which canonical
    # senders never do; receivers read null as "".
    m = SCHEMA.DiscoveryFrame.new_message()
    m.schemaVersion = 1
    m.sessionStartUnixUs = 1_730_000_000_000_000
    o = m.init("objects", 1)[0]
    o.name = "obj"
    o.primary = True
    return envelope(0x00, m.to_bytes())


def type_mismatch_value():
    # after discovery-channels: lights.headlights (id 2) is declared boolean,
    # this frame sends it as a number
    m = SCHEMA.MotionFrame.new_message()
    m.timestamp = 2.5
    o = m.init("objects", 1)[0]
    o.name = "demo_car"
    o.orientation.w = 1
    c = o.init("channels", 1)[0]
    c.id = 2
    c.number = 1.0
    return envelope(0x01, m.to_bytes())


def undeclared_channel():
    # after discovery-channels: id 99 is not declared
    m = SCHEMA.MotionFrame.new_message()
    m.timestamp = 2.5
    o = m.init("objects", 1)[0]
    o.name = "demo_car"
    o.orientation.w = 1
    c = o.init("channels", 1)[0]
    c.id = 99
    c.number = 5.0
    return envelope(0x01, m.to_bytes())


VECTORS = [
    ("runt-datagram", runt, "skip", None,
     "Shorter than the 8-byte envelope"),
    ("foreign-magic", foreign_magic, "skip", None,
     "Another protocol's datagram on the shared group: magic is not OMT1"),
    ("unknown-frame-type", unknown_frame_type, "skip", None,
     "Frame type 0x07, not defined by this schema"),
    ("truncated-message", truncated, "decode-error", None,
     "motion-pose cut short: the segment ends past the datagram"),
    ("segment-size-overflow", segment_size_overflow, "decode-error", None,
     "motion-pose whose segment table claims 64 more words than the datagram holds"),
    ("multi-segment", multi_segment, "accept", None,
     "motion-pose content in a multi-segment message (valid, never sent by canonical senders): "
     "reads like motion-pose"),
    ("non-canonical-null-text", non_canonical_null_text, "accept", None,
     "Discovery with gameName, typeLabel and location as null pointers: read as \"\""),
    ("unknown-dynamics-variant", unknown_dynamics, "accept", None,
     "motion-bodydynamics with dynamics discriminant 9: treat as noDynamics, keep pose"),
    ("unknown-drivepoint-variant", unknown_drivepoint_variant, "accept", None,
     "motion-drivepoints with drive point 1 (id 1) discriminant 99: ignore its state, keep the others"),
    ("unknown-wheel-measurement-variant", unknown_wheel_measurement, "accept", None,
     "motion-wheel with the rpm optionality union's discriminant 5: treat as noRpm, keep the other fields"),
    ("page-index-out-of-range", page_index_out_of_range, "ignore-page", None,
     "discovery-paged-p1 with page 2 of pageCount 2: malformed page, ignored"),
    ("type-mismatch-value", type_mismatch_value, "drop-value", "discovery-channels",
     "After discovery-channels: boolean channel id 2 sent as a number: drop the value"),
    ("undeclared-channel", undeclared_channel, "drop-value", "discovery-channels",
     "After discovery-channels: channel id 99, which nothing declares: never applied"),
    ("nonfinite-pose", nonfinite_pose, "fault", None,
     "motion-pose with position x NaN and y +inf: decodes; receivers driving hardware treat it as a fault "
     "(implementation-udp.md § Trust and safety)"),
]


def main():
    out = HERE / "vectors"
    out.mkdir(exist_ok=True)
    for f in out.glob("*.hex"):
        f.unlink()
    manifest = {
        "negativeCorpusVersion": 1,
        "derivedFrom": "conformance/vectors (positive corpus)",
        "expectations": {
            "skip": "silently skipped before decoding (not a decode error); the receiver keeps receiving",
            "decode-error": "counted as a decode error; no frame is dispatched; the receiver keeps receiving",
            "accept": "decoded and applied; see the description for how unknown parts read",
            "ignore-page": "decoded, but the page is not merged into the descriptor tables",
            "drop-value": "decoded; the value is not applied to the channel",
            "fault": "decoded; a receiver driving hardware does not follow it",
        },
        "vectors": [],
    }
    for vec_id, build, expect, after, description in VECTORS:
        blob = build()
        write_hex(out / f"{vec_id}.hex", blob)
        entry = {"id": vec_id, "file": f"vectors/{vec_id}.hex", "expect": expect, "description": description}
        if after:
            entry["after"] = after
        manifest["vectors"].append(entry)
        print(f"  {vec_id}: {len(blob)} bytes, {expect}")
    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
