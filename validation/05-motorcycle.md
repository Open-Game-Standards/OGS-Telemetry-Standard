# Test 05: motorcycle (GP Bikes-style)

## Setup

- `ObjectDescriptor`: `type = vehicle`, `primary = true`, 2 × `wheel` drive
  points (front: steered, fork suspension; rear: driven, shock), rider as a
  second `humanoid` object (non-primary)

## Core mapping

| Game field | OGS-TS destination | Class |
|---|---|---|
| position / attitude | `position` + `orientation` (lean = roll, fully in quaternion) | direct |
| velocity / acceleration | `kinematics` | direct |
| engine rpm / gear / throttle / brake / clutch | `engine.rpm`, `transmission.gear`, `engine.throttle`, `brakes.pedal`, `input.clutch` | annex |
| front/rear wheel angular speed | `WheelState.rpm` ×2 | direct |
| fork / shock travel | `WheelState.compression` ×2 | direct |
| steering (rider input vs fork angle) | `steering.input` (channel, %) and `WheelState.steerAngle` (front wheel, rad) | annex / direct |
| tyre temp / pressure / wear / slip | `WheelState.tyre` + `WheelState.slip` | direct |
| rider hang-off / body position | second `humanoid` object's `position`/`orientation` | direct |

## Notes

None — two wheels, one steered + one driven, exercises exactly the machinery
the car test maps. Rider hang-off streams as a second (`humanoid`) object.

## Verdict

**Covers cleanly** — the variable-length drive-point list absorbs the wheel
count; the rider-as-second-object pattern previews multi-object streaming
(cockpit views, co-op rigs).
