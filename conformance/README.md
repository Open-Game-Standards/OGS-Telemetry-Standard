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
