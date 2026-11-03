# iRacing → OGS-TS sender reference

How an iRacing sender (irsdk memory-mapped file → OGS-TS bridge) exposes the
documented telemetry set (250 documented variables + session-string YAML)
as OGS-TS v1. The irsdk surface is itself read-only, matching OGS-TS scope.

Source: iRacing SDK documentation. Unit column: where the docs state no
unit (†), the sender must verify at capture and declare the channel unit —
values must never be guessed onto the wire.

## Core schema (no channels needed)

| OGS-TS field | irsdk source | Conversion |
|---|---|---|
| `kinematics.position` | **not exposed** — no local-world XYZ. Sender either (a) keeps a session-stable local origin and derives meters from `Lat`/`Lon`/`Alt` (equirectangular, ~0.3 % error at track scale), or (b) leaves position near-origin and carries absolute location only via geo channels (rigs do not need absolute position) | recipe |
| `orientation` | `Roll`/`Pitch`/`Yaw` † | Euler → quaternion |
| `kinematics.velocity` | `VelocityX/Y/Z` † (m/s) | direct |
| `bodyDynamics.specificForce` | `LatAccel`/`LongAccel`/`VertAccel` † | direct if m/s²; ×9.80665 if G; verify at capture |
| `bodyDynamics.angularVelocity` | `RollRate`/`PitchRate`/`YawRate` † (rad/s) | direct |
| wheel drive points `compression` | `LF/RF/LR/RRshockDefl` † (docs list `HF/HR` front/rear pairs + `_st` steering-linked variants — capture-verify corner mapping) | m, direct |
| `WheelState.damperVelocity` | `*shockVel` † | m/s, direct |
| `ContactMedium` per object | `PlayerTrackSurfaceMaterial` / `CarIdxTrackSurfaceMaterial` (material enum → medium map) | recipe |
| `Environment.temperature` | `TrackTemp` (°C) | direct |
| `referencePoint` | irsdk reports vehicle-frame data at the physics reference — declare what the capture shows (typically CG) | declaration |

## Channel reference

Cadence: **stream** = per-tick; **session** = discovery `values`, or `texts` for text (the YAML strings).

### Geo (stream, throttled)
`position.lat`/`position.lon` (deg, `Lat`/`Lon`), `position.altMsl` (m,
`Alt`) — Float32 geo is display-grade.

### Controls & FFB (stream)
| Channel | irsdk | Notes |
|---|---|---|
| `ctrl.steering.angle` (rad) | `SteeringWheelAngle` | + = right (CONVENTIONS C-4); clamp to `SteeringWheelAngleMax`; sign capture-verify † |
| `ctrl.throttle` / `ctrl.brake` / `ctrl.clutch` (0..1) | `Throttle`/`Brake`/`Clutch` | `*Raw` are pedal axes; pick one, declare which |
| `ctrl.handbrake` | `HandBrake` | |
| `ctrl.ffb.torque` (N·m)† | `SteeringWheelTorque` | for FFB middleware |
| `ctrl.ffb.peakForce` (N·m)† | `SteeringWheelPeakForceNm` | session |

### Engine / drivetrain (stream)
`engine.rpm` (`RPM`), `transmission.gear` (`Gear`), `engine.shiftLight`
(0..1, `ShiftIndicatorPct`), `engine.manifoldPressure`† (`ManifoldPress`),
`engine.oilTemp`/`waterTemp` (°C), `engine.oilPressure` (kPa→Pa ×1000)†,
`engine.voltage`, `engine.warnings` (bool, `EngineWarnings`),
`ers.batteryJ` (`EnergyERSBattery`, J), `ers.deployPct`
(`EnergyMGU_KLapDeployPct`), `p2p.count`/`p2p.active` (`PushToPass*`).

### Fuel / brakes / tyres (stream + session)
`fuel.level` (declare unit: L or kWh — `FuelLevel` is unit-ambiguous by
drivetrain), `fuel.usePerHour`† (`FuelUsePerHour`), `fuel.pressure`†,
`brakes.absActive` (bool, `BrakeABSActive`), `brakes.absCut` (0..1,
`BrakeABSCutPct`), `haptics.rumble.lf/lr/rf/rr` (`TireLF/LR/RF/RR_
rumblePitch`), session: `tyre.compound` (`PlayerTireCompound`),
`tyre.setsUsed/available` (`*TireSets*`).

### Timing (stream)
`lap.current` (`Lap`), `lap.currentTime` (`LapCurrentLapTime`),
`lap.lastTime`, `lap.bestTime`, `lap.distPct` (`LapDistPct`), and the
`LapDelta*` family (`…toBestLap/…toOptimalLap`, `_ok` validity bools).

### Session & weather (session `values`/`texts`; stream when dynamic)
`session.num`/`state`/`lapsRemain`/`lapsTotal`/`timeRemain`/`timeOfDay`
(`Session*`), `session.uniqueId` (`SessionUniqueID` — identity anchor),
`pit.stopActive`, `pit.repairLeft`, `pits.open`, `weather.trackTemp`,
`weather.wetness` (`TrackWetness`), `weather.declaredWet` (bool),
`weather.precipitation`, `weather.skies`, `weather.windDir/vel`,
`weather.fog`, `weather.solarAltitude/azimuth`. `SessionFlags` is a
bitmask — decompose consumed flags to boolean channels; the raw word may
also ride a channel. `SessionTick`/`SessionTime`/`FrameRate` stream
(`perf.*`).

### State (session)
`session.onTrack`/`inGarage` (`IsOnTrack`/`IsInGarage`),
`session.replayPlaying` + `replay.playSpeed` (`IsReplayPlaying`,
`ReplayPlaySpeed`), `driver.incidentCount` (`PlayerCarDriverIncidentCount`).

## Session-string YAML → discovery

| YAML section | OGS-TS home |
|---|---|
| `WeekendInfo` (weather type, wind, commercial/team modes, track size) | session `values`/`texts` on the primary object |
| `SessionInfo` (session type, results, laps) | session `values`/`texts` |
| `DriverInfo` (driver/car entries per CarIdx) | **per-car object descriptors** (name, car number, typeLabel) for the multi-object grid |
| `QualifyResultsInfo` | session `values`/`texts` |
| `CameraInfo`, `RadioInfo`, `SplitTimeInfo` | session `values`/`texts` (consumer-UI features; SplitTime sectors may also stream `lap.sector*`) |

## Multi-car grid

`CarIdx*` arrays + `PlayerCarIdx` → one OGS-TS object per streamed car
(descriptors built from `DriverInfo`; identity = car index). Guidance from
test 14: primary object at full rate; remote cars throttled or
distance-filtered. Full-rate 64-car pose is ≈ 266 KB/s at 60 Hz, about
three times the sender size envelope (implementation-udp.md § Sender size
envelope): stream remote cars at ≤ 15 Hz, or keep cars near the player at
full rate and the rest at a few Hz. Per-car channels: `position`/`lapDistPct`/`estTime`/`gear`/
`rpm`/`steer`/`onPitRoad`/`lap`/`classPosition`
(`CarIdxPosition/LapDistPct/EstTime/Gear/RPM/Steer/OnPitRoad/Lap/
ClassPosition`).

## Sender notes

- The irsdk publishes at its own fixed rate (session-tick based); the OGS-TS
  sender streams per captured tick and lets discovery declare cadence.
- † entries: the documentation set is maturing (units present on 40/250
  variable pages). Senders verify at capture and declare; receivers trust
  the declared unit. Never guess.
- Community-tooling precedent for the bridge: SimHub/GPDS already parse
  this surface — an OGS-TS sender is a re-emit, not an extraction project.
