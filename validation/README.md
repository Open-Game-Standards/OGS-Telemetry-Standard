# Validation: mapping known game telemetry to OGS-TS v1

Method: take a game's *documented* telemetry output (field list + semantics)
and map every field to its OGS-TS destination. Every field must land in exactly
one of:

| Class | Meaning |
|---|---|
| **direct** | a schema field (pose, drive-point state, kinematics) |
| **annex** | a ratified `CHANNELS.md` channel (auto-maps in receivers) |
| **custom channel** | a free-named channel — works, needs receiver config |
| **GAP** | no honest home — schema or annex change needed |

Gaps are graded: *deferred-safe* (fixable additively in v1.x without wire
breakage) vs *blocking* (must change before release). Conversion recipes the
sender must apply (axis remap, Euler→quaternion, unit changes) are recorded
per game — they are integration cost, not schema gaps, but frequent ones get
a documented recipe.

Results so far:

| Test | Domains | Verdict |
|---|---|---|
| [01-race-car.md](01-race-car.md) | AC-style + iRacing-style car | Covers cleanly — per-wheel dynamics incl. tyre data land in `WheelState` |
| [02-prop-aircraft.md](02-prop-aircraft.md) | MSFS SimConnect + X-Plane datarefs | Covers — gear as wheels; `ctrl.*`/`wind.*`/`air.*` channel families |
| [03-jet.md](03-jet.md) | DCS-style export | Covers — optional thrust; %RPM as its own channel |
| [04-sailboat.md](04-sailboat.md) | Sailaway-style | Covers — multi-sail via drive points; wind rides `wind.*` channels |
| [05-motorcycle.md](05-motorcycle.md) | GP Bikes-style | Covers cleanly — rider as second (`humanoid`) object |
| [06-drone-mech.md](06-drone-mech.md) | FPV sim / MAVLink-style + legged mech | Covers — multi-propeller objects; optional per-leg force |
| [07-elite-spacecraft.md](07-elite-spacecraft.md) | Elite Dangerous community memory offsets | Covers — `bodyDynamics` (accelerometer-class source); ship↔SRV primary switching; low-rate fused pose |
| [08-star-citizen.md](08-star-citizen.md) | Star Citizen / D-BOX (official, vendor-encapsulated) | Out of reach today — game→rig protocol closed; decoded-traffic scenario maps via `bodyDynamics` + impact channels |
| [09-whitewatervr.md](09-whitewatervr.md) | WhitewaterVR raft (game-native UDP, YawVR plugin evidence) | Covers — buoyancy corners as suspension drive points; car-shaped fakery documented |
| [10-gamelink-batch.md](10-gamelink-batch.md) | YawVR GameLink collection (72-game survey + deep dives) | Covers — no schema gaps; quat-native outputs degraded to indexed floats; body-accel lingua franca; coaster/mech/space-racer/antigrav domains |
| [11-spacemonkey.md](11-spacemonkey.md) | SpaceMonkey middleware (~24 games, injected providers) | Covers — 5th source class; Dirt-4 de-facto-carrier finding; fwd/up precedent; **naming risk: OpenMotionAPI collision** |
| [12-flypt-cor.md](12-flypt-cor.md) | FlyPT Mover documentation (center of rotation) | Requirement adopted — `referencePoint` + `namedPoints` close the silent reference-point contract; correction stays consumer-side |
| [13-extensibility.md](13-extensibility.md) | Design review — custom datapoints at two cadences | Supported — streamed channels (motion) + session channels (`values` in discovery); late joiners get whole state from discovery |
| [14-iracing.md](14-iracing.md) | iRacing SDK official documentation (~250 vars + session YAML) | Covers + adopts `damperVelocity`; both dynamics reps native; session `values` exercised; multi-car grid guidance |
| [15-xplane12.md](15-xplane12.md) | X-Plane 12 classic Data Set Output table | Covers — near-perfect `bodyDynamics` source (G triple + P/Q/R, 6th confirmation); imperial→SI recipes; moments → channels |
| [16-msfs2024.md](16-msfs2024.md) | MSFS 2024 SDK — all 1,354 documented SimVars | Covers — STRUCT_* composites mirror OGS-TS groupings; eyepoint/engine positions → `namedPoints`; CG vs non-CG AGL pair vindicates `referencePoint` |

Cross-domain results: every tested vehicle class maps to the two-layer
model using schema fields, annex channels, and channel families — no
dedicated drive-point variants beyond the ratified set. Recurring sender
recipes: axis remap, Euler→quaternion, local-frame G→world conversion,
geodetic→local tangent.
