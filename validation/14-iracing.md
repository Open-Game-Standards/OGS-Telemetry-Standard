# Test 14: race car (iRacing SDK, official documentation)

Reviewed source: iRacing SDK documentation site (`irsdkdocs/` — ~250
documented telemetry variables plus the session-string YAML sections:
WeekendInfo, DriverInfo, SessionInfo, QualifyResultsInfo; simulator-context
notes for replay, spectator, ghost, team and spotting modes). Code not kept
in this org; evidence captured in the knowledge base.

## Pose and dynamics — both native representations

iRacing exposes world kinematics (`VelocityX/Y/Z`, `Lat`/`Lon`/`Alt`,
`Speed`) *and* body-frame dynamics (`LatAccel`/`LongAccel`/`VertAccel`,
`RollRate`/`PitchRate`/`YawRate`) natively — a sender-side XOR choice per
the OGS-TS dynamics rule, and the body accel triple + angular rates map
straight into `bodyDynamics` (fifth independent confirmation of that
variant).

| iRacing | OGS-TS destination | Class |
|---|---|---|
| `Lat`/`Lon`/`Alt`, `VelocityX/Y/Z`, `Speed` | `kinematics.position/velocity` (lat/lon as geo channels) | direct |
| `Roll`/`Pitch`/`Yaw` | `orientation` (Euler→quat) | recipe |
| `LatAccel`/`LongAccel`/`VertAccel` | `bodyDynamics.specificForce` | direct |
| `RollRate`/`PitchRate`/`YawRate` | `bodyDynamics.angularVelocity` | direct |
| `HF/HRshockDefl` per corner | `WheelState.compression` ×4 | direct |
| `HF/HRshockVel` per corner | `WheelState.damperVelocity` ×4 | direct |
| `SteeringWheelAngle`, throttle/brake/clutch (raw+processed) | `ctrl.steer/throttle/brake/clutch` channels | annex |
| `SteeringWheelTorque`/`PctTorque`/`PeakForceNm` | `ctrl.ffb.*` channels (FFB middleware consumes) | custom |
| `Gear`, `RPM`, `Shift*`, `ManifoldPress`, oil/water/voltage, `Fuel*`, `EnergyERS*`, `PushToPass` | `transmission.*`, `engine.*`, `fuel.*`, `ers.*`, `p2p.*` channels | annex/custom |
| `TireLF/LR/RF/RR_rumblePitch` | `haptics.rumble.*` channels ×4 | custom |
| zone tyre temps/pressures/wear | per-corner channels (`wheel.lf.*`) — per-zone data exceeds the carcass average in `WheelState.tyre` | convention |

`damperVelocity` is a `WheelState` field on ≥2-game evidence (iRacing
shockVel; Dirt 4 / Codemasters-carrier `suspension_velocity` from tests
10–11) — per-drive-point physics that cannot ride object channels without
stringly linkage (the `GenericState.force` lesson).

## Session string → session channel values

The YAML sections are the richest exercise yet of discovery `values`
(test 13): `WeekendInfo` (weather type, wind, commercial/team modes),
`SessionInfo` (session type, laps, results), `DriverInfo` (driver/car
entries), `QualifyResultsInfo` — all session-scaled → discovery-valued
channels, atomic for late joiners. Tick-rate session variables split by
cadence: `SessionTime`/`SessionTick` stream; `SessionLapsRemain`,
`PitsOpen`, `TrackTemp`, `TrackWetness`, `WeatherDeclaredWet`, `WindDir`/
`Vel`, `Skies`, `FogLevel`, `SolarAltitude`/`Azimuth` ride discovery
`values` (or stream if a sender watches them at rate — cadence decides the
layer).

## Multi-car grid

`CarIdx*` arrays (position, lap distance, est. time, gear, RPM, steer,
track surface/material, tyre compound — one slot per car, ~64) plus
`PlayerCarIdx`. OGS-TS mapping: each streamed car is its own object
(`CarIdxTrackSurfaceMaterial` → `ContactMedium` per object). No schema
gap, one sender guideline: the primary object streams at full rate;
remote cars stream throttled or distance-filtered — full-rate 64-car
pose-only ≈ 4.4 KB/frame ≈ 266 KB/s at 60 Hz, affordable but wasteful.

## Contexts (replay / spectator / ghost / spotting)

Documented context quirks (replay provides partial/incorrect variables;
AI sessions reset Session variables on restart; TestDrive hides identity)
are sender-side guidance, not schema: OGS-TS session identity is
`sessionStartUnixUs` — a replay context that keeps the session id simply
streams what it has; restarts re-send discovery.

## Verdict

**Covers** — plus one adoption: `WheelState.damperVelocity` (≥2-game
evidence). Both dynamics representations, the session-values mechanism,
and multi-object all exercised by a single documented source.

Validation set: **14 tests, 6 source classes, zero open gaps.**
