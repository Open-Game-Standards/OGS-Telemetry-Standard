# X-Plane 12 → OGS-TS sender reference

How an X-Plane 12 sender exposes datarefs as OGS-TS v1. Core quantities
land in the schema directly; a curated set of datarefs rides sender-declared
channels. Scope: read-only egress. Dataref writes and X-Plane commands are
the command path (see DESIGN, Non-goals).

Source variables: the X-Plane 12 dataref catalogue
([developer.x-plane.com/datarefs](https://developer.x-plane.com/datarefs/)),
status `CURRENT`, desktop platforms. Every dataref is readable, including
those X-Plane marks writable (`MUTABLE`, `ACCESSOR`); position, airspeed,
engine and control datarefs are among the writable ones. A sender reads
datarefs through a plugin (XPLM), UDP `RREF` subscriptions, or the X-Plane
12 Web API (`/api/v3`, which also serves byte-array strings).

The reference curates the datarefs that motion, haptics, instruments,
environment and cockpit-state consumers use: ~125 channel names, ~180
values for a twin-engine aircraft with three gear. A sender can publish further datarefs
as channels (see *Further datarefs*).

## Frames

X-Plane's local OpenGL frame is right-handed: +x east, +y up, +z south,
metres, origin at (`sim/flightmodel/position/lat_ref`, `lon_ref`).
Aircraft coordinates are +x right, +y up, +z aft, relative to the CG.

- World: OGS-TS (x, y, z) = X-Plane (x, y, −z). OGS-TS +Z is north, +X
  east, +Y up.
- Object-local: OGS-TS (x, y, z) = aircraft (x, y, −z). The object-local
  origin is the CG; `referencePoint` is named `"cg"` at (0, 0, 0).

## Core schema (no channels needed)

| OGS-TS field | Dataref source | Conversion |
|---|---|---|
| `position` | `sim/flightmodel/position/local_x/y/z` (double) | (x, y, −z), m. X-Plane moves the local origin as the aircraft crosses scenery; when `lat_ref`/`lon_ref` change, position jumps. Re-send discovery with the session anchor unchanged; receivers see one step |
| `orientation` | `sim/flightmodel/position/psi/theta/phi` | deg → rad; heading, pitch, roll applied in that order → quaternion. Signs match C-4 as published (+psi nose right, +theta nose up, +phi right wing down). `psi` is relative to the local frame's north, consistent with `position`; `sim/flightmodel2/position/true_psi` is true north and is not used for the pose |
| `bodyDynamics.specificForce` | `sim/flightmodel/forces/g_side`, `g_nrml`, `g_axil` | ×9.80665 → (x, y, z) = (side, normal, axial). Verify each sign against the sim at capture: level at rest reads ≈ (0, +9.81, 0), a take-off roll reads +z, a coordinated turn reads x ≈ 0 |
| `bodyDynamics.angularVelocity` | `sim/flightmodel/position/Qrad`, `Rrad`, `Prad` | rad/s, direct: x = pitch (Q), y = yaw (R), z = roll (P). Sign-verify against C-4 |
| `kinematics` (alternative) | `local_vx/vy/vz`, `local_ax/ay/az` | (x, y, −z). The XOR rule allows one representation; emit `bodyDynamics` |
| `Environment.airDensity` | `sim/weather/rho` | kg/m³, direct |
| `Environment.temperature` | `sim/weather/aircraft/temperature_ambient_deg_c` | degC, direct |
| `Environment.pressure` | `sim/weather/aircraft/barometer_current_pas` | Pa, direct |
| `Environment.gravity` | `sim/weather/aircraft/gravity_mss` | m/s², direct |
| `Environment.medium` | — | `air` |
| `namedPoints` | `sim/graphics/view/pilots_head_x/y/z` | `"pilot"`, (x, y, −z), m |
| `ObjectDescriptor.typeLabel` | `sim/aircraft/view/acf_ICAO` (string) | e.g. `"C172"` |

The environment changes continuously with altitude. The sender refreshes
it at the periodic discovery re-send, which is not a descriptor change
(the generation stays). Per-tick values ride `air.*` and `env.*` channels.

### Wheel drive points

One `wheel` drive point per gear `i` where `sim/aircraft/parts/acf_gear_type[i]`
≠ 0, named `gear[i+1]`.

| Field | Dataref source | Conversion |
|---|---|---|
| `offset` | `sim/flightmodel/parts/tire_x/y/z_no_deflection[i]` | (x, y, −z), m |
| `WheelSpec.radius` | `sim/flightmodel2/gear/tire_radius_mtrs[i]` | m |
| `WheelSpec.driven` | — | `false` |
| `WheelSpec.steered` | `sim/aircraft/overflow/acf_gear_steers[i]` | bool |
| `WheelState.rpm` | `sim/flightmodel2/gear/tire_rotation_rate_rad_sec[i]` (signed) | ×60/2π |
| `WheelState.slip` | `sim/flightmodel2/gear/tire_skid_ratio[i]` | 0 = full traction … 1 = full skid. A magnitude, not a signed slip ratio |
| `WheelState.compression` | `sim/flightmodel2/gear/tire_vertical_deflection_mtr[i]` | m |
| `WheelState.contact` | `sim/flightmodel2/gear/on_ground[i]`, `sim/flightmodel/ground/surface_texture_type` | off ground → `air`; on ground: Concrete/Asphalt/Shoulder/Blastpad → `asphalt`, grass → `grass`, Dirt/Ground → `dirt`, Gravel → `gravel`, Water/Lake → `water`, Snow → `snow`, other → `other` |
| `WheelState.torque`, `brakePressure` | — | X-Plane exposes neither: left at `noTorque` / `noBrakePressure` |

Wheels use the `core` variant. `WheelExtended` is all-or-neither, and
X-Plane has no tyre pressure, temperature or wear, so steer angle, load and
damper velocity ride channels (*Gear*).

### Propeller and jet drive points

One drive point per engine `i` < `sim/aircraft/engine/acf_num_engines`,
named `engine[i+1]`, typed by `sim/aircraft/prop/acf_en_type[i]`: recip
carb (0), recip injected (1), electric (3) and turboprops (9, 10) are
`propeller`; jets (5, 7) are `jet`; rocket (6) is `generic`.

| Field | Dataref source | Conversion |
|---|---|---|
| `offset` | `sim/flightmodel2/engines/location_x/y/z_mtr[i]` | (x, y, −z), m (relative to the default CG) |
| `PropellerSpec.blades` | `sim/aircraft/prop/acf_num_blades[i]` | integer |
| `PropellerSpec.diameter` | — | not exposed; 0 |
| `PropellerState.rpm` | `sim/flightmodel2/engines/prop_rotation_speed_rad_sec[i]` | ×60/2π |
| `PropellerExtended.pitch` | `sim/flightmodel2/engines/prop_pitch_deg[i]` | deg → rad |
| `PropellerExtended.thrust` | `sim/flightmodel/engine/POINT_thrust[i]` | N |
| `JetState.throttle` | `sim/cockpit2/engine/actuators/throttle_ratio[i]` | 0..1 |
| `JetState.thrust` | `sim/flightmodel/engine/POINT_thrust[i]` | N |
| `GenericState.engaged` | `sim/flightmodel/engine/ENGN_running[i]` | bool |

## Channel reference

Cadence: **stream** = per-tick in `MotionObject.channels`; **session** =
current value in `ObjectDescriptor.values` (discovery, re-sent on change).
Per-instance channels use 1-based index suffixes (`engine[1].n1` reads
dataref element 0), as in the MSFS 2024 reference.

### Ratified channels (CHANNELS.md)

| Channel | Dataref | Notes |
|---|---|---|
| `engine.rpm` | `sim/cockpit2/engine/indicators/engine_speed_rpm[0]` | engine 1 |
| `engine.throttle` | `sim/cockpit2/engine/actuators/throttle_ratio[0]` | 0..1 |
| `engine.torque` | `sim/cockpit2/engine/indicators/torque_n_mtr[0]` | Nm |
| `engine.running` | `sim/flightmodel/engine/ENGN_running[0]` | boolean |
| `vehicle.speed` | `sim/flightmodel/position/groundspeed` | m/s |
| `brakes.pedal` | max of `sim/cockpit2/controls/left_brake_ratio`, `right_brake_ratio` | 0..1 |
| `fuel.level` | `sim/flightmodel/weight/m_fuel_total` ÷ (`sim/aircraft/weight/acf_m_fuel_tot` × 0.45359237) | 0..1; capacity is in lb |
| `session.paused` | `sim/time/paused` | boolean, every motion frame (C-11) |

### Position / geo (stream)

| Channel | Type | Unit | Dataref |
|---|---|---|---|
| `position.lat` / `position.lon` | number | rad | `sim/flightmodel/position/latitude/longitude` (double deg → rad; Float32 ≈ 1 m, display-grade, C-9) |
| `position.altMsl` | number | m | `sim/flightmodel/position/elevation` |
| `env.heightFromGround` | number | m | `sim/flightmodel/position/y_agl` |

### Air data (stream)

| Channel | Unit | Dataref |
|---|---|---|
| `air.speedIndicated` | m/s | `sim/flightmodel/position/indicated_airspeed` (kt ×0.514444) |
| `air.speedTrue` | m/s | `sim/flightmodel/position/true_airspeed` |
| `air.mach` | — | `sim/flightmodel/misc/machno` |
| `air.verticalSpeed` | m/s | `sim/flightmodel/position/vh_ind` |
| `air.alpha` / `air.beta` | rad | `sim/flightmodel/position/alpha` / `beta` (deg) |
| `air.alphaX/Y/Z` | rad/s2 | `sim/flightmodel/position/Q_dot`, `R_dot`, `P_dot` (deg/s²); x pitch, y yaw, z roll, as `angularVelocity` |
| `air.turnBall` | — | `sim/flightmodel/misc/slip`, −1..1, + = ball right of centre |
| `air.loadFactor` | — | `sim/flightmodel/forces/g_nrml`; 1 in level flight |
| `air.flightPathAngle` | rad | `sim/flightmodel/position/vpath` (deg) |
| `air.onGround` | boolean | `sim/flightmodel/failures/onground_any` |
| `nav.headingMagnetic` | rad | `sim/flightmodel/position/mag_psi` (deg) |
| `nav.track` | rad | `sim/flightmodel/position/hpath` (deg) |
| `nav.magneticVariation` | rad | `sim/flightmodel/position/magnetic_variation` (deg); session |

### Wind / weather (stream unless noted)

| Channel | Unit | Dataref | Notes |
|---|---|---|---|
| `wind.trueSpeed` | m/s | `sim/weather/aircraft/wind_now_speed_msc` | |
| `wind.trueDirection` | rad | `sim/weather/aircraft/wind_now_direction_degt` | **from** convention (C-7), deg → rad |
| `wind.x/y/z` | m/s | `sim/weather/aircraft/wind_now_x/y/z_msc` | (x, y, −z); vector points toward where the air moves (C-7) — verify direction at capture |
| `env.visibility` | m | `sim/weather/aircraft/visibility_reported_sm` | statute mile ×1609.344; session |
| `env.precipOnAircraft` | — | `sim/weather/aircraft/precipitation_on_aircraft_ratio` | 0..1 |
| `env.thermalRate` | m/s | `sim/weather/aircraft/thermal_rate_ms` | |
| `env.qnh` | Pa | `sim/weather/aircraft/qnh_pas` | session |

### Controls (stream)

| Channel | Unit | Dataref |
|---|---|---|
| `ctrl.elevator` / `ctrl.aileron` / `ctrl.rudder` | −1..1 | `sim/cockpit2/controls/yoke_pitch_ratio` / `yoke_roll_ratio` / `yoke_heading_ratio` (pilot input; signs match C-5) |
| `ctrl.total.elevator/aileron/rudder` | −1..1 | `sim/cockpit2/controls/total_pitch_ratio/total_roll_ratio/total_heading_ratio` (input + autopilot + stability augmentation) |
| `ctrl.trim.elevator/aileron/rudder` | −1..1 | `sim/cockpit2/controls/elevator_trim/aileron_trim/rudder_trim` |
| `ctrl.flaps` | 0..1 | `sim/cockpit2/controls/flap_handle_request_ratio` (handle) |
| `flaps.deployed` | 0..1 | `sim/cockpit2/controls/flap_system_deploy_ratio` (surfaces) |
| `ctrl.spoilers` | — | `sim/cockpit2/controls/speedbrake_ratio` (handle; 0..1, −0.5 = armed, as sent) |
| `spoilers.deployed` | 0..1 | `sim/flightmodel2/controls/speedbrake_ratio` (surfaces) |
| `brakes.left` / `brakes.right` | 0..1 | `sim/cockpit2/controls/left_brake_ratio` / `right_brake_ratio` |
| `gear.handleDown` | boolean | `sim/cockpit2/controls/gear_handle_down`; session |

### Gear (stream; `gear[n]` matches drive point `gear[n]`)

| Channel | Unit | Dataref |
|---|---|---|
| `gear[n].position` | 0..1 | `sim/flightmodel2/gear/deploy_ratio[n−1]` |
| `gear[n].steerAngle` | rad | `sim/flightmodel2/gear/tire_steer_actual_deg[n−1]`, + = right (C-4) |
| `gear[n].loadForce` | N | `sim/flightmodel2/gear/tire_vertical_force_n_mtr[n−1]` (newtons, despite the unit label) |
| `gear[n].damperVelocity` | m/s | `sim/flightmodel2/gear/total_deflection_rate[n−1]`, + = compressing |
| `gear[n].brake` | 0..1 | `sim/flightmodel2/gear/tire_part_brake[n−1]` |
| `gear.force.x/y/z` | N | `sim/flightmodel/forces/fside_gear`, `fnrml_gear`, −`faxil_gear` (ground reaction, body axes; `faxil` is positive aft) |

### Engines (stream; `engine[n]`, n = dataref index + 1, up to `acf_num_engines`)

| Channel | Unit | Dataref |
|---|---|---|
| `engine[n].n1` / `engine[n].n2` | 0..1 | `sim/cockpit2/engine/indicators/N1_percent` / `N2_percent` (% ×0.01) |
| `engine[n].rpm` | rpm | `sim/cockpit2/engine/indicators/engine_speed_rpm` |
| `engine[n].propRpm` | rpm | `sim/cockpit2/engine/indicators/prop_speed_rpm` |
| `engine[n].itt` / `engine[n].egt` | degC | `sim/flightmodel2/engines/ITT_deg_cel` / `EGT_deg_cel` |
| `engine[n].oilPressure` | Pa | `sim/cockpit2/engine/indicators/oil_pressure_psi` (×6894.757) |
| `engine[n].fuelFlow` | kg/s | `sim/cockpit2/engine/indicators/fuel_flow_kg_sec` |
| `engine[n].manifoldPressure` | Pa | `sim/cockpit2/engine/indicators/MPR_in_hg` (×3386.389) |
| `engine[n].torque` | Nm | `sim/cockpit2/engine/indicators/torque_n_mtr` |
| `engine[n].throttle` / `mixture` / `propLever` | 0..1 | `sim/cockpit2/engine/actuators/throttle_ratio` / `mixture_ratio` / `prop_ratio` |
| `engine[n].reverser` | 0..1 | `sim/flightmodel2/engines/thrust_reverser_deploy_ratio` |
| `engine[n].running` | boolean | `sim/flightmodel/engine/ENGN_running` |

Oil temperature (`sim/cockpit2/engine/indicators/oil_temperature_deg_C`)
reads °C or °F depending on the aircraft, with no flag that says which, so
the reference leaves it out.

### Fuel / mass (stream, slow)

| Channel | Unit | Dataref |
|---|---|---|
| `fuel.quantity` | kg | `sim/flightmodel/weight/m_fuel_total` |
| `fuel.tank[n]` | kg | `sim/flightmodel/weight/m_fuel[n−1]` (9 tanks; empty tanks read 0) |
| `mass.total` | kg | `sim/flightmodel/weight/m_total` |
| `mass.cg.x` / `mass.cg.z` | m | `sim/flightmodel2/misc/cg_offset_x` / −`cg_offset_z` |

### Warnings (stream, boolean)

`warn.masterWarning`, `warn.masterCaution`, `warn.stall`, `warn.gearUnsafe`,
`warn.lowVoltage`, `warn.hydraulicPressure`, `warn.fuelQuantity` from
`sim/cockpit2/annunciators/master_warning`, `master_caution`,
`stall_warning`, `gear_unsafe`, `low_voltage`, `hydraulic_pressure`,
`fuel_quantity`; `warn.overG`, `warn.overVne`, `warn.overVfe` from
`sim/flightmodel/failures/over_g`, `over_vne`, `over_vfe`;
`warn.oilPressureLow[n]` from `sim/cockpit2/annunciators/oil_pressure_low`.

### Electrics / cabin (session or slow stream)

| Channel | Unit | Dataref |
|---|---|---|
| `elec.battery[n]` | boolean | `sim/cockpit2/electrical/battery_on` |
| `elec.generator[n]` | boolean | `sim/cockpit2/electrical/generator_on` |
| `elec.busVoltage[n]` | V | `sim/cockpit2/electrical/bus_volts` |
| `elec.avionics` | boolean | `sim/cockpit2/switches/avionics_power_on` |
| `elec.apuRunning` | boolean | `sim/cockpit2/electrical/APU_running` |
| `cabin.altitude` | m | `sim/cockpit2/pressurization/indicators/cabin_altitude_ft` (×0.3048) |
| `cabin.verticalSpeed` | m/s | `sim/cockpit2/pressurization/indicators/cabin_vvi_fpm` (×0.00508) |
| `cabin.canopy` | 0..1 | `sim/flightmodel2/misc/canopy_open_ratio` |

### Lights (session)

`light.landing`, `light.nav`, `light.strobe`, `light.beacon`, `light.taxi`
(boolean) from `sim/cockpit2/switches/landing_lights_on`,
`navigation_lights_on`, `strobe_lights_on`, `beacon_on`, `taxi_light_on`.

### Autopilot / radios (session)

| Channel | Unit | Dataref |
|---|---|---|
| `ap.on` | boolean | `sim/cockpit2/autopilot/autopilot_on` |
| `ap.flightDirector` | — | `sim/cockpit2/autopilot/flight_director_mode` (0 off, 1 on, 2 on with servos) |
| `ap.altitude` | m | `sim/cockpit2/autopilot/altitude_dial_ft` (×0.3048) |
| `ap.heading` | rad | `sim/cockpit2/autopilot/heading_dial_deg_mag_pilot` (deg, magnetic) |
| `ap.airspeed` | — | `sim/cockpit2/autopilot/airspeed_dial_kts_mach` (knots or Mach, as sent) |
| `ap.verticalSpeed` | m/s | `sim/cockpit2/autopilot/vvi_dial_fpm` (×0.00508) |
| `nav.com1.active` / `nav.com1.standby` | Hz | `sim/cockpit2/radios/actuators/com1_frequency_hz_833` / `com1_standby_frequency_hz_833` (kHz ×1000) |
| `nav.nav1.active` | Hz | `sim/cockpit2/radios/actuators/nav1_frequency_hz` (10 kHz units ×10,000) |
| `nav.nav1.hdef` / `nav.nav1.vdef` | — | `sim/cockpit2/radios/indicators/nav1_hdef_dots_pilot` / `nav1_vdef_dots_pilot` (dots, as sent); stream |
| `nav.xpdr.code` | — | `sim/cockpit2/radios/actuators/transponder_code` (four octal digits as a decimal number, as sent) |

COM2, NAV2, ADF and GPS follow the same pattern from the
`sim/cockpit2/radios/*` families.

### Session / misc (session)

| Channel | Unit | Dataref |
|---|---|---|
| `session.replay` | boolean | `sim/time/is_in_replay` |
| `session.simRate` | — | `sim/time/sim_speed_actual` |
| `session.timeZulu` / `session.timeLocal` | s | `sim/time/zulu_time_sec` / `local_time_sec` (since midnight); stream |
| `session.crashed` | boolean | `sim/flightmodel2/misc/has_crashed`; stream |
| `perf.frameRate` | Hz | 1 ÷ `sim/operation/misc/frame_rate_period`; stream |
| `aircraft.icao` / `aircraft.tailNumber` | text | `sim/aircraft/view/acf_ICAO` / `acf_tailnum` |

## Events

| Event | Source | Notes |
|---|---|---|
| `body.impact` | rising edge of `sim/flightmodel/failures/onground_any` | touchdown; intensity from \|`vh_ind`\| at the edge (sender-chosen normalisation, e.g. ÷3 m/s clamped to 1); direction (0, −1, 0) |
| `body.impact` | rising edge of `sim/flightmodel2/misc/has_crashed` | intensity 1 |
| `fail.<name>` | a `sim/operation/failures/rel_*` dataref becoming inoperative | see *Failures* |

## Failures

X-Plane 12 has ~800 `sim/operation/failures/rel_*` datarefs (failure
enum per system). Publishing each as a channel would dominate the
descriptor set while almost all read "working". The reference publishes:

- `fail.active` (number, session): the count of failures currently
  inoperative;
- one `fail.<name>` event when a failure becomes inoperative, named after
  the dataref suffix (`fail.engfai0`).

A sender that needs individual failure states (a cockpit with failure
lights) publishes the relevant `rel_*` datarefs as session values under
*Further datarefs*.

## Other aircraft

TCAS targets (`sim/cockpit2/tcas/targets/*`, up to 64, with
`sim/cockpit2/tcas/indicators/tcas_num_acf` in use) are other aircraft. They
map to non-primary objects (`ObjectType.aircraft`, named `traffic[n]`),
not to channels on the user's aircraft:

| OGS-TS field | Dataref source |
|---|---|
| `position` | `sim/cockpit2/tcas/targets/position/x/y/z[n]` → (x, y, −z) |
| `orientation` | `…/psi`, `…/the`, `…/phi[n]` (deg → rad, as for the user aircraft) |
| `kinematics.velocity` | `…/vx/vy/vz[n]` → (x, y, −z) |
| `typeLabel` | `sim/cockpit2/tcas/targets/icao_type` (string slot n) |

As with iRacing's grid: the primary object streams at full rate, and
traffic objects are throttled (e.g. 10 Hz) or distance-filtered.

## Further datarefs

The mechanism is total: any readable dataref can be a channel. A sender
offering more than this reference names each extra channel after its
dataref path (`sim/cockpit2/switches/...`), so users and receivers can
look it up in the X-Plane catalogue.

- Units convert to C-3 where the dataref's unit is known (knots, feet,
  degrees, psi, inHg, statute miles, as above).
- A dataref whose unit X-Plane leaves open (`any`, "units vary by
  plane", enums, bitfields) is declared with unit `""` and a description
  saying the value is as sent, with its meaning.
- Arrays are index-suffixed (`…[1]` for element 0).
- Rarely-changing datarefs ride session `values`.

## Sender notes

- **Catalogue size.** The curated set is ~125 names and ~180 values for
  a twin, so discovery is ~20 KB in ~15 pages (~10 KB/s at the
  2-second re-send): paged discovery, motion parts and
  bounded refresh carry it (implementation-udp.md § Datagram budget).
  Pose, dynamics and drive points ride the first datagram of every tick.
  The set's values fit one datagram per tick, inside the sender size
  envelope (implementation-udp.md § Sender size envelope). Datarefs
  beyond it are for X-Plane's own APIs; a sender adding many under
  *Further datarefs* leaves the envelope.
- **Writable datarefs are read like any other.** Filtering the catalogue
  on `access_mode = READONLY` drops most core telemetry.
- **Overridden values.** Many datarefs hold whatever a plugin writes
  while an `sim/operation/override/*` flag is set (flight controls,
  joystick, TCAS). A sender reports what X-Plane reports and does not
  interpret overrides.
- **Missing wheel quantities.** X-Plane has no wheel torque or brake
  pressure, so wheels leave both unset (`noTorque`, `noBrakePressure`);
  braking intensity is `gear[n].brake`.
- **Sign checks.** Verify the specific-force and angular-rate signs, the
  `wind.x/y/z` direction and `air.turnBall` against the sim at capture,
  before trusting the conversions above.
- **Strings.** `RREF` returns numbers only; read byte-array datarefs
  (`acf_ICAO`, `acf_tailnum`, TCAS `icao_type`) through a plugin or the
  Web API.
- Names follow CHANNELS.md conventions and the MSFS 2024 reference where
  the concept matches, so recurring concepts can be ratified on two-game
  evidence without renaming.
