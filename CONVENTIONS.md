# OGS-TS Conventions (normative)

One closed set of conventions for every value on the wire. Schema field
comments, `CHANNELS.md` families, and per-game references cite these clauses
by number (`C-3`); nothing may contradict them. Adding or changing a clause
is a spec change (see DESIGN.md, Evolution).

## C-1 Frames

- **World frame** — left-handed, +Z forward, +Y up, +X right, meters,
  seconds.
- **Body frame** — the world frame rotated by the object's quaternion:
  x +right (sway), y +up (heave), z +forward (surge).
- **Object-local frame** — one sender-chosen origin per object (typically
  the CG), used by drive-point offsets and named points; declared via
  `referencePoint` + `namedPoints`.
- **Down** — unless declared otherwise (C-12), gravity acts along world −Y.

## C-2 Orientation

Orientation is a unit quaternion (x/y/z/w). Senders normalize; receivers may
renormalize defensively. Either sign is the same rotation — receivers must
not prefer one sign. The quaternion rotates **world axes into body axes**.
A sender that does not measure orientation sends the identity quaternion
`(0, 0, 0, 1)`; all-zero is not a rotation.

## C-3 Units

SI base units everywhere, with one closed whitelist of declared exceptions:

| Quantity | Unit | Status |
|---|---|---|
| length, velocity, acceleration, force, pressure | m, m/s, m/s², N, **Pa** | SI |
| angles, angular rates | **rad**, **rad/s** | SI — never degrees |
| temperature | **°C** | declared exception |
| rotational speed | **rpm** | declared exception |
| normalized quantities | 0..1 (unipolar), −1..1 (bipolar) | unitless (`""`) |

Extending the whitelist is a spec change; a unit outside this table never
rides the wire. Channel `unit` strings use exactly these spellings
(`degC`, `rpm`, `Pa`, …). Receivers trust the declaration and never guess
units onto the wire.

`°C` and `rpm` are the only two exceptions because, unlike velocity,
acceleration, force, and pressure, neither quantity typically feeds
further receiver-side math: washout filters, FFB force calculations, and
cueing transforms consume m/s, m/s², N, and Pa directly, so keeping those
SI avoids a hidden conversion before they can be used. Temperature and
rotational speed are terminal — read by a gauge, dashboard, or logger and
nothing else — so there SI buys the wire nothing, and the exception
matches what every tachometer and thermometer already shows. Speed does
not get the same exception despite `km/h`/`mph` being the common dashboard
unit, because velocity is exactly the kind of value consumer-side
kinematics (interpolation, derived acceleration, cueing) operates on
directly, the same reason pressure and force stay SI.

## C-4 Rotation sign

Rotations follow the body axes of C-1: **+pitch = nose-up (about x),
+yaw = nose-right (about y), +roll = right-wing/ right-side down (about
z)**. In this left-handed frame, a positive rotation about an axis appears
clockwise when viewed looking along that axis. Every angular quantity on
the wire (angular velocity, Euler-derived angles, steering angles) uses
this same sense — positive steering turns the same direction as +yaw:
**positive = right**. Symmetric-pair deflections (wing flap) are positive
= tip up on either side.

## C-5 Control inputs

Driver/control input channels (`ctrl.*`) follow the same rule as C-4: a
positive input produces the positive rotation about the corresponding body
axis — `ctrl.elevator` + = nose-up, `ctrl.rudder` + = nose-right,
`ctrl.aileron` + = roll right-down, `ctrl.steering.angle` + = steering
right. Pedals/levers are 0..1 (C-3). Control inputs describe what the
*driver* did; effects on the vehicle live in schema fields or other
channels (C-6).

## C-6 Identity — what a value measures

A value lives on the physical object it is named for. Schema fields in a
`WheelState` describe that road wheel; `steerAngle` is the angle of that
wheel about its steer axis, **not** the handwheel (that is
`ctrl.steering.angle`). Anything measuring the driver's input is a `ctrl.*`
channel; anything measuring the vehicle's state is a schema field or
object/channel state. When a source mixes these (stick position vs.
orientation), senders resolve the identity before naming the value.

## C-7 Wind

`wind.*Direction` is the meteorological **from** convention, radians, in
the world frame of C-1 (direction from which the wind blows, measured as
yaw about +Y). Apparent-wind angles are relative to the object's nose,
**positive = from the right**. Wind vector components (`wind.x/y/z`) point
**toward** where the air moves, world frame (a vector, not a bearing).

## C-8 Timestamps

`MotionFrame.timestamp` is seconds since the session anchor
(`sessionStartUnixUs`, µs wall clock, from discovery). Timestamps are
monotonic within a session; a new anchor value declares a new session.

## C-9 Precision

All wire floats are Float32, not Float64: every consumer class (motion
cueing, haptics, dashboards) renders or actuates from the value within
one frame, so the ~7 decimal digits of relative precision Float32 gives
is already well past what a physical actuator or a human eye resolves,
and halving every float field's wire cost matters at 60-120 Hz where
Float64 would not buy a receiver anything it can use. The one place this
trades against absolute magnitude is large worlds, handled structurally
rather than by widening the type: world `position` assumes a
session-stable local origin, so large-world senders re-origin on
teleport/session start rather than emitting absolute planetary
coordinates. Geographic lat/lon rides channels, where Float32 gives ~1 m
precision at Earth magnitudes — display-grade, not navigation-grade;
senders needing more split degrees from fractional degrees.

## C-10 Events

`EventFrame` carries discrete stimuli (impacts, gunfire, footsteps) for
haptic and cueing consumers. Each event carries a session-monotonic `id`;
the transport is lossy, so senders SHOULD re-carry recent events (~100 ms
window) and receivers MUST dedup by id. A sender MUST send every event at
least once, however slowly it ticks, and keeps every event frame within the
datagram budget (implementation-udp.md § Event splitting). `intensity` is 0..1 normalized
(C-3). `duration` is seconds: 0 = momentary impulse, >0 = a sustain
window the consumer may render continuously. `direction` is optional,
in the body frame (C-1) of the associated object, and points **toward the
source** of the stimulus — a hit from the left has −x. Event names use
dot-namespaced strings ratified like channel names (CHANNELS.md).

## C-11 Pause

A pause (pause menu, sim pause, photo mode, any state where simulation
time stops for the player) is not the end of a session. Without a signal,
a paused sender is indistinguishable from a dead one, and a motion rig
holds whatever attitude the game froze in.

Senders:

- A sender that can tell when its game is paused SHOULD declare the
  ratified boolean channel `session.paused` (CHANNELS.md) on its primary
  object and carry its value in **every** motion frame, so a receiver
  that joins mid-pause sees it on the first frame.
- While paused, a sender MUST keep sending: discovery on its normal
  re-send cadence and motion frames at its normal rate, under the same
  session anchor, with timestamps that keep advancing (C-8 — they are
  wall-clock, not game time). Pose carries the frozen values.
- While paused, a sender SHOULD send `noDynamics`: no specific force or
  angular rates are measured while the simulation is stopped, and a
  derivative taken across the pause boundary is meaningless.
- While paused, a sender SHOULD NOT send new events (C-10), and SHOULD
  discard events queued before the pause rather than send them after it:
  actuators are settling, and a stimulus from before the stop is stale.
- A sender that cannot tell when its game is paused does not declare the
  channel.

Receivers:

- While `session.paused` is true, receivers SHOULD bring actuators to
  rest at a gentle, receiver-chosen rate (motion platforms toward their
  neutral or park position) and SHOULD stop rendering haptic output; on
  resume they SHOULD return to the live values without a step.
- A pause MUST NOT count toward staleness or session end
  (implementation-udp.md, Liveness): the sender is still streaming.
- An undeclared `session.paused` means the sender does not report
  pauses, never "paused".

Replay and simulation rate:

- A replay is not live simulation: the motion is a recording the player
  watches. While `session.replay` is true, receivers SHOULD behave as for
  a pause by default; a user may opt in to motion during replays.
- `session.simRate` is simulation time per real time. Pose and dynamics
  are reported as the simulation computes them, so at a rate other than 1
  accelerations are the accelerated simulation's. Receivers SHOULD bring
  actuators to rest when the rate is not 1, unless the user opts in.
  Timestamps stay wall-clock (C-8).

## C-12 Gravity

Gravity is a vector **g** in the world frame (C-1), m/s², pointing the way
gravity pulls (toward the attracting mass). Each object has one
**effective gravity** per motion frame, resolved in this order:

1. `MotionObject.localGravity.vector`, when selected in that frame;
2. otherwise `Environment.gravityVector`, when selected;
3. otherwise (0, −`Environment.gravity`, 0).

A zero vector is a real value (weightless), never "not provided"; absence
is always the `Void` default of the union.

Dynamics are defined against the effective gravity:

- `kinematics.acceleration` is coordinate acceleration **a**, gravity
  excluded.
- `bodyDynamics.specificForce` is **f** = q⁻¹ · (**a** − **g**), what an
  accelerometer at the reference point reads. At rest under default
  gravity it is (0, +`gravity`, 0) in the body frame of a level object.
- Receivers convert between the two with **a** = q · **f** + **g**, and
  remove the gravity reaction from specific force with
  q⁻¹ · **a** = **f** + q⁻¹ · **g**.

Senders:

- `Environment.gravity` is always the magnitude of the session gravity,
  also when `gravityVector` is set (|`gravityVector`|), so a receiver that
  reads only the scalar still has the right value.
- A sender whose session gravity does not point along world −Y sets
  `Environment.gravityVector`. Discovery is re-sent when it changes (as
  for any environment change), so it suits values that change rarely.
- A sender whose gravity varies by object position or changes faster than
  discovery re-sends (planet surfaces, rotating habitats, multi-body
  scenes) sets `localGravity.vector` on the
  affected objects. The field describes its own frame only: a sender
  using it carries it in **every** motion frame for that object, so a
  receiver that joins mid-session sees it on the first frame.
- A sender reporting `bodyDynamics` computes specific force against the
  same effective gravity it declares.

Receivers:

- Resolve the effective gravity per object and frame as above. A
  receiver that does not read `localGravity` or `gravityVector` falls
  back to the scalar along world −Y.
- Receivers that present acceleration in multiples of g choose their own
  reference (standard gravity 9.80665 m/s² or the effective magnitude);
  the wire stays in m/s² (C-3).
