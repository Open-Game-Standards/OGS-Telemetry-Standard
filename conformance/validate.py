#!/usr/bin/env python3
"""validate.py — decode every conformance vector and assert the
manifest-declared semantics, independently of any reference SDK.

Uses pycapnp (official capnproto bindings) against ogs_telemetry.capnp:
the schema and the corpus are validated by a third implementation, not
by the code that generated them. Each vector is also checked for
canonical OGS encoding (implementation-capnproto.md § Encoding rules):
a schema-free re-encoder written from the Cap'n Proto canonicalization
rules must reproduce the payload exactly, and a schema-driven walk checks
unused bits, discriminants and field presence. Exit 0 = all vectors
verified.

Usage: python conformance/validate.py   (from the repo root)
"""
import json
import pathlib
import sys

import capnp  # pycapnp

HERE = pathlib.Path(__file__).parent
SCHEMA = HERE.parent / "ogs_telemetry.capnp"
MANIFEST = HERE / "manifest.json"

PASS = FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    PASS, FAIL = PASS + ok, FAIL + (not ok)
    suffix = f" — {detail}" if (detail and not ok) else ""
    print(f"{'PASS' if ok else 'FAIL'} {name}{suffix}")


def load(vec_id):
    hex_ = "".join((HERE / "vectors" / f"{vec_id}.hex").read_text().split())
    blob = bytes.fromhex(hex_)
    assert blob[:4] == b"OMT1", "envelope magic"
    return blob[4], blob[8:]


frame_type_names = {0: "DiscoveryFrame", 1: "MotionFrame", 2: "EventFrame"}


def main():
    schema = capnp.load(str(SCHEMA))  # type: ignore # stub-less Cython module
    try:
        manifest = json.loads(MANIFEST.read_text())
    except (OSError, ValueError) as exc:
        # unreadable/corrupt manifest is a CI failure, not a traceback
        print(f"FAIL manifest readable/valid — {exc}")
        sys.exit(1)
    check("manifest schemaVersion 1", manifest["schemaVersion"] == 1)
    ids = [v["id"] for v in manifest["vectors"]]
    check("sixteen known vectors", ids == [
        "discovery-minimal", "discovery-channels", "motion-pose",
        "motion-channels", "motion-multi", "motion-bodydynamics",
        "event-impact", "discovery-gravity-vector", "motion-local-gravity",
        "motion-local-gravity-zero", "discovery-paged-p0", "discovery-paged-p1",
        "motion-parts-p0", "motion-parts-p1", "discovery-identity",
        "motion-wheel"], str(ids))

    nodes = struct_nodes(schema)
    for vec in manifest["vectors"]:
        vec_id = vec["id"]
        ft, payload = load(vec_id)
        check(f"{vec_id} envelope",
              ft == expected_type[vec_id], f"frame type {ft}")
        cls = getattr(schema, frame_type_names[ft])
        with cls.from_bytes(payload) as msg:  # pycapnp wants a context manager
            try:
                ok, detail = globals()["check_" + vec_id.replace("-", "_")](msg), ""
            except capnp.KjException as exc:  # e.g. undeclared discriminant
                ok, detail = False, str(exc).splitlines()[0]
            check(f"{vec_id} semantics", ok, detail)
            problems = []
            matches_input(nodes, cls.schema.node, msg, vec["input"],
                          frame_type_names[ft], problems)
            check(f"{vec_id} matches manifest input exactly", not problems,
                  "; ".join(problems))
        seg, problems = single_segment(payload)
        if seg is not None:
            try:
                ok = canonicalize(seg) == seg
                problems = [] if ok else ["differs from its canonical form"]
            except EncodingError as exc:
                problems = [str(exc)]
        check(f"{vec_id} canonical form", not problems, "; ".join(problems))
        if seg is not None:
            problems = encoding_problems(schema, cls.schema.node, seg)
            check(f"{vec_id} encoding rules", not problems,
                  "; ".join(problems))


def check_discovery_minimal(d):
    return (d.schemaVersion == 1 and d.gameName == "conformance"
            and d.sessionStartUnixUs == 1_730_000_000_000_000
            and len(d.objects) == 1 and d.objects[0].name == "obj"
            and d.objects[0].primary
            and d.environment.airDensity == 1.25
            and d.environment.medium == "asphalt"
            and d.instanceLabel == "" and d.host == "")


def check_discovery_channels(d):
    ch = list(d.objects[0].channels)
    return (d.objects[0].name == "demo_car"
            and d.objects[0].typeLabel == "conformance car"
            and len(ch) == 3
            and ch[0].name == "engine.rpm" and ch[0].unit == "rpm"
            and ch[0].range.min == 0 and ch[0].range.max == 9000
            and ch[1].name == "vehicle.speed" and ch[1].unit == "m/s"
            and ch[1].range.max == 30
            and ch[2].name == "lights.headlights" and ch[2].unit == ""
            and [c.type for c in ch] == ["number", "number", "boolean"])


def check_motion_pose(m):
    o = m.objects[0]
    return (m.timestamp == 1.25 and o.name == "obj"
            and (o.position.x, o.position.y, o.position.z) == (1.5, 0.25, -3.75)
            and o.orientation.w == 1 and o.orientation.x == 0)


def check_motion_channels(m):
    o = m.objects[0]
    cv = {c.id: c.number for c in o.channels if c.which == "number"}
    return (m.timestamp == 2.5 and o.name == "demo_car"
            and o.orientation.y == 1
            and cv.get(0) == 3250.5 and cv.get(1) == 8
            and any(c.which == "boolean" and c.boolean for c in o.channels))


def check_motion_multi(m):
    return (m.timestamp == 3.75 and len(m.objects) == 2
            and m.objects[0].name == "player_car"
            and m.objects[0].position.x == 1
            and m.objects[1].name == "wingman"
            and (m.objects[1].position.y, m.objects[1].position.z) == (0.5, 2.5))


def check_motion_bodydynamics(m):
    o = m.objects[0]
    bd = o.bodyDynamics
    return (m.timestamp == 4.5 and o.name == "obj"
            and (o.position.x, o.position.y, o.position.z) == (0.5, 1.25, -2.5)
            and o.orientation.y == 0.5 and o.orientation.w == 0.875
            and o.which == "bodyDynamics"
            and (bd.specificForce.x, bd.specificForce.y, bd.specificForce.z)
                == (0.25, 9.5, -1.5)
            and (bd.angularVelocity.x, bd.angularVelocity.y, bd.angularVelocity.z)
                == (-0.125, 0.375, 0.75))


def check_event_impact(e):
    ev = e.events[0]
    return (e.timestamp == 0.125 and len(e.events) == 1
            and ev.id == 7 and ev.name == "body.impact"
            and ev.intensity == 0.75 and ev.duration == 0.25
            and ev.which == "direction"
            and (ev.direction.x, ev.direction.y, ev.direction.z) == (-1, 0, 0))


def check_discovery_gravity_vector(d):
    env = d.environment
    if env.which != "gravityVector":
        return False
    g = env.gravityVector
    return (env.medium == "vacuum" and (g.x, g.y, g.z) == (3, -4, 0)
            and env.gravity == (g.x ** 2 + g.y ** 2 + g.z ** 2) ** 0.5
            and d.objects[0].type == "spacecraft")


def check_motion_local_gravity(m):
    o = m.objects[0]
    if o.which != "bodyDynamics" or o.localGravity.which != "vector":
        return False
    g, f = o.localGravity.vector, o.bodyDynamics.specificForce
    # identity orientation: specific force = a − g with a = 0 (C-12)
    return (m.timestamp == 5.25 and (g.x, g.y, g.z) == (-2, 0, 0)
            and (f.x, f.y, f.z) == (-g.x, -g.y, -g.z))


def check_motion_local_gravity_zero(m):
    o = m.objects[0]
    if o.which != "noDynamics" or o.localGravity.which != "vector":
        return False
    g = o.localGravity.vector
    return m.timestamp == 6.5 and (g.x, g.y, g.z) == (0, 0, 0)


# ---------------------------------------------------------------------------
# Canonical OGS encoding (implementation-capnproto.md § Encoding rules)
# ---------------------------------------------------------------------------

MASK64 = (1 << 64) - 1


class EncodingError(Exception):
    pass


def check_discovery_paged_p0(d):
    o = d.objects[0]
    ch = list(o.channels)
    return (d.generation == 3 and d.page == 0 and d.pageCount == 2
            and o.name == "demo_car" and o.type == "vehicle" and o.primary
            and o.typeLabel == "conformance car"
            and len(ch) == 1 and ch[0].id == 0 and ch[0].name == "engine.rpm"
            and ch[0].type == "number"
            and len(list(o.values)) == 0)


def check_discovery_paged_p1(d):
    o = d.objects[0]
    ch = {c.id: c for c in o.channels}
    texts = list(o.texts)
    # a later page lists the object by name only: identity stays default
    return (d.generation == 3 and d.page == 1 and d.pageCount == 2
            and o.name == "demo_car" and not o.primary and o.typeLabel == ""
            and len(list(o.drivePoints)) == 0
            and sorted(ch) == [1, 2]
            and ch[1].name == "session.track" and ch[1].type == "text"
            and ch[2].name == "vehicle.speed" and ch[2].unit == "m/s"
            and ch[2].type == "number"
            and len(list(o.values)) == 0
            and len(texts) == 1 and texts[0].id == 1 and texts[0].text == "Test Ring")


def check_motion_parts_p0(m):
    o = m.objects[0]
    cv = {c.id: c.number for c in o.channels if c.which == "number"}
    return (m.timestamp == 7.75 and m.generation == 3
            and m.part == 0 and m.partCount == 2
            and o.name == "demo_car" and o.position.x == 4 and o.orientation.w == 1
            and cv == {0: 4100})


def check_motion_parts_p1(m):
    o = m.objects[0]
    cv = {c.id: c.number for c in o.channels if c.which == "number"}
    # a later part carries channel values only: pose and dynamics are default
    return (m.timestamp == 7.75 and m.generation == 3
            and m.part == 1 and m.partCount == 2
            and o.name == "demo_car" and o.orientation.w == 0
            and o.which == "noDynamics" and cv == {2: 12.5})


def check_motion_wheel(m):
    o = m.objects[0]
    w = o.drivePoints[0].wheel
    return (m.timestamp == 8.25 and o.name == "obj"
            and w.rpm == 1200 and w.slip == 0.0625 and w.compression == 0.03125
            and w.contact == "asphalt" and w.which == "core"
            and w.torque.which == "value" and w.torque.value == 850
            and w.brakePressure.which == "noBrakePressure")


def check_discovery_identity(d):
    o = d.objects[0]
    return (d.instanceLabel == "Rig 2" and d.host == "sim-pc"
            and d.gameName == "conformance"
            and o.name == "obj" and o.type == "aircraft" and o.primary)


def single_segment(payload):
    """Split a framed payload into its one segment's u64 words."""
    if len(payload) < 8 or len(payload) % 8:
        return None, ["payload is not a whole number of words"]
    count = int.from_bytes(payload[0:4], "little") + 1
    if count != 1:
        return None, [f"{count} segments; canonical form is single-segment"]
    words = int.from_bytes(payload[4:8], "little")
    body = payload[8:]
    if words * 8 != len(body):
        return None, [f"segment table says {words} words, payload has "
                      f"{len(body) // 8}"]
    return [int.from_bytes(body[i:i + 8], "little")
            for i in range(0, len(body), 8)], []


def pointer(seg, at):
    """Decode the pointer at word `at`: None, or (kind, target, a, b)."""
    w = seg[at]
    if w == 0:
        return None
    kind = w & 3
    if kind > 1:
        raise EncodingError(f"word {at}: far/capability pointer")
    off = (w & 0xFFFFFFFF) >> 2
    if off & (1 << 29):
        off -= 1 << 30
    target = at + 1 + off
    if kind == 0:  # struct: data words, pointer words
        return 0, target, (w >> 32) & 0xFFFF, (w >> 48) & 0xFFFF
    return 1, target, (w >> 32) & 7, w >> 35  # list: size code, count


def struct_ptr(off, dw, pw):
    return ((off << 2) & 0xFFFFFFFF) | (dw << 32) | (pw << 48)


def list_ptr(off, size, count):
    return 1 | ((off << 2) & 0xFFFFFFFF) | (size << 32) | (count << 35)


def trim(words):
    n = len(words)
    while n and words[n - 1] == 0:
        n -= 1
    return n


LIST_BITS = {0: 0, 1: 1, 2: 8, 3: 16, 4: 32, 5: 64}


def canonicalize(seg):
    """Schema-free canonical re-encoding, straight from the Cap'n Proto
    encoding spec: preorder, single segment, trailing zero data words and
    null pointers truncated (per struct list: across all elements),
    zero-sized structs at offset -1."""
    out = [0]
    try:
        _copy(seg, 0, out, 0)
    except IndexError:
        raise EncodingError("pointer out of bounds") from None
    return out


def _copy(seg, src_at, out, dst_at):
    p = pointer(seg, src_at)
    if p is None:
        return
    kind, t, a, b = p
    if kind == 0:
        data = seg[t:t + a]
        ptrs = list(range(t + a, t + a + b))
        dw = trim(data)
        pw = trim([seg[i] for i in ptrs])
        if dw == pw == 0:
            out[dst_at] = struct_ptr(-1, 0, 0)
            return
        at = len(out)
        out.extend(data[:dw])
        out.extend([0] * pw)
        out[dst_at] = struct_ptr(at - dst_at - 1, dw, pw)
        for i in range(pw):
            _copy(seg, ptrs[i], out, at + dw + i)
        return
    size, count = a, b
    at = len(out)
    if size == 7:  # composite: tag word, then elements
        n = (seg[t] & 0xFFFFFFFF) >> 2
        edw, epw = (seg[t] >> 32) & 0xFFFF, (seg[t] >> 48) & 0xFFFF
        if n * (edw + epw) != count:
            raise EncodingError(f"word {src_at}: composite list size mismatch")
        elems = [t + 1 + i * (edw + epw) for i in range(n)]
        dw = max((trim(seg[e:e + edw]) for e in elems), default=0)
        pw = max((trim(seg[e + edw:e + edw + epw]) for e in elems), default=0)
        out.append(n << 2 | dw << 32 | pw << 48)
        for e in elems:
            out.extend(seg[e:e + dw])
            out.extend([0] * pw)
        out[dst_at] = list_ptr(at - dst_at - 1, 7, n * (dw + pw))
        for k, e in enumerate(elems):
            for i in range(pw):
                _copy(seg, e + edw + i, out, at + 1 + k * (dw + pw) + dw + i)
        return
    if size == 6:  # pointer list
        out.extend([0] * count)
        out[dst_at] = list_ptr(at - dst_at - 1, 6, count)
        for i in range(count):
            _copy(seg, t + i, out, at + i)
        return
    bits = count * LIST_BITS[size]
    words = (bits + 63) // 64
    raw = 0
    for i in range(words):
        raw |= seg[t + i] << (64 * i)
    raw &= (1 << bits) - 1  # zero the padding past the last element
    out.extend((raw >> (64 * i)) & MASK64 for i in range(words))
    out[dst_at] = list_ptr(at - dst_at - 1, size, count)


SLOT_BITS = {
    "void": 0, "bool": 1, "int8": 8, "uint8": 8, "int16": 16, "uint16": 16,
    "enum": 16, "int32": 32, "uint32": 32, "float32": 32, "int64": 64,
    "uint64": 64, "float64": 64,
}
NO_DISCRIMINANT = 0xFFFF


def struct_nodes(schema):
    """Top-level struct and enum nodes by id, plus the group nodes of named
    unions (laid out in their parent's data and pointer sections)."""
    nodes = {}
    for name in dir(schema):
        try:
            decl = getattr(schema, name).schema
            node = decl.node
        except AttributeError:
            continue
        if node.which in ("struct", "enum"):
            nodes[node.id] = node
        if node.which == "struct":
            for f in node.struct.fields:
                if f.which == "group":
                    group = decl.fields[f.name].schema.node
                    nodes[group.id] = group
    return nodes


def encoding_problems(schema, root, seg):
    """Unused bits zero, declared discriminants, field presence."""
    nodes = struct_nodes(schema)
    problems = []
    try:
        _walk_struct(nodes, root, seg, 0, root.displayName.split(":")[-1],
                     problems)
    except (EncodingError, IndexError) as exc:
        problems.append(str(exc) or "pointer out of bounds")
    return problems


def _walk_struct(nodes, node, seg, at, path, problems):
    p = pointer(seg, at)
    if p is None or p[0] != 0:
        raise EncodingError(f"{path}: expected a struct pointer")
    _check_struct(nodes, node, seg, p[1], p[2], p[3], path, problems)


def _check_struct(nodes, node, seg, base, dw, pw, path, problems):
    data = 0
    for i in range(dw):
        data |= seg[base + i] << (64 * i)
    used, used_ptrs = _check_fields(nodes, node, seg, base, dw, pw, data,
                                    path, problems)
    stray = data & ~used & ((1 << (64 * dw)) - 1)
    if stray:
        problems.append(f"{path}: non-zero unused data bits "
                        f"(mask {stray:#x})")
    for i in range(pw):
        if i not in used_ptrs and seg[base + dw + i] != 0:
            problems.append(f"{path}: pointer slot {i} outside the layout "
                            "is not null")


def _check_fields(nodes, node, seg, base, dw, pw, data, path, problems):
    """Checks one struct's (or named union's) fields over its parent's
    sections; returns the data bits and pointer slots its layout uses."""
    s = node.struct
    used, used_ptrs = 0, set()
    which = None
    if s.discriminantCount:
        bit = s.discriminantOffset * 16
        which = (data >> bit) & 0xFFFF
        used |= 0xFFFF << bit
        declared = {f.discriminantValue for f in s.fields
                    if f.discriminantValue != NO_DISCRIMINANT}
        if which not in declared:
            problems.append(f"{path}: undeclared discriminant {which}")
    for f in s.fields:
        in_union = f.discriminantValue != NO_DISCRIMINANT
        if in_union and f.discriminantValue != which:
            continue
        fpath = f"{path}.{f.name}"
        if f.which == "group":
            if in_union:
                raise EncodingError(f"{fpath}: group inside a union")
            g_used, g_ptrs = _check_fields(nodes, nodes[f.group.typeId], seg,
                                           base, dw, pw, data, fpath, problems)
            used |= g_used
            used_ptrs |= g_ptrs
            continue
        t = str(f.slot.type.which)
        if t in SLOT_BITS:
            width = SLOT_BITS[t]
            used |= ((1 << width) - 1) << (f.slot.offset * width)
            continue
        idx = f.slot.offset
        used_ptrs.add(idx)
        present = idx < pw and seg[base + dw + idx] != 0
        ptr_at = base + dw + idx
        if t == "list":
            if present:
                _check_list(nodes, f.slot.type.list.elementType, seg,
                            ptr_at, fpath, problems)
            continue
        if not present:
            problems.append(f"{fpath}: must be written"
                            + (" (selected variant)" if in_union else ""))
            continue
        if t == "struct":
            _walk_struct(nodes, nodes[f.slot.type.struct.typeId], seg,
                         ptr_at, fpath, problems)
        elif t != "text":
            raise EncodingError(f"{fpath}: unsupported field type {t}")
    return used, used_ptrs


def _check_list(nodes, elem_type, seg, at, path, problems):
    kind, t, size, count = pointer(seg, at)
    if kind != 1:
        raise EncodingError(f"{path}: expected a list pointer")
    if elem_type.which != "struct" or size != 7:
        raise EncodingError(f"{path}: unsupported list element type")
    n = (seg[t] & 0xFFFFFFFF) >> 2
    if n == 0:
        problems.append(f"{path}: empty list must be null")
    edw, epw = (seg[t] >> 32) & 0xFFFF, (seg[t] >> 48) & 0xFFFF
    node = nodes[elem_type.struct.typeId]
    for i in range(n):
        _check_struct(nodes, node, seg, t + 1 + i * (edw + epw), edw, epw,
                      f"{path}[{i}]", problems)


# ---------------------------------------------------------------------------
# Manifest completeness: a manifest input lists every field that differs from
# its default, so the decoded message must equal it exactly — what lets an
# independent encoder rebuild each vector from the manifest alone.
# ---------------------------------------------------------------------------

def matches_input(nodes, node, reader, expected, path, problems):
    fields = list(node.struct.fields)
    known = {f.name for f in fields}
    for key in expected:
        if key not in known:
            problems.append(f"{path}.{key}: not a field of the schema")
    union = [f for f in fields if f.discriminantValue != NO_DISCRIMINANT]
    variant = None
    if union:
        named = [f.name for f in union if f.name in expected]
        if len(named) > 1:
            problems.append(f"{path}: input names several variants {named}")
        variant = named[0] if named else min(
            union, key=lambda f: f.discriminantValue).name
        try:
            which = str(reader.which)
        except capnp.KjException:  # undeclared discriminant
            which = "<undeclared>"
        if which != variant:
            problems.append(f"{path}: variant {which}, input says {variant}")
            return
    for f in fields:
        if f.discriminantValue != NO_DISCRIMINANT and f.name != variant:
            continue
        fpath = f"{path}.{f.name}"
        if f.which == "group":  # named union: same rules, nested input
            matches_input(nodes, nodes[f.group.typeId], getattr(reader, f.name),
                          expected.get(f.name, {}), fpath, problems)
            continue
        t = str(f.slot.type.which)
        if t == "void":
            continue
        actual = getattr(reader, f.name)
        if t == "struct":
            matches_input(nodes, nodes[f.slot.type.struct.typeId], actual,
                          expected.get(f.name, {}), fpath, problems)
        elif t == "list":
            items = expected.get(f.name, [])
            if len(actual) != len(items):
                problems.append(f"{fpath}: {len(actual)} elements, "
                                f"input has {len(items)}")
                continue
            elem = nodes[f.slot.type.list.elementType.struct.typeId]
            for i, (a, e) in enumerate(zip(actual, items)):
                matches_input(nodes, elem, a, e, f"{fpath}[{i}]", problems)
        else:
            if t == "enum":
                enum = nodes[f.slot.type.enum.typeId].enum
                default = enum.enumerants[0].name
                actual = str(actual)
            else:
                default = "" if t == "text" else False if t == "bool" else 0
            want = expected.get(f.name, default)
            if actual != want:
                problems.append(f"{fpath}: {actual!r}, input says {want!r}")


expected_type = {
    "discovery-minimal": 0, "discovery-channels": 0,
    "motion-pose": 1, "motion-channels": 1, "motion-multi": 1,
    "motion-bodydynamics": 1, "event-impact": 2,
    "discovery-gravity-vector": 0, "motion-local-gravity": 1,
    "motion-local-gravity-zero": 1,
    "discovery-paged-p0": 0, "discovery-paged-p1": 0,
    "motion-parts-p0": 1, "motion-parts-p1": 1,
    "discovery-identity": 0, "motion-wheel": 1,
}


if __name__ == "__main__":
    main()
    print(f"conformance: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)
