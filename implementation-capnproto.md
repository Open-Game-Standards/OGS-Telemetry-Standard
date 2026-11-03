# Cap'n Proto Implementation

The OGS-TS uses [Cap'n Proto](https://capnproto.org/) as its data format. Cap'n Proto is a zero-copy, binary serialization format optimized for speed and efficiency, making it an excellent choice for sending motion telemetry data over UDP. It avoids encoding/decoding overhead by using a memory-aligned layout, and it supports optional fields, nested structures, and tagged unions efficiently.

For the design behind the schema — the two frames and why metadata and samples are separated — see [DESIGN.md](DESIGN.md). This page covers working with the schema in practice.

## The schema

The schema lives in [`ogs_telemetry.capnp`](ogs_telemetry.capnp) and defines two root messages:

- **`DiscoveryFrame`** — sent once per session and re-sent whenever anything it describes changes. Declares the game, session anchor, environment, and per object: drive-point descriptors (geometry, suspension) and channel descriptors (id, name, unit, range, value type).
- **`MotionFrame`** — sent at the telemetry rate (~60 Hz). Carries the pose core plus drive-point state and channel values, all keyed by the ids declared in discovery.

Compile it for C++:

```bash
capnp compile -oc++ ogs_telemetry.capnp
```

This generates `ogs_telemetry.capnp.h` and `ogs_telemetry.c++`.

## Message framing (normative)

A datagram's Cap'n Proto payload is in the standard serialization format:
a segment table followed by the segments. The table is a `u32` segment
count minus one, then one `u32` word-size per segment, padded with zeros
to an **even u32 count** (so a 1-segment table is exactly one word — 8
bytes — with no additional padding). Messages are single-segment in
practice; multi-segment is legal but unnecessary at OGS-TS frame sizes.
This is the standard Cap'n Proto stream framing: messages built by
official capnp implementations (C++, Rust, Go, Python…) are valid OGS-TS
payloads as-is.

## Encoding rules (normative)

These rules keep unused bits free for schema evolution and give every
message exactly one encoding, so independent encoders can be compared
byte for byte against the [conformance corpus](conformance/).

An **optionality union** is a union whose first-declared variant is a
`Void` default meaning "not provided" (`noDynamics`, `noRange`,
`noSuspension`, `noDirection`, `noForce`, `noThrust`, `core`,
`noGravityVector`, `noLocalGravity`, `noAtmosphere`, `noTyre`, and every
`WheelState` measurement's `no…` variant). Its
default variant therefore has discriminant 0. `DrivePoint`,
`DrivePointDescriptor` and `ChannelValue` carry the other unions.

### Senders MUST

- **Emit valid Cap'n Proto** for `ogs_telemetry.capnp`, framed as above.
- **Zero every unused bit.** Data bits that belong neither to a non-union
  field, nor to the union discriminant, nor to the selected variant are
  zero; pointer slots outside that layout are null. This covers struct
  padding and the storage of unselected variants. v1.x fields are
  allocated in currently unused bits, so a stray bit there decodes as a
  value of a future field.
- **Use declared discriminants only.** A union discriminant is the number
  of a declared variant. A sender with nothing to report for an
  optionality union leaves it zero-initialized, which selects the `Void`
  default — every official Cap'n Proto builder does this automatically.

### Senders SHOULD: canonical OGS encoding

Encode conformance (byte comparison with the corpus) requires these
rules, and every reference encoder follows them.

- **Canonical form**, as defined by the Cap'n Proto
  [encoding spec](https://capnproto.org/encoding.html#canonicalization):
  a single segment; objects in preorder; trailing zero data words and
  trailing null pointers truncated (in a struct list, only when zero in
  every element); a pointer to a zero-sized struct has offset −1.
- **Field presence:**
  - non-union `Text` fields are always written, `""` included;
  - non-union struct fields are always written, all-zero included;
  - list fields are written when non-empty and left null when empty;
  - a union variant with a pointer payload is written exactly when it is
    selected.

Official Cap'n Proto libraries emit valid but generally non-canonical
messages. To byte-match the corpus with one, set every non-union `Text`
and struct field explicitly, initialize no empty lists, then canonicalize
before framing — in C++ `capnp::MessageReader::canonicalize()`, or from
the command line `capnp convert binary:canonical`. Canonical output has no
segment table; prepend the one-segment table described above.

### Receivers MUST

- **Accept any valid Cap'n Proto message**, canonical or not, single- or
  multi-segment.
- **Read a null pointer as the field's default**: empty text, empty list,
  all-zero struct.
- **Never fail on an unknown discriminant.** For an optionality union,
  treat it as the `Void` default (`noDirection` ≡ omnidirectional,
  `noForce` ≡ force not available). For any other union, ignore the
  union's content and keep the struct's non-union fields.

## The minimal sender

The smallest compliant stream is one object with pose only — no drive points,
no channels (~68 bytes per frame). A motion platform can already drive from
this; everything else in the standard is additive:

```cpp
// --- once per session -------------------------------------------
::capnp::MallocMessageBuilder dmsg;
DiscoveryFrame::Builder d = dmsg.initRoot<DiscoveryFrame>();
d.setSchemaVersion(1);
d.setGameName("MyGame");
d.setSessionStartUnixUs(1759843200000000ULL);
d.initObjects(1)[0].setName("player");
// send as frame type 0x00 (see implementation-udp.md)

// --- every tick, ~60 Hz ------------------------------------------
::capnp::MallocMessageBuilder mmsg;
MotionFrame::Builder f = mmsg.initRoot<MotionFrame>();
f.setTimestamp(t);                    // seconds since session start
MotionObject::Builder obj = f.initObjects(1)[0];
obj.setName("player");
obj.initPosition().setX(x); obj.getPosition().setY(y); obj.getPosition().setZ(z);
auto q = obj.initOrientation();       // unit quaternion: OGS-TS world -> object
q.setX(0.0f); q.setY(0.0f); q.setZ(0.0f); q.setW(1.0f);  // identity
// send as frame type 0x01
```

Add drive points and channels later as needed — they are declared in
discovery and keyed by id, so they never complicate the motion tick.

## Building a DiscoveryFrame

The discovery frame is where a game declares everything about its telemetry: what objects it streams, what drive points they have, and what channels exist. This example declares a racing-style player car with four wheels and three channels:

```cpp
#include "ogs_telemetry.capnp.h"
#include <capnp/message.h>

kj::Array<capnp::word> buildDiscovery() {
    ::capnp::MallocMessageBuilder message;
    DiscoveryFrame::Builder d = message.initRoot<DiscoveryFrame>();

    d.setSchemaVersion(1);
    d.setGameName("RacingSim");
    d.setSessionStartUnixUs(1759843200000000ULL); // wall-clock anchor

    Environment::Builder env = d.initEnvironment();
    env.setGravity(9.81f);       // m/s^2
    env.setMedium(ContactMedium::ASPHALT);
    auto air = env.getAtmosphere().initKnown(); // leave unset without an atmosphere model
    air.setAirDensity(1.225f);   // kg/m^3
    air.setTemperature(20.0f);   // °C
    air.setPressure(101325.0f);  // Pa

    auto objects = d.initObjects(1);
    ObjectDescriptor::Builder car = objects[0];
    car.setName("player_car");
    car.setType(ObjectType::VEHICLE);
    car.setTypeLabel("Formula-style racer");   # optional, display-only
    car.setPrimary(true);                     # reference object for rigs
    car.setLocation("spa");

    // Reference point: where reported pose/dynamics are measured.
    // Default (unset) = the object-local frame origin (typically the CG).
    // Senders measuring elsewhere declare it so consumers can apply
    // lever-arm corrections to their own pivot/head position.
    NamedPoint::Builder ref = car.initReferencePoint();
    ref.setName("cg");
    ref.initPosition().setZ(-1.2f);   // CG 1.2 m behind origin, vehicle-local

    // Drive points: four wheels with geometry and suspension
    auto points = car.initDrivePoints(4);
    const char* names[4] = {"wheel_fl", "wheel_fr", "wheel_rl", "wheel_rr"};
    for (int i = 0; i < 4; i++) {
        auto p = points[i];
        p.setId(i);
        p.setName(names[i]);
        p.initOffset().setX(-0.8f);  // tune per corner; y/z omitted for brevity
        auto wheel = p.initWheel();
        wheel.setRadius(0.34f);
        wheel.setDriven(true);
        wheel.setSteered(i < 2);
        auto susp = wheel.initSuspension();   // optional: skip = noSuspension
        susp.initTravel().setMin(-0.05f);  // meters
        susp.getTravel().setMax(0.15f);
        susp.setStiffness(65000.0f);       // N/m
        susp.setDamping(5000.0f);          // N·s/m (0 = unspecified)
    }

    // Channels: any datapoint the game wants to expose, self-describing.
    // Ratified names from CHANNELS.md auto-map in receivers — use them when
    // the concept matches.
    auto channels = car.initChannels(3);
    auto rpm = channels[0];
    rpm.setId(0).setName("engine.rpm").setUnit("rpm");
    rpm.initRange().setMin(0).setMax(9000);
    rpm.setDescription("Engine revolutions per minute");
    auto gear = channels[1];
    gear.setId(1).setName("transmission.gear").setUnit("");
    gear.initRange().setMin(-1).setMax(6);
    auto lights = channels[2];
    lights.setId(2).setName("lights.headlights").setUnit("");
    lights.setDescription("Headlights on/off");

    return capnp::messageToFlatArray(message);
}
```

A flight sim would declare propeller drive points (`initPropeller()` with diameter/blades) and channels like `engine.throttle` or `altitude` — same mechanism, different vocabulary. Games with exotic mechanics can leave drive points `generic` and expose everything as channels.

## Building a MotionFrame

The motion frame is intentionally cheap to build — bare values keyed by discovery ids:

```cpp
kj::Array<capnp::word> buildMotion(double timestampSeconds) {
    ::capnp::MallocMessageBuilder message;
    MotionFrame::Builder f = message.initRoot<MotionFrame>();

    f.setTimestamp(timestampSeconds); // seconds since session start

    auto objects = f.initObjects(1);
    MotionObject::Builder car = objects[0];
    car.setName("player_car");

    // Pose core — the required minimal set (left-handed, Z-forward, Y-up)
    car.initPosition().setX(1.5f);  // …setY/setZ similarly
    auto q = car.initOrientation(); // unit quaternion, OGS-TS world -> object axes
    q.setZ(0.0f); q.setW(1.0f);     // identity; …setX/setY for actual rotation
    // dynamics is optional — omit it and receivers derive velocity/
    // acceleration from pose deltas (send obj.initKinematics() for world
    // velocity+acceleration, or obj.initBodyDynamics() for accelerometer-
    // style specific force + angular rates — whichever you measure natively)

    // Drive-point state: only points with state this tick
    auto points = car.initDrivePoints(4);
    for (int i = 0; i < 4; i++) {
        auto p = points[i];
        p.setId(i);
        WheelState::Builder w = p.initWheel();
        // every measurement is its own named union: set what you measure,
        // leave the rest unset (never 0 for "unknown")
        w.setContact(ContactMedium::ASPHALT);
        w.getRpm().setValue(1200.0f + i * 10.0f);
        w.getSlip().setValue(0.01f);           // slip ratio
        w.getCompression().setValue(0.04f);    // meters
        w.getTorque().setValue(850.0f);        // Nm
        if (i < 2) w.getSteerAngle().setValue(0.02f); // rad, + = right (C-4)
        w.getLoadForce().setValue(4200.0f);    // N along suspension axis
        auto tyre = w.initTyre();              // pressure, temperature, wear together
        tyre.setPressure(110000.0f);           // Pa
        tyre.setTemperature(88.0f);            // degC carcass
        tyre.setWear(0.97f);                   // 1 = new
    }

    // Channel values: typed, keyed by discovery ids
    auto values = car.initChannels(3);
    values[0].setId(0).setNumber(7800.0f);   // engine.rpm
    values[1].setId(1).setNumber(4.0f);      // transmission.gear
    values[2].setId(2).setBoolean(true);     // lights.headlights

    return capnp::messageToFlatArray(message);
}
```

## Reading frames

Deserialize with `FlatArrayMessageReader`. The frame type is identified by the transport envelope (a frame-type byte in the UDP header — see [implementation-udp.md](implementation-udp.md)), so a receiver knows which root type to expect:

```cpp
#include "ogs_telemetry.capnp.h"
#include <capnp/serialize.h>

void onDiscovery(kj::ArrayPtr<const capnp::word> words) {
    ::capnp::FlatArrayMessageReader message(words);
    DiscoveryFrame::Reader d = message.getRoot<DiscoveryFrame>();

    // Build the id -> descriptor maps your UI/rig needs:
    // channel names, units, ranges for gauges; drive-point geometry
    for (ObjectDescriptor::Reader obj : d.getObjects()) {
        for (ChannelDescriptor::Reader ch : obj.getChannels()) {
            // ch.getName(), ch.getUnit(), ch.hasRange() ? ch.getRange().getMax()…
        }
    }
}

void onMotion(kj::ArrayPtr<const capnp::word> words) {
    ::capnp::FlatArrayMessageReader message(words);
    MotionFrame::Reader f = message.getRoot<MotionFrame>();

    for (MotionObject::Reader obj : f.getObjects()) {
        // obj.getPosition(), obj.getOrientation() …
        for (ChannelValue::Reader v : obj.getChannels()) {
            switch (v.which()) {
                case ChannelValue::NUMBER:  /* v.getNumber() */ break;
                case ChannelValue::BOOLEAN: /* v.getBoolean() */ break;
            }
        }
        for (TextValue::Reader t : obj.getTexts()) { /* t.getId(), t.getText() */ }
        for (DrivePoint::Reader p : obj.getDrivePoints()) {
            if (p.which() == DrivePoint::WHEEL) {
                WheelState::Reader w = p.getWheel();
                // w.getRpm(), w.getContact() …
            }
        }
    }
}
```

Cap'n Proto requires 8-byte word alignment — the UDP envelope is 8 bytes, so a payload starting at offset 8 is already word-aligned (see the UDP receiver example).

## Wire size

- `MotionFrame`, one object, pose only: ~68 bytes.
- Four wheels (every measurement and the tyre) + eight channels ≈ +490 bytes — comfortably within the mandatory 1,400-byte datagram budget at 60 Hz.
- `DiscoveryFrame`: ~300–800 bytes for a typical sender, re-sent every 2 s — strings dominate, so declare channels generously; they cost nothing per frame. A channel descriptor costs roughly 50–120 bytes (name, unit and description dominate), so one page holds ~10–25 channels; larger sets are paged.
- Simulator-scale senders (hundreds of channels, multi-car grids) stay within the budget through paged discovery, motion parts and bounded refresh ([implementation-udp.md](implementation-udp.md) § Datagram budget).

The equivalent self-describing-per-frame JSON would be several times larger on every packet.

## Evolution rules

- **Adding fields or variants (v1.x):** receivers built against an older schema skip unknown fields and unknown union discriminants silently — no coordination needed.
- **Optional data:** optionality is carried by union discriminants (`noDynamics`/`core`/`noRange`/`noSuspension`/…), never by null struct fields — inline struct fields are not nullable in Cap'n Proto. Pointer fields (text, lists, union struct members like `range`, `suspension`) do have `hasX()` accessors; check them or the discriminant before use.
- **Unset unions:** an optionality union a sender never touches is zero-initialized, which is its `Void` default. Receivers skip unknown discriminants as described in [Encoding rules](#encoding-rules-normative).
- **Adding channels or drive points:** change the `DiscoveryFrame` (a new `generation`) and re-send it; receivers key by id and simply see new entries.
- **Removing or renumbering ids:** never mid-session — ids are the contract between discovery and motion frames.

## Library layer

For the high-level C API and the transport abstraction that hides Cap'n Proto entirely — including discovery handling and envelope framing — see [implementation-udp.md](implementation-udp.md).
