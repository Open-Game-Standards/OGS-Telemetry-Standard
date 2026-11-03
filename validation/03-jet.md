# Test 03: jet (DCS-style export semantics)

## Setup

- `ObjectDescriptor`: `type = aircraft`, `primary = true`, 1 × `jet` drive
  point, 3 × `wheel` drive points (gear legs)

## Core mapping

| Game field (DCS export) | OGS-TS destination | Class |
|---|---|---|
| pitch/bank/heading (Euler) | `orientation` (Euler→quat + axis remap) | direct |
| world/body velocity | `kinematics.velocity` | direct |
| body-frame G (normal accel) | `kinematics.acceleration` (rotate via orientation) | recipe |
| throttle position 0..1 | `JetState.throttle` | direct |
| engine thrust | `JetState.thrust` (optional — DCS-style games expose %RPM, not N; senders without measured thrust use the `noThrust` default) | direct |
| engine RPM % | `jet.rpmPct` (% — deliberately NOT `engine.rpm`, whose ratified unit is rpm; the annex rule holds) | custom channel |
| EGT / oil press/temp / afterburner | `engine.egt`, `engine.oilPressure`, `engine.afterburner` | custom channel |
| internal fuel % / kg | `fuel.level` / `fuel.mass` | annex / custom |
| gear legs up/down + compression | 3 × `WheelState` (`compression`; `gear.down` channel) | direct |
| nose-wheel steering | `WheelState.steerAngle` | direct |
| flaps / airbrake / speedbrake | `ctrl.flaps`, `ctrl.airbrake`, `ctrl.speedbrake` | convention channel |
| IAS / Mach / AoA | `air.*` | convention channel |
| nav/strobe/landing lights | `lights.*` (landing light ≈ `lights.headlights`) | annex/close |
| weapons, countermeasures, radar | — | out of scope (combat systems) |

## Notes

- %RPM deliberately does **not** reuse `engine.rpm` (ratified unit is `rpm`) —
  the annex unit rule holds; `jet.rpmPct` is a separate custom channel.
- Idle ≈ 0 N is a real thrust value, which is why `thrust` is optional via
  union rather than zero-sentinel.

## Verdict

**Covers cleanly.** The jet case exercises the same conventions as 02 with
zero additional machinery; %RPM-vs-rpm is exactly what the annex unit rule
exists for.
