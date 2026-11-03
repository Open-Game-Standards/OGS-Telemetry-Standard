# OGS-TS Schema v1: Two-Layer Design

Status: current (v1.0). Authoritative schema: `ogs_telemetry.capnp`.

## 1. Goals

The schema serves the OGS-TS requirements:

- Minimal, easily understood required telemetry: a game implementing just the
  pose core is compliant.
- Generic across game domains (racing, flight, marine, spacecraft, mechs); no
  domain's vocabulary is hardcoded into the structure.
- A structured extension mechanism: developers can add any telemetry datapoint
  as a well-documented, typed channel without schema changes.
- Network efficient and low latency; fits a UDP MTU at 60 Hz.
- Works on console and PC; read-only (the game never accepts input data).
- Supports multiple local clients (dashboards, motion rigs, haptics, loggers)
  without extra ports or proxying, via multicast.

Coordinate system and wire conventions (normative) are defined once in
[CONVENTIONS.md](CONVENTIONS.md) (frames, quaternion policy, units plus the
declared-exception whitelist, rotation signs, control-input signs, value
identity, wind convention, timestamps, precision). Design rationale:

- **Left-handed world** (Z-forward, Y-up): engine-native for
  Unity/DirectX/Unreal, the largest sender population; consumers are
  quaternion-native and take the frame as declared.
- **One closed conventions layer**: every angular quantity shares one
  sign sense (positive rotation = positive yaw direction: steering + =
  right), every unit is SI or on a short whitelist (°C, rpm), and what a
  value measures is fixed by where it lives (driver inputs are `ctrl.*`
  channels; `steerAngle` is the road wheel, not the handwheel).
  Per-field comments cite clause numbers (e.g. `C-3`, `C-4`).

## Non-goals (current scope)

- **Write-back / commands.** OGS-TS is read-only game → software in v1, a
  deliberate choice at this stage, however one that remains open
  to change through discussion with game developers. The rationale:
  a wire that can command the game is a cheat vector for competitive
  titles, and commands need reliable, ordered, consented delivery; lossy
  multicast telemetry must not carry them. MSFS itself treats writing
  as a separate mechanism (input key events / gauge RPN), not a property
  of the telemetry surface, and per-variable writability is not uniformly
  marked.

### Write back

If write-back is ever adopted, the impact splits into a cheap part and an
expensive part, and the standard keeps them separate.

**Cheap: writability as discovery metadata.** "The game specifies which
fields are writable" is metadata, and discovery is where metadata lives:
a descriptor union variant (`ro` / `rw` plus rate limit, trigger-vs-level
semantics) advertises what *could* be written. This fits the two-layer
doctrine unchanged and gives tools auto-configuration without per-game
plugins. Advertisement alone carries no obligation; a sender may declare
`rw` channels while no write profile is active.

**Expensive: the write path itself.** Writes have requirements the read
path structurally lacks:

| Requirement | Why the read path can't carry it |
|---|---|
| Reliability & ordering | A dropped or reordered command is a silently wrong state; multicast fire-and-forget has neither |
| Addressing | Multicast reaches everyone; a write must reach *the sender* (unicast endpoint advertised in discovery) |
| Authorization | Any process can join a multicast group; without a handshake/keys, writable = any local process drives the game |
| Feedback | Accepted/rejected/out-of-range, applied-when; a command/response protocol (RPC) with round-trip timing motion loops may not tolerate |
| Precedence | Game logic vs. writer conflicts need a per-field concurrency contract |

Any future command surface therefore will be a separate opt-in profile
on its own endpoint with its own handshake, never a flag on the telemetry
wire. Costs to budget when that day comes: the transport and conformance
surface roughly doubles (negative tests: unauthorized, stale, out-of-range,
racing writes), and evolution rules apply. Removing a *readable* channel
is survivable (receivers skip unknowns); removing a *writable* one breaks
consumers, so writables become compatibility-bound API surface.

**Scope note: writes are tooling, not motion.** The realistic write use
cases (time control, teleport/reposition, session and weather setup,
camera moves for capture) are tool operations, not motion operations.
Even force feedback needs no writes-to-game: torque flows game →
middleware on the existing read path (`ctrl.ffb.torque`), and middleware →
wheel is USB. A future write profile is best understood as a sibling
control protocol that shares OGS-TS's discovery vocabulary, not as telemetry
becoming bidirectional.

## 2. Core idea: two layers

Telemetry data divides cleanly into two kinds with different change rates:

- **What a channel IS**: name, type, unit, valid range, geometry. Changes
  never or rarely.
- **What a channel reads**: the sample. Changes every frame.

Repeating metadata per frame bloats the wire; deleting it loses
self-description. The standard therefore defines two frames with separate
cadences:

| Frame | Cadence | Contents |
|---|---|---|
| `DiscoveryFrame` | once per session, re-sent on change | game name, session anchor, instance identity (label, host), environment, object descriptors, drive-point descriptors (suspension spec rides WheelSpec), channel descriptors (id, name, unit, range, description, value type) |
| `MotionFrame` | ~60 Hz | timestamp, per-object pose (position, orientation quaternion), optional velocity/acceleration, drive-point state (typed union), channel values (id + number or boolean), text values (id + text) |
| `EventFrame` | on demand | discrete stimuli for haptics/cueing: id, name, intensity, duration, optional body-frame direction; redundancy by short replay + id dedup (CONVENTIONS C-10) |

This is the same split as motorsport CAN + DBC files: declare the signal
dictionary once, stream bare values. Senders key everything by `UInt16` ids
assigned in discovery; receivers that miss a descriptor wait for the next
discovery re-send. A dictionary too large for one datagram is paged, and a
tick too large for one datagram is sent in parts (§ 6).

## 3. Frame structure

`DiscoveryFrame` describes the session:

- `schemaVersion`: `1` for this schema.
- `gameName`, `sessionStartUnixUs`: wall-clock anchor; frame timestamps are
  seconds relative to it.
- `environment`: ambient conditions of the simulation medium (air density,
  temperature, pressure, gravity magnitude with an optional world-frame
  gravity vector, and the dominant medium, `ContactMedium`). Objects whose
  gravity differs per position or per frame carry `localGravity` in the
  motion frame instead (CONVENTIONS C-12).
- `objects`: one `ObjectDescriptor` per streamed object (the `primary`
  flag marks the reference object). Each carries identity (`name`, `type`,
  `location`; `type` is a ratified `ObjectType` enum plus optional
  `typeLabel` for display), `referencePoint` and `namedPoints`,
  `DrivePointDescriptor`s, and `ChannelDescriptor`s (below).
- One **object-local frame** per object: drive-point offsets and named
  points share a single sender-chosen origin (typically the CG, otherwise
  the model origin); `MotionObject.position` is the world position of the
  declared `referencePoint`. Consumers only use differences between
  declared points, which are frame-invariant.
- `referencePoint` (the object-local point the reported pose and dynamics
  are measured at; default = the object-local frame origin, typically the
  CG) and `namedPoints` (other named points such as `cg`, `pilot`,
  `driverEye`) let consumers correct motion to their own pivot/head
  position with the lever-arm terms `a + α×r + ω×(ω×r)`; the correction
  itself is consumer-side. Suspension geometry rides `WheelSpec`.

`MotionFrame` carries the samples:

- `timestamp`: seconds since session start.
- `objects`: one `MotionObject` per descriptor: pose core (position and an
  orientation quaternion, the required minimal set), optional dynamics
  (world `kinematics` or body `bodyDynamics`), and per-tick drive-point
  state and channel values, keyed by the discovery ids.

Drive points are typed on both sides: the descriptor carries static geometry
(suspension travel/stiffness, wheel radius/driven/steered, propeller
diameter/blades) in a union; the motion frame carries the matching dynamic
state (`WheelState`, `PropellerState`, `JetState`, `SailState`, `LegState`,
`WingState`, `GenericState`) in a parallel union.

## 4. The extension mechanism

`ChannelDescriptor` + `ChannelValue` are the standard's extension point:

- A sender declares any datapoint it wants to expose (`engine.rpm` with unit
  `rpm` and a range, `headlights` as a boolean, `gear` as a number) and then
  streams bare values keyed by the descriptor's id.
- Receivers can render, normalize, and range-check channels without any prior
  knowledge of the game: unit, min/max and value type come from the
  descriptor; numbers and booleans ride `ChannelValue`, text rides
  `TextValue`.
- Drive points without a dedicated variant use `generic`: the descriptor states
  the geometry it can, and actual values travel as named channels.

New drive-point variants and new descriptor fields can be added in v1.x without
breaking deployed receivers (see §7).

### Consumer classes

The wire shape obligates consumers to very little, so non-motion devices are
first-class consumers alongside motion rigs:

- **Motion rigs / cueing**: pose core + drive points (the original shape).
- **Haptics (vests, transducers)**: pose core + channels; `EventFrame` for
  discrete stimuli (impacts, gunfire); drive points ignored.
- **FFB middleware**: torque/deflection channels the game publishes
  (`ctrl.ffb.torque`); still read-only telemetry, never commands to the game.
- **Dashboards / loggers / tooling**: channels + session values.

A minimal sender is one object (name + position + orientation) plus whatever
channels/events it has; drive points are optional. Creature senders (horse,
dragon) use the same core: `ObjectType.creature`, legs via `leg`, wings via
`wing` (also ornithopters), everything else `generic` + labels. Undulating
bodies (snake, eel) have no per-segment drive points; spine detail rides
channels if a game ever exposes it.

## 5. Key decisions and rationale

- **Cap'n Proto over a hand-rolled fixed-layout struct.** The obvious
  alternative, pack fields into a struct and send it raw over UDP, is
  what most existing sim telemetry already does, and it fails on
  a core capability this standard needs. A struct has no schema evolution:
  adding a channel changes the layout, so every receiver breaks or must
  special-case a version. It has no cross-language/cross-compiler
  portability without hand-maintained offset tables (padding, alignment,
  and endianness are compiler- and platform-specific). And it has no safe
  optional or variable-length data: every optional field breaks things and every string is a fixed buffer, or the parser hand-
  rolls variable layout itself. Cap'n Proto keeps the one
  property a struct has that matters here, no parse step and read in place, 
  while adding schema evolution (unknown-field/union-discriminant
  skipping, §8), portability (one schema, codegen per language), and real
  optional/variable data (unions, lists, text) as first-class. The cost is
  a schema compiler and a codegen step in the build, once per engine (see
  `implementation-capnproto.md`); for a standard meant to outlive any one
  game's telemetry struct, this is the correct choice.
- **Channel ids over per-frame names.** Names in every frame repeat ~10 bytes
  per channel per tick; ids cost 2 bytes. Discovery keeps names durable and
  human-readable where it is cheap. Ids are sender-assigned per object, stable
  for the session; discovery re-sends reset nothing (receivers key purely by
  id).
- **Unions for drive points.** Cap'n Proto unions give cheap tagged variants;
  unknown-union discriminants are skipped by old decoders, so new point types
  (e.g. `hoverFan`) can be added in v1.x without breaking deployed receivers.
- **Typed channel values.** Booleans (headlights, wipers) and text (mode labels)
  are first-class, not abused floats. Text at high rate is discouraged by
  comment, not banned; dashboards sometimes need label changes. The
  descriptor declares the value type, so a receiver can lay out and bind a
  channel before its first value; a value whose variant differs from a
  declared type is dropped. Text values ride their own `TextValue` lists
  (`texts` beside `channels` and session `values`), so `ChannelValue` is
  data only and a list of numbers and booleans costs 8 bytes per value.
- **Two channel cadences.** Custom datapoints come in two speeds, and the
  layer follows the cadence (the same principle that splits discovery from
  motion):
  - *Streamed channels*: fast-changing values (tyre temps, boost pressure,
    assist states) ride `MotionObject.channels` per tick. Absence means
    unchanged: receivers keep the latest known value per id. A sender that
    carries only changed values re-sends every value within each 2-second
    discovery interval (bounded refresh), so late joiners converge within
    that interval.
  - *Session channels*: rarely-changing values (setup, session type, stage
    name, weather preset, labels) carry their current value in
    `ObjectDescriptor.values` (text channels in `texts`). A change re-sends discovery, so a receiver
    that joins mid-session learns every session value from discovery alone;
    the delta stream never strands late joiners. This is where text labels
    naturally live.

  A channel lives in one layer; moving it between layers is a discovery
  change. Session-scoped datapoints that belong to the session rather than
  any object (server name, weather) attach to the primary object's channel
  set. (Validation: [13-extensibility.md](validation/13-extensibility.md).)
- **Optional dynamics, one native representation.** Senders provide
  whichever dynamics representation they measure natively: world-space
  `kinematics` (velocity + acceleration) or body-frame `bodyDynamics`
  (specific force + angular rates, the accelerometer-class source pattern
  and the direct input of washout cueing). Receivers convert between the
  two using orientation and the object's effective gravity (CONVENTIONS
  C-12). Absence is the union's `Void` default (Cap'n Proto
  struct fields are inline, not nullable); there are no sentinels, and
  zeros are real readings.
- **Discovery re-send on change.** Vehicle swap, channel set change, or medium
  change (air → water) re-sends the whole `DiscoveryFrame` (every page) under
  a new `generation`. Idempotent by design.
- **Paged discovery and generations.** A descriptor set larger than one
  datagram is split into self-contained pages of one `generation`;
  receivers merge them by object name and id, and use each page on arrival.
  Motion frames name the generation their ids refer to, so a vehicle swap
  never misreads ids while the new pages are in flight. Paging stays inside
  the protocol: plain multicast, no reassembly buffers, no side channel, and
  a lost page delays only its own descriptors.
- **Motion parts keep pose first.** A tick too large for one datagram goes
  out in parts sharing a timestamp. Pose, dynamics and drive points ride the
  first part listing each object, so motion consumers never wait on channel
  volume.
- **Ranges in descriptors, not per frame.** Min/max per descriptor restores
  sane error handling (clients drop out-of-range values) without paying the
  cost on every frame.
- **Coordinate system.** Left-handed, Z-forward, Y-up, world space.
- **Orientation as a unit quaternion.** The pose core carries `position` +
  `orientation` (`Quaternion`, x/y/z/w, unit norm, either sign; rotates OGS-TS
  world axes into object body axes). Chosen over a forward/up vector pair
  because the primary consumers (motion-control/cueing and
  motion-compensation software) work natively in quaternions, and
  interpolation across packet loss (`slerp`/`nlerp`) is the boring standard
  path. Decided pre-release, so no representation duality exists (no
  optional vector pair, no receiver-side basis conversion).
- **`ObjectType` is a ratified enum, not free text.** Receivers (notably
  motion-control software selecting a cueing preset) can switch on it
  reliably; free text (`"Car"` vs `"car"` vs `"F1"`) forces receiver-side
  guessing. The set stays coarse (vehicle / aircraft / watercraft /
  spacecraft / humanoid / camera / creature / other) because fine-grained
  domain hints already live in the drive-point union. Unknown enumerants
  survive round-trips (`UInt16` on the wire), so new values can be ratified
  in v1.x without breaking deployed receivers. `typeLabel` (optional text)
  carries display flavor and the finest grain of receiver profile
  selection (the cascade in the next bullet); `location` stays free text,
  pure display data nothing switches on.
- **Explicit `primary` flag.** The descriptor of the reference object (the
  pose a motion rig reproduces and a compensation tool corrects) carries
  `primary = true` (exactly one SHOULD be set; receivers fall back to the
  first object). Combined with discovery re-sends on change, this enables
  within-game profile switching: when the player enters a vehicle or
  aircraft, the game re-sends discovery with a new primary object and
  `ObjectType`; receivers watching discovery switch cueing presets
  automatically.
- **Receiver profile selection is a cascade.** Motion software that lets
  users tune rig response selects along three levels over discovery, most
  to least specific: `gameName` → the primary object's `ObjectType` → the
  primary object's `typeLabel`. Each level falls back to the one above it
  when no user profile matches, and `typeLabel` is matched exactly
  (sender-chosen free text, never fuzzy). One wire therefore covers
  per-game, per-class, and per-vehicle tuning — a user can make one
  specific machine feel different from its class — with no sender-side
  profile concept; the discovery re-send is the switch signal.
- **Common Channels annex.** Cross-game semantics are ratified in
  [`CHANNELS.md`](CHANNELS.md): an optional vocabulary of well-known channel
  names with required units (`engine.rpm` is `rpm`). Senders SHOULD use
  ratified names when the concept matches and MUST NOT reuse a ratified name
  with a different unit; everything else stays free-form. Receivers match
  exactly and fall back to per-game profiles, never fuzzy-match. Binding is
  already solved by discovery ids, so the annex is semantic convenience at
  zero wire cost. New entries require the concept in ≥2 shipping games and a
  reviewed PR; entries are never renamed or re-united.
- **Plain UDP over a messaging library or shared memory.** At 60-120 Hz
  with sub-500-byte packets, transport latency is a few hundred
  microseconds at most, noise next to the physics tick, cueing filters,
  and actuator response. A high-performance messaging layer would add a
  media driver and client library to every integration for performance
  this use case cannot use. Plain UDP multicast is trivial to ship in
  engine plugins (see §7 and `implementation-udp.md`). Shared memory (a memory-mapped
  file) is the alternative most existing sim telemetry already uses
  (iRacing, Assetto Corsa/ACC, ManiaPlanet, RedOut), but it is the wrong
  shape for the "multiple local clients without extra ports or proxying"
  requirement: an MMF is a single-writer region readers poll and must
  coordinate torn-read protection against themselves, not a fan-out
  primitive — N consumers (dashboard, motion rig, haptics, logger) either
  share bespoke versioning/locking or each race the writer independently.
  Multicast UDP gives every consumer the same stream on joining the
  group, with no shared-file coordination, and does not foreclose a
  second machine on the LAN the way an MMF would.
- **Optionality is uniform across drive-point states.** Every state that
  carries quantities a sender may not measure (`WheelState`,
  `PropellerState`, `JetState`, `LegState`, `GenericState`) expresses
  "not measured" via a union variant with a `Void` default. Quantities
  sources report together bundle into one all-or-neither sub-struct
  (`TyreState`, `PropellerExtended`); quantities sources report
  independently get a union each. Every `WheelState` measurement (rpm,
  slip, compression, steer angle, load force, damper velocity, torque,
  brake pressure) is its own named union, because sources expose very
  different subsets: aircraft gear reports compression only, arcade
  physics rpm and contact. Senders must not claim a variant with sentinel
  values; zeros inside measured fields are real readings. Recorded
  conventions live in [CONVENTIONS.md](CONVENTIONS.md): tyre wear 1 = new;
  tyre temp carcass/average °C; `SuspensionSpec.damping` 0 = unspecified
  (the receiver approximates load force from stiffness otherwise).
- **Atmosphere is optional, gravity is not.** Air density, temperature and
  pressure come together from a weather or atmosphere model, or not at
  all, so `Environment.atmosphere` is one all-or-neither bundle and a game
  without one leaves it unset (vacuum is a known atmosphere of zero
  density). Gravity is always declared: a sender with no gravity model
  declares standard gravity, 9.80665 m/s².
- **`GenericState` carries force.** Generic drive points are multi-instance
  by design (four hover fans = four points), and per-point physical values
  cannot ride object-level channels without stringly-typed linkage. Force is
  the universal mechanical quantity (wheel torque and propeller thrust both
  reduce to it), so `GenericState` carries optional world-space `force :Vector3`
  (N), and the descriptor's `GenericSpec` carries `ratedForce` for
  normalization. Dedicated states keep their own idioms (torque, thrust); a
  uniform force field can be added in v1.x if force-based cueing software
  wants it.

## 6. Wire sizes

- `MotionFrame`, one object, pose only: ~68 bytes.
- Four wheels (every measurement and the tyre) + eight channels ≈ +490 bytes, still far
  within the 1,400-byte datagram budget at 60 Hz.
- `DiscoveryFrame`: ~300-800 bytes for a typical sender (strings dominate),
  re-sent every 2 s.
- Every datagram stays within a mandatory 1,400-byte budget. Simulator-scale senders
  (full catalogues, multi-car grids) page discovery, split large ticks into
  parts and spread the value refresh across ticks
  (`implementation-udp.md` § Datagram budget).

## 7. Transport

One UDP multicast group, one port. Each datagram carries an 8-byte envelope
(magic `OMT1`; frame type `0x00` discovery, `0x01` motion, `0x02` event;
reserved) followed by the Cap'n Proto message, which stays word-aligned and
readable in place. `DiscoveryFrame` is sent at session start, on change, and
re-sent every 2 seconds (paged when large) so late joiners converge and lost
discovery heals;
`MotionFrame` is fire-and-forget: receivers hold the last pose and
interpolate across occasional loss. Defaults: group `239.255.17.17`, port
`40123`, TTL 1; all configurable. See `implementation-udp.md`.

## 8. Evolution and compatibility

- `schemaVersion` distinguishes major schema revisions; `1` is current.
- Cap'n Proto unknown-field skipping: receivers ignore fields and descriptor
  variants they do not know; absent optional fields decode as defaults. v1.x
  may therefore add channels, drive-point variants, and optional fields
  freely.
- The Cap'n Proto schema is the single source of truth. If a JSON mirror is
  ever needed for tooling (e.g. web dashboards), it must be generated from
  the capnp, never hand-maintained.
