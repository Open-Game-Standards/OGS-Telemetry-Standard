# Common Channels Annex

Status: informative annex to the OGS-TS v1 schema. Channel names are *data*
carried in `ChannelDescriptor` — this annex has no schema or wire-format
impact. It ratifies well-known channel names **with required units** so
receivers can auto-map telemetry across games without per-game
configuration.

## Units

Channel units follow [CONVENTIONS.md](CONVENTIONS.md) C-3: SI base units
plus a closed whitelist of declared exceptions — `degC` (temperature),
`rpm` (rotational speed). Angles are always `rad`. Never degrees,
`km/h`, `kt`, `bar`, or `psi`; senders convert at the source.

## For senders

- If a channel's concept matches a ratified name below, use the ratified
  name, type, and unit exactly (`engine.rpm` is `rpm` and a number), and
  declare that type in the descriptor's `type`.
- You MUST NOT reuse a ratified name with a different unit — that is a
  different channel; give it your own name.
- Concepts not covered: name freely (`boat.anchorDepth`, `mech.reactorHeat`).
  Anything recurring may be ratified later (see below).

## For receivers

Match **exactly** on the ratified name — never fuzzy-match or substring-match
ratified names. A channel whose name+unit match an annex entry can be bound
with zero configuration. For everything else, fall back to per-game profiles.
Discovery always carries the sender's name and unit, so this annex is a
semantic convenience, never a dependency.

## Naming conventions (families — not ratified entries)

Some channel families recur across domains without single fixed semantics.
Use these prefixes so receivers can group them; individual names remain
free-form until a specific entry is ratified:

- `ctrl.*` — control inputs beyond the ratified ones below (`ctrl.total.*`
  after augmentation, `ctrl.steering.input`, …). Signs follow CONVENTIONS
  C-5: a positive input produces the positive rotation about the matching
  body axis.
- `wind.*` — per-tick wind: `wind.trueSpeed` / `wind.apparentSpeed` (m/s),
  `wind.trueDirection` / `wind.apparentAngle` (rad). Direction follows the
  meteorological **from** convention in the world frame; apparent angle is
  relative to the nose, positive = from the right (CONVENTIONS C-7);
  vector channels `wind.x/y/z` point toward where the air moves.
  Wind changes per gust, so it rides motion-frame channels — never the
  discovery-static `environment`.
- `air.*` — air data beyond the ratified entries below (`air.alphaX/Y/Z`
  angular accelerations, `air.variometer`, …).

Further entries in these families are ratified as their naming stabilizes
across ≥2 games.

## Ratification rules

1. The concept must exist in at least **two shipping games** (or clear
   equivalents across domains — e.g. `engine.rpm` for a car and a boat's
   propeller shaft).
2. Additions are pull requests to this file; OGS reviews for name quality
   (lowercase, dotted hierarchy), unit sanity, and non-overlap.
3. Entries are never renamed or re-united — corrections supersede by adding
   a new name and noting the deprecation inline.

## Ratified channels (v1)

| Name | Type | Unit | Description |
|---|---|---|---|
| `engine.rpm` | number | `rpm` | Crankshaft / shaft revolutions per minute |
| `engine.throttle` | number | — | Driver throttle input, −1..1 (C-3): −1 = full reverse thrust, 0 = idle/no thrust, +1 = full forward. Unidirectional vehicles simply send 0..1; reverse-by-gear cars keep the pedal here 0..1 and express direction via `transmission.gear` |
| `engine.torque` | number | `Nm` | Current engine output torque |
| `engine.temperature` | number | `degC` | Coolant / motor temperature |
| `engine.running` | boolean | — | Engine/motor currently producing power |
| `transmission.gear` | number | — | −1 reverse, 0 neutral, 1…n forward |
| `vehicle.speed` | number | `m/s` | Speed over ground (display conversions are the receiver's job) |
| `brakes.pedal` | number | — | Driver brake input, 0..1 (C-3) |
| `brakes.pressure` | number | `Pa` | Master cylinder brake pressure |
| `ctrl.steering.angle` | number | `rad` | Handwheel angle, + = right (C-4); the road wheel's own angle is schema `steerAngle` (C-6) |
| `input.clutch` | number | — | Driver clutch input, 0..1 (C-3) |
| `lights.headlights` | boolean | — | Headlights on |
| `lights.highBeam` | boolean | — | High beams on |
| `lights.wipers` | boolean | — | Wipers active |
| `lights.turnSignal` | number | — | −1 left, 0 none, 1 right |
| `aids.abs` | boolean | — | Anti-lock braking currently active |
| `aids.tcs` | boolean | — | Traction control currently active |
| `aids.esp` | boolean | — | Stability control currently active |
| `fuel.level` | number | — | Remaining fuel/energy fraction, 0..1 (C-3) |
| `fuel.rate` | number | `m3/s` | Current consumption rate (L/h ÷ 3.6e6) |
| `session.paused` | boolean | — | Simulation paused for the player (pause menu, sim pause). Carried in every motion frame; senders keep streaming while paused (C-11). Evidence: MSFS 2024 (SimConnect pause state, reference-msfs2024.md), X-Plane `sim/time/paused`, Assetto Corsa / ACC shared-memory status `AC_PAUSE` |
| `session.replay` | boolean | — | A replay is playing rather than live simulation. Receivers treat it like a pause by default (CONVENTIONS C-11). Evidence: X-Plane `sim/time/is_in_replay`, iRacing `IsReplayPlaying`, Assetto Corsa / ACC status `AC_REPLAY` |
| `session.simRate` | number | — | Simulation time per real time: 1 = real time, 4 = 4× accelerated, 0.5 = slow motion. Evidence: X-Plane `sim/time/sim_speed_actual`, MSFS `SIM RATE` |
| `air.indicatedAirspeed` | number | `m/s` | Indicated airspeed |
| `air.trueAirspeed` | number | `m/s` | True airspeed |
| `air.verticalSpeed` | number | `m/s` | Rate of climb, + = climbing |
| `air.mach` | number | — | Mach number |
| `air.aoa` | number | `rad` | Angle of attack, + = nose above the flight path |
| `air.beta` | number | `rad` | Sideslip angle, + = relative wind from the right (as C-7 apparent angles) |
| `air.loadFactor` | number | — | Normal load factor in g, 1 in level flight |
| `air.turnBall` | number | — | Slip/skid ball, −1..1, + = ball right of centre |
| `ctrl.elevator` | number | — | Pilot pitch input, −1..1, + = nose-up (C-5) |
| `ctrl.aileron` | number | — | Pilot roll input, −1..1, + = roll right-down (C-5) |
| `ctrl.rudder` | number | — | Pilot yaw input, −1..1, + = nose-right (C-5) |
| `ctrl.flaps` | number | — | Flap lever, 0..1 (0 = retracted) |
| `ctrl.spoilers` | number | — | Spoiler / speedbrake lever, 0..1 (0 = retracted; an armed state rides its own channel) |
| `ctrl.trim.elevator` / `ctrl.trim.aileron` / `ctrl.trim.rudder` | number | — | Trim, −1..1, signs as the matching control (C-5) |
| `gear.position` | number | — | Landing gear extension, 0 = up, 1 = down |

Evidence for the `air.*`, `ctrl.*` and `gear.position` entries: MSFS 2024,
X-Plane 12, DCS World, Falcon BMS and IL-2 (the sender references and the
OGS-TS Bridge's sources for them).

Deliberately out of scope for now: race state (`race.lap`,
`race.position`, lap timing) — recurring, but domain-specific enough to go
through the ratification process as a real first test of it.

## Event names (unratified — same process as channels)

`EventFrame` stimuli (CONVENTIONS C-10) use dot-namespaced names, ratified
by the same ≥2-game bar as channels. Candidates seen in the wild so far
(none yet two-game, none ratified):

| Name | Notes |
|---|---|
| `body.impact` | collision, direction + intensity |
| `weapon.fire` | the player's own weapon firing |
| `weapon.hit` | being hit; direction points toward the shooter |
| `explosion` | high-intensity, often sustained |
| `surface.scrape` | duration > 0 sustain window |
| `footstep.stomp` | heavy footfall (also derivable from `LegState.contact`) |

Senders facing a concept not listed: name freely, exactly as with
channels (`mech.stomp`, `space.decompress`). Reuse only exact ratified
names.
