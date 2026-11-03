# Test 15: aircraft (X-Plane 12, classic Data Set Output)

Reviewed source: X-Plane Data Set Output table (condensed reference
derived from the official table; based on X-Plane 10.30 with 11/12
evolution notes — operator-provided, captured in the knowledge base).
Companion to test 02 (prop aircraft), focused on the classic DSET
interface rather than datarefs.

## Mapping

| DSET field | OGS-TS destination | Class |
|---|---|---|
| `pitch`/`roll`/`hding, true` | `orientation` (Euler→quat; true heading, not magnetic) | recipe |
| `X`/`Y`/`Z` (local, inertial, m) | `kinematics.position` | direct |
| `vX`/`vY`/`vZ` (m/s) | `kinematics.velocity` | direct |
| `Gload, norml/axial/side` | `bodyDynamics.specificForce` (×9.80665; +1 G in level flight matches the accelerometer sign convention) | direct |
| `P`/`Q`/`R` (rad/s, body) | `bodyDynamics.angularVelocity` | direct |
| `lat`/`lon`, `alt, ftmsl` | geo channels (`position.lat/lon/altMsl`) | convention |
| `alt, ftagl` | `env.heightFromGround` channel (same pattern as FlyDangerous, test 10) | convention |
| `Vind/ktas/ktgs`, `Mach`, `VVI`, `alpha`, `beta`, `hpath/vpath`, `slip` | `air.*` channels (SI conversions: kt→m/s ×0.514444, fpm→m/s) | annex family |
| `L`/`M`/`N` (ft-lb roll/pitch/yaw torque) | `air.rollTorque/pitchTorque/yawTorque` channels (×1.35582 N·m) — whole-aircraft aggregate moments ride channels | custom |
| yoke/aileron/elevator/rudder, trim/flaps/gear/brakes, engine N1/N2/thrust | `ctrl.*`, `gear.*`, `engine.*` channels | annex |
| `f-act`/`f-sim`/`frame time` | `perf.*` channels (sender choice) | custom |

## Notes

- **Sixth independent confirmation of `bodyDynamics`** — the classic table
  exposes exactly the pair cueing wants (body G triple + P/Q/R), in the
  same shape as ED, WhitewaterVR, F1, NoLimits2, iRacing.
- **Both dynamics representations available** (world vX/vY/vZ and body
  G-loads) — sender picks one per the XOR rule; X-Plane senders will
  typically pick `bodyDynamics`.
- **Imperial→SI is the recipe tax** of the classic interface (knots,
  ft, ft-lb, fpm, deg); dataref-based senders skip it. Required-units rule
  in CHANNELS.md carries the conversions.
- Modern X-Plane integrations prefer **datarefs via plugins** — the
  XPLM/plugin path is exactly OGS-TS's engine-plugin sender model; the
  classic UDP DSET is the legacy bridge target (like the Dirt 4 carrier
  in test 11).
- **Catalogue scale.** Subscribing to datarefs over UDP (RREF) instead
  of the DSET table exposes the whole catalogue: 5,484 current X-Plane 12
  datarefs, all readable (X-Plane's `READONLY` / `MUTABLE` / `ACCESSOR`
  marks writability, not readability), ~37,000 values with arrays
  expanded. That is far beyond the sender size envelope
  (implementation-udp.md § Sender size envelope). The X-Plane 12 sender
  reference ([reference-xplane12.md](../reference-xplane12.md)) curates
  ~120 channels whose values fit one datagram per tick; the rest of the
  catalogue is served by X-Plane's own plugin, RREF and Web API
  interfaces.

## Verdict

**Covers** — no adoptions; moments and AoA/sideslip ride channels as in
tests 02–03. The classic table is a near-perfect `bodyDynamics` source.

Validation set: **15 tests, 6 source classes, zero open gaps.**
