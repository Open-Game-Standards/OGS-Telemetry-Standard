# MSFS 2024 → OGS-TS sender reference

How an MSFS 2024 sender exposes its simulation variables as OGS-TS v1. Core
quantities land in the schema directly; everything else rides sender-
declared channels. Scope: read-only egress — SimConnect key events and
variable writes remain the command path (see DESIGN, Non-goals).

Source variables: the MSFS 2024 SDK SimVar set (1,354 documented names).

## Core schema (no channels needed)

| OGS-TS field | SimVar source | Conversion |
|---|---|---|
| `position` | local world X/Y/Z (session-stable local origin — re-origin on teleport, not planetary absolutes) | m, direct |
| `orientation` | `PLANE_PITCH/BANK/HEADING_DEGREES_TRUE` | Euler (rad!) → quaternion |
| `kinematics.velocity` | `VELOCITY_WORLD_X/Y/Z` | m/s, direct |
| `kinematics.acceleration` | `ACCELERATION_WORLD_X/Y/Z` | ft/s² → m/s² ×0.3048 |
| `bodyDynamics.specificForce` | `ACCELERATION_BODY_X/Y/Z` | ft/s² → m/s²; then `f = a − R(q)·g` (at rest reads +9.81 heave) |
| `bodyDynamics.angularVelocity` | `ROTATION_VELOCITY_BODY_X/Y/Z` | rad/s, direct |
| `Environment.atmosphere.known` (airDensity, temperature, pressure), `Environment.gravity` | `AMBIENT DENSITY/TEMPERATURE/PRESSURE`, planet gravity | SI |
| `namedPoints` | `STRUCT_EYEPOINT_*`, `STRUCT_ENGINE_POSITION` | object-local m |
| wheel drive points (`rpm`, `slip`, `contact`, `steerAngle`) | `CENTER/LEFT/RIGHT WHEEL RPM`, `GEAR SKIDDING FACTOR`, `SIM ON GROUND` + surface, `GEAR_*_STEER_ANGLE` | steerAngle + = right per CONVENTIONS C-4 — sign-verify against the sim; unit is rad (watch the DEGREES-named neighbours) |
| jet drive point (`throttle`) | `GENERAL ENG THROTTLE LEVER POSITION` | 0..1 direct |

Dynamics rule: emit the body set (`bodyDynamics`) — the fullest native
frame; the XOR rule forbids emitting both. MSFS trap: several `*_DEGREES`
variables are actually **radians** (documented per variable) — the sender,
not the receiver, absorbs doc quirks.

## Channel reference

Cadence: **stream** = per-tick in `MotionObject.channels`; **session** =
current value in `ObjectDescriptor.values`, or `texts` for text channels (discovery, re-sent on change).

### Position / geo (stream, throttled)
| Channel | Type | Unit | SimVar |
|---|---|---|---|
| `position.lat` / `position.lon` | number | rad | `PLANE LATITUDE/LONGITUDE` (radians, direct; Float32 ≈ 1 m — display-grade) |
| `position.altMsl` | number | m | `PLANE_ALTITUDE` (ft → m) |
| `env.heightFromGround` | number | m | `PLANE_ALT_ABOVE_GROUND` (the non-CG variant; CG relation is declared via `referencePoint`) |

### Air data (stream)
| Channel | SimVar |
|---|---|
| `air.indicatedAirspeed` / `air.trueAirspeed` (m/s) | `AIRSPEED INDICATED/TRUE` (kt) |
| `air.mach` | `AIRSPEED MACH` |
| `air.verticalSpeed` (m/s) | `VERTICAL_SPEED` (fpm) |
| `air.aoa` / `air.beta` (rad) | `ANGLE OF ATTACK` / `SIDESLIP` |
| `air.alphaX/Y/Z` (rad/s²) | `ROTATION_ACCELERATION_BODY_X/Y/Z` — lever-arm α for consumer corrections |
| `air.turnBall` (−1..1) | `TURN COORDINATOR BALL` (position) — + = ball right of centre, as MSFS reports; the slip/skid cue motion profiles use for tilt coordination |
| `air.variometer` (m/s) | `VARIOMETER RATE` |
| `air.loadFactor` | `G FORCE` — 1 in level flight |
| `air.relativeWind.x/y/z` (m/s) | `RELATIVE WIND VELOCITY BODY X/Y/Z` — airflow relative to the aircraft, body axes |
| `velocity.body.x/y/z` (m/s) | `VELOCITY BODY X/Y/Z` |
| `nav.headingMagnetic` / `nav.headingGyro` (rad) | `PLANE HEADING DEGREES MAGNETIC/GYRO` (the gyro may drift) |
| `mass.yawInertia` (kg·m²) | `TOTAL WEIGHT YAW MOI` (slug·ft² ×1.35582) |

### Wind / ambient (session, or stream when dynamic weather)
| Channel | SimVar | Notes |
|---|---|---|
| `wind.speed` (m/s), `wind.direction` (rad), `wind.x/y/z` | `AMBIENT WIND VELOCITY/DIRECTION/X/Y/Z` | direction is the **from** convention (CONVENTIONS C-7); MSFS reports degrees → ×π/180; vector components point toward |
| `env.visibility` (m), `env.precipRate`, `env.inCloud` (bool) | `AMBIENT VISIBILITY/PRECIP RATE/IN CLOUD` |
| `wind.body.x/y/z` (m/s) | `AIRCRAFT WIND X/Y/Z` | ambient wind in body axes |

### Controls (stream)
| Channel | SimVar |
|---|---|
| `ctrl.aileron` / `ctrl.elevator` / `ctrl.rudder` (−1..1) | `AILERON/ELEVATOR/RUDDER POSITION` |
| `ctrl.aileronDeflection` etc. (rad, surface-actual) | `*_DEFLECTION` |
| `ctrl.trim.*` | `ELEVATOR/AILERON/RUDDER TRIM` |
| `ctrl.flaps` / `ctrl.spoilers` (0..1) | `FLAPS INDEX`→norm / `SPOILERS POSITION` |
| `gear.position` (0..1), `gear.damageBySpeed` | `GEAR_ANIMATION_POSITION`, `GEAR DAMAGE BY SPEED` |
| `gear.contact[1..6].compression` (0..1), `gear.contact[1..6].onGround` (bool) | `CONTACT POINT COMPRESSION:0..5`, `CONTACT POINT IS ON GROUND:0..5` |

### Engines / fuel (stream; per-engine instances use index-suffixed channels, e.g. `engine[1].n1`)
| Channel | SimVar |
|---|---|
| `engine.n1` / `engine.n2` (0..1) | `ENG N1 RPM` / `ENG N2 RPM` (%) |
| `engine.rpm`, `engine.itt` (°C), `engine.oilTemp/Pressure` | `GENERAL ENG RPM`, `TURB ENG ITT`, `ENG OIL…` |
| `engine.fuelFlow` (kg/s) | `ENG FUEL FLOW PPH` |
| `engine[n].vibration`, `engine[n].rotorRpm` (fraction of nominal) | `ENG VIBRATION:n`, `ENG ROTOR RPM:n` (%) |
| `fuel.quantity` (kg), `fuel.selectedKg` | `FUEL TOTAL QUANTITY`, `FUEL SELECTED QUANTITY` |

### Electrics / hydraulics (session or slow stream)
`elec.busVoltage`, `elec.generatorLoad[kW]`, `elec.apuOn` (bool),
`hyd.pressure[Pa]`, `fail.engine[bool]`… from the `ELECTRICAL*`, `HYDRAULIC*`,
`GENERAL ENG FAILED`, `*_FAILURE` families.

### Avionics / radios (session)
`nav.com1.active[Hz]`, `nav.com1.standby`, `nav.nav1.active`,
`nav.adf.bearing[rad]`, `nav.xpdr.code`, `nav.gs`, `nav.locDeflection`… from
the `COM/NAV/ADF/VOR/ILS/GPS/TRANSPONDER` families (134 vars — declarations
follow the vendor manual's naming; ratify later per the ≥2-game bar).

### Lights / cabin / service (session or slow stream)
`light.landing/nav/strobe/beacon/taxi` (bool) from `LIGHT ON`-family vars;
`cabin.seatbelts`, `cabin.noSmoking` (bool); `pushback.attached` (bool),
`pushback.angle` (rad).

### Touchdown / impacts (stream, event-class)
| Channel | SimVar |
|---|---|
| `impact.touchdown` (bool edge) | `SIM ON GROUND` rising edge |
| `impact.touchdownBank/Heading/Pitch` | `PLANE TOUCHDOWN_*` (latched values, sent once on touchdown) |
| `impact.verticalSpeed` | `VERTICAL_SPEED` at touchdown |

### Session / misc (session)
`session.slew` (bool, `IS SLEW ACTIVE`), `session.paused`,
`session.timeOfDayZulu[s]`, `perf.frameRate` (stream, `FRAME RATE`),
`session.simRate` (`SIM RATE`), `air.onGround` (stream, `SIM ON GROUND`).

## Sender notes

- Re-origin `position` per session/teleport; geo channels carry absolute
  location at display precision (DESIGN, Precision).
- The 531 avionics-instrument/animation variables (needle positions,
  `…_ANIMATION…`) are also just channels when a sender wants them — the
  mechanism is total; this reference curates the motion-relevant set.
- Names above follow CHANNELS.md conventions where they exist; the rest are
  sender-declared and ratifiable later without any wire change.
