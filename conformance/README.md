# Conformance corpus

Golden OGS-TS datagrams + a semantic manifest, generated deterministically
by the reference implementation
([`ogs-ts-dotnet`](https://github.com/Open-Game-Standards/ogs-ts-dotnet),
`src/ConformanceGen`).
Every engine implementation (Unity, Godot, UE, …) validates against this
corpus so their encoders provably agree on the wire.

Every vector is in **canonical OGS encoding**
([implementation-capnproto.md § Encoding rules](../implementation-capnproto.md#encoding-rules-normative)):
Cap'n Proto canonical form, zeroed unused bits, declared discriminants,
and fixed field presence. The bytes are therefore a function of the
message content alone, not of the encoder that produced them.

## Files

- `manifest.json` — per-vector semantics: frame type, description, and the
  `input` object (the semantic content; serves as encode source **and**
  decode expectation). An input lists every field that differs from its
  default; an omitted field is default (0, false, `""`, empty list,
  all-default struct, first enumerant, first union variant). Union
  variants appear by name; a `Void` variant other than the first appears
  with the value `null`; a named union (`localGravity`) appears as an
  object under its name, holding its variant the same way
- `vectors/<id>.hex` — the raw datagram **including the 8-byte `OMT1`
  envelope**, lowercase hex wrapped at 64 characters

All floats in the corpus are **float32-exact** — implementations compare
exactly, no epsilon.

## Vectors

| id | covers |
|---|---|
| `discovery-minimal` | smallest valid DiscoveryFrame (one primary object) |
| `discovery-channels` | channels with units, ranges, a description, declared value types, unitless boolean |
| `motion-pose` | pose core: position + identity quaternion |
| `motion-channels` | pose + number/boolean channel values by discovery id |
| `motion-multi` | two objects, primary first |
| `motion-bodydynamics` | pose + `bodyDynamics` union: accelerometer-style specific force, C-4 angular velocity |
| `event-impact` | `body.impact` with intensity, duration, direction |
| `discovery-gravity-vector` | `Environment.gravityVector` union: tilted session gravity, scalar `gravity` = its magnitude (C-12) |
| `motion-local-gravity` | `MotionObject.localGravity.vector` (named union) with `bodyDynamics` reacting to it (C-12) |
| `motion-local-gravity-zero` | `localGravity.vector` selected with an all-zero vector: weightless, distinct from `noLocalGravity` |
| `discovery-paged-p0` / `-p1` | paged discovery: generation 3 in two pages, identity on page 0, a session text value (`texts`) on page 1 |
| `motion-parts-p0` / `-p1` | one tick in two motion parts: pose in part 0, channel values only in part 1 |
| `discovery-identity` | sender instance identity: `instanceLabel` and `host`; declared `motionRateHz`; `noAtmosphere` |
| `motion-wheel` | wheel drive point with per-field optionality: rpm, slip, compression and torque selected, every other measurement and the tyre unset |
| `motion-kinematics` | pose + `kinematics` union variant: world-space velocity and coordinate acceleration |
| `discovery-drivepoints` | every drive-point descriptor variant with its spec, and a channel with `unspecified` value type |
| `motion-drivepoints` | wheel measuring everything incl. `tyre`, propeller `extended`, jet `thrust`, generic `force` |
| `motion-texts` | a `TextValue` in a motion frame beside a number in `channels` |

Malformed and future-shaped datagrams a receiver must survive live in
[negative/](negative/). `recordings/sample.ogsrec` is a sample
recording ([recording.md](../recording.md)): five corpus datagrams from
two senders, one IPv4 and one IPv6; `validate.py` checks it.

## Sender behaviour

The vectors fix bytes. Some rules fix what a sender does over time, which
bytes cannot show, so they are checked by driving a sender and inspecting
the datagrams it emits. The reference implementation's tests
(`ogs-ts-dotnet`, `PublisherRegressionTests`) do this over a loopback socket;
`ogs-ts-unreal`'s conformance binary checks the same planning logic; the
reference monitor flags the same rules live. A rule that names no clause is
a behaviour of the reference implementation that senders deriving their own
dynamics should match.

| Rule | Check | Monitor finding |
|---|---|---|
| The declared `motionRateHz` is the achieved mean rate at any host frame rate (implementation-udp.md § Send cadence) | A 10 s run at 60, 90 and 144 FPS, and with jittered frames, sends within 1 % of the declared rate; a stall longer than one interval resyncs instead of bursting | `motion-rate` |
| Every event is sent at least once, however slowly the host ticks (CONVENTIONS C-10) | One event per frame at 60, 10, 9 and 4 FPS, and one fired before the first tick, all arrive | none (receivers cannot see an unsent event) |
| Event frames stay within the datagram budget (implementation-udp.md § Event splitting) | A 60-event burst with directions arrives complete in frames of at most 1,400 bytes, disjoint and in order | `datagram-budget` |
| No events while paused; queued events are dropped at the pause (CONVENTIONS C-11) | An event fired before and one fired during a pause send nothing; one fired after resuming is sent | none |
| An unmeasured orientation is the identity quaternion (CONVENTIONS C-2) | A sender with no orientation bound sends `(0, 0, 0, 1)` | `quaternion-norm` |
| Derived dynamics are static at a moving spawn or resume: the sample after a reset does not difference against a zero previous velocity (reference `BodyDynamicsDeriver`, IMPLEMENTING.md; no CONVENTIONS clause) | A sender spawning at cruise speed reads only the gravity reaction, with measured and with derived velocity | none |

Missing motion frames (`motion-gap`) and delay variation (`motion-jitter`)
are likewise visible to the monitor, from the senders' own timestamps.

## Using the corpus

- **Decode direction (receivers)**: parse each `.hex`, decode, compare
  against the manifest `input`. Guarded continuously by
  `Ogs.Telemetry.Tests.ConformanceVectorTests`.
- **Encode direction (senders)**: build each frame from the manifest
  `input` in canonical OGS encoding and byte-compare with the `.hex`
  file.
- **Corpus self-check**: `python conformance/validate.py` (pycapnp)
  decodes every vector, verifies it equals its manifest input exactly
  and is in canonical OGS encoding, independently of the generator.

## Regeneration

```bash
cd ogs-ts-dotnet
dotnet run --project src/ConformanceGen [outputDir]
```

Regeneration is **deterministic**: with unchanged schema and manifest,
`git diff` after regenerating must be empty — canonical OGS encoding
leaves the encoder no freedom. If bytes change, the change
is a wire-format change — review it as such, then regenerate as part of
that change. Schema evolution rules (unknown-field skipping) mean additions
usually alter vectors legitimately: regenerate, review the diff, and note
the corpus version bump.
