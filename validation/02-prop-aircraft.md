# Test 02: prop aircraft (MSFS SimConnect / X-Plane datarefs)

## Setup

- `ObjectDescriptor`: `type = aircraft`, `primary = true`, 1 × `propeller`
  drive point (`PropellerSpec`: diameter, blades), 3 × `wheel` drive points
  (landing gear — `SuspensionSpec` fits gear travel/stiffness/damping)
- Annex channels: `engine.throttle`, `engine.running`, `fuel.level`,
`fuel.rate`, `lights.headlights` (landing light)

## Core mapping

| Game field | OGS-TS destination | Class |
|---|---|---|
| lat/lon/alt, local x/y/z (X-Plane OpenGL RH Z-up) | `position` (geodetic→local tangent + axis remap at sender) | direct |
| pitch/roll/heading (MSFS Euler) / `position/q` (X-Plane quaternion) | `orientation` | direct |
| VELOCITY WORLD / `local_vx..` | `kinematics.velocity` | direct |
| ACCELERATION WORLD | `kinematics.acceleration` | direct |
| angular velocities (X-Plane R/P/Y rates) | derivable from orientation deltas (slerp derivative) | recipe |
| ENG RPM / PROP RPM | `PropellerState.rpm` (pitch/thrust ride the optional `extended` variant when measured) | direct |
| throttle lever % | `engine.throttle` | annex |
| fuel flow / tank quantity | `fuel.rate` / `fuel.level` | annex |
| mixture, oil temp/pressure | `mixture.*`, `engine.oilTemp`… | custom channel |
| gear compression (X-Plane per-gear deflection) | `WheelState.compression` ×3 | direct |
| nose-gear steer angle | `WheelState.steerAngle` | direct |
| gear position 0..1 | `gear.down` | convention channel |
| aileron/elevator/rudder/flaps/spoilers | `ctrl.*` | convention channel |
| airspeed TAS/IAS, AoA, Mach | `air.*` | convention channel |
| ambient wind dir/vel | `wind.trueDirection` / `wind.trueSpeed` | convention channel |
| ambient temp/pressure/density | `environment` (discovery-static — acceptable: slowly varying) | direct |
| stall warning / G meter | `air.stall`, `air.gLoad` | custom channel |
| avionics/FMS state | — | out of scope (instrument emulation) |

## Notes

- Control surfaces are object-level quantities — channels are their honest
  home; the `ctrl.*`, `wind.*`, `air.*` families in `CHANNELS.md` are annex
  candidates (`ctrl.*`/`air.*` have ≥2-game evidence).
- Per-tick wind rides `wind.*` channels — wind gusts are motion-frame data;
  the discovery-static `environment` carries only slowly varying ambient
  conditions (temperature/pressure/density).

## Verdict

**Covers cleanly.** Gear-as-wheels works naturally (`SuspensionSpec` models
oleo travel/stiffness/damping); the conventions (`ctrl.*`, `wind.*`, `air.*`)
cover the flight-control surface area without schema bloat.
