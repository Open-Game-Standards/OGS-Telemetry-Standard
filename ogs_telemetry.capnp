# Open Game Standards — OGS Telemetry Standard, schema v1 (two-layer)
#
# Layers (see DESIGN.md):
#   DiscoveryFrame — low rate: once per session, re-sent on change. Self-describing
#                    metadata: environment, objects, drive points, channel descriptors.
#   MotionFrame    — high rate (~60 Hz): bare kinematics + state values, keyed by the
#                    ids declared in DiscoveryFrame.
#
# Principles:
#   - Static metadata lives in discovery; per-frame samples stay bare (no repeated
#     units/ranges/enums on the wire).
#   - Domain generality: drive points are a union (wheel/propeller/jet/sail/leg/generic);
#     channels are typed key-values declared up front — any game, any domain.
#   - Unknown-field skipping in both directions: receivers ignore unknown fields and
#     unknown union variants, so v1.x can add without breaking deployed decoders.

@0xea4c1f1039af078e;

# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

struct Vector3 {
  x @0 :Float32;
  y @1 :Float32;
  z @2 :Float32;
}

struct Quaternion {
  # Unit quaternion (senders must normalize; receivers may renormalize
  # defensively). Either sign represents the same rotation. Rotates OGS-TS
  # world axes (left-handed, Z-forward, Y-up) into object body axes.
  x @0 :Float32;
  y @1 :Float32;
  z @2 :Float32;
  w @3 :Float32;
}

struct Range {
  min @0 :Float64;
  max @1 :Float64;
}

enum ObjectType {
  # Coarse classification for cueing-preset selection and UI. Fine-grained
  # domain hints live in the drive-point union (wheel/propeller/sail/leg).
  # Unknown enumerants survive round-trips (UInt16 on the wire), so new
  # values may be ratified in v1.x without breaking deployed receivers.
  # `other` holds the zero value so the catch-all never interleaves with
  # real classes as the set grows (additions append below), and an unset
  # type decodes as "unknown" instead of guessing a cueing preset.
  other      @0;   # escape hatch — never force a wrong class
  vehicle    @1;   # ground: car, kart, tank
  aircraft   @2;   # plane, helicopter, drone
  watercraft @3;   # boat, ship, submarine
  spacecraft @4;
  humanoid   @5;   # on-foot player or NPC
  camera     @6;   # spectator / free camera
  creature   @7;   # horse, dragon, alien — pose core is domain-agnostic;
                   # taxonomy detail rides typeLabel ("dragon", "warhorse")
}

enum ContactMedium {
  # `other` holds the zero value so the catch-all never interleaves with
  # real mediums as the set grows (additions append below), and an unset
  # medium decodes as "unknown" rather than guessing a real medium.
  other       @0;
  air         @1;
  asphalt     @2;
  dirt        @3;
  grass       @4;
  gravel      @5;
  rumbleStrip @6;
  water       @7;
  snow        @8;
  ice         @9;
  vacuum      @10;
}

struct Environment {
  # Ambient conditions of the simulation medium. Sent in discovery; may be
  # re-sent on change (e.g. entering water). Units per CONVENTIONS C-3.
  airDensity @0 :Float32;   # kg/m^3
  temperature @1 :Float32;  # °C (declared exception, C-3)
  pressure @2 :Float32;     # Pa
  gravity @3 :Float32;      # m/s^2, magnitude; equals |gravityVector| when that is set
  medium @4 :ContactMedium; # dominant surrounding medium
  union {
    # Gravity direction (CONVENTIONS C-12).
    noGravityVector @5 :Void;  # default: gravity acts along world -Y, magnitude `gravity`
    gravityVector @6 :Vector3; # m/s^2, world frame, pointing the way gravity pulls
  }
}

# ---------------------------------------------------------------------------
# Discovery frame (low rate)
# ---------------------------------------------------------------------------

struct DiscoveryFrame {
  schemaVersion @0 :UInt16;        # 1 for this schema
  gameName @1 :Text;
  sessionStartUnixUs @2 :Int64;    # wall-clock anchor; frame timestamps are relative
  environment @3 :Environment;
  objects @4 :List(ObjectDescriptor);

  # Re-send the whole frame when any descriptor changes (vehicle swap, channel
  # set change). Receivers key purely by ids, so re-sends are non-breaking.

  # Paging (implementation-udp.md § Datagram budget). A descriptor set too
  # large for one datagram is split into pages that share a generation;
  # each page is a self-contained DiscoveryFrame declaring part of it.
  generation @5 :UInt32;           # descriptor-set generation, kept by every sender:
                                   # increments by one (wrapping) whenever any id,
                                   # name, unit, range, drive point or object identity
                                   # changes, never for session `values` alone.
                                   # MotionFrame.generation names the set its ids
                                   # refer to.
  page @6 :UInt16;                 # 0-based index of this page within the generation
  pageCount @7 :UInt16;            # pages in this generation; 0 or 1 = the frame is
                                   # the complete set (unpaged)

  # Sender identity for receivers choosing among several senders on one
  # network (implementation-udp.md § Senders and sessions). Display and
  # pinning only: receivers tell senders apart by source address and port.
  instanceLabel @8 :Text;          # user-set label for this instance, e.g. "Rig 2",
                                   # "Instructor"; "" = none
  host @9 :Text;                   # sender's host name, e.g. "sim-pc"; "" = not given
}

struct ObjectDescriptor {
  # In a paged generation an object may be listed on several pages. The
  # lowest-numbered page listing it carries its full identity (type through
  # drivePoints); later pages listing it carry only further channels and
  # values, and receivers merge them by name. A channel id is declared on
  # exactly one page of a generation.
  name @0 :Text;                   # stable per session; matches MotionObject.name
  type @1 :ObjectType;             # coarse class; ratifiable enum
  location @2 :Text;               # e.g. track/place name (display-only)
  typeLabel @3 :Text;              # optional display label, e.g. "Formula 1 2024";
                                   # receivers may also select per-vehicle
                                   # profiles on it (exact match)
  primary @4 :Bool;                # reference object for motion rigs / compensation;
                                   # exactly one SHOULD be set per discovery frame
  referencePoint @5 :NamedPoint;   # where reported pose/dynamics are measured;
                                   # default (name "", zero) = the object-local
                                   # frame origin (typically the CG)
  namedPoints @6 :List(NamedPoint);# other named vehicle-local points (cg, pilot,
                                   # driver eye, seats...) for consumer corrections
  drivePoints @7 :List(DrivePointDescriptor);
  channels @8 :List(ChannelDescriptor);
  values @9 :List(ChannelValue);    # current values of session-scoped channels
                                   # (rarely-changing datapoints: setup, session
                                   # type, stage name, weather preset). Discovery
                                   # is re-sent when one changes, so late-joining
                                   # receivers get complete state from discovery
                                   # alone. Fast-changing channels stream in
                                   # MotionObject.channels instead; a channel
                                   # lives in one layer — moving it re-sends
                                   # discovery.
  texts @10 :List(TextValue);      # current values of session-scoped text channels
}

struct NamedPoint {
  # A labeled position in the object-local frame (meters; same sender-chosen
  # frame as the drive-point offsets — typically the CG — and the same axes
  # as the orientation quaternion). Reference points let consumers correct
  # received motion to their own pivot/head position (lever-arm corrections):
  #   a_seat = a_ref + alpha x r + omega x (omega x r),   r = seat - referencePoint
  # OGS-TS transports the declared reference and named points; the correction
  # itself is consumer-side. Conventional names: "cg", "pilot", "driverEye".
  name @0 :Text;
  position @1 :Vector3;
}

struct ChannelDescriptor {
  # Declares one generic telemetry channel. Ids are sender-assigned, unique
  # within the object. This is the extension mechanism of the standard: any
  # game can expose any datapoint as a well-documented, typed channel.
  id @0 :UInt16;
  name @1 :Text;                   # stable identifier, e.g. "engine.rpm"
  unit @2 :Text;                   # per CONVENTIONS C-3, e.g. "rpm", "m/s", "degC", "" = unitless
  union {
    # Range is optional: inline struct fields are not nullable, so the
    # discriminant carries the optionality.
    noRange @3 :Void;              # default: unbounded / unknown
    range @4 :Range;               # declared operating range
  }
  description @5 :Text;            # human-readable, shown by dash tools
  type @6 :ChannelType;             # number/boolean ride ChannelValue, text rides TextValue
}

enum ChannelType {
  # Declared value type of a channel, so receivers can lay out and bind a
  # channel before its first value arrives. `unspecified` holds the zero
  # value: an unset type never claims a variant.
  unspecified @0;
  number      @1;
  boolean     @2;
  text        @3;
}

struct SuspensionSpec {
  # Static suspension geometry per drive point.
  travel @0 :Range;                # compression travel, meters
  stiffness @1 :Float32;           # N/m for unit displacement
  damping @2 :Float32;             # N·s/m; 0 = unspecified (force approximation then uses stiffness only)
}

struct DrivePointDescriptor {
  id @0 :UInt16;
  name @1 :Text;                   # e.g. "wheel_front_left"
  offset @2 :Vector3;              # position in the object-local frame, meters.
                                   # One sender-chosen frame per object (typically
                                   # the CG); NamedPoints use the same frame, and
                                   # consumers only use differences, which are
                                   # frame-invariant
  union {
    # Static, type-specific geometry. Extensible: add variants in v1.x —
    # old receivers skip unknown variants (unknown-union discriminant).
    wheel @3 :WheelSpec;
    propeller @4 :PropellerSpec;
    jet @5 :Void;
    sail @6 :Void;
    leg @7 :Void;
    wing @8 :WingSpec;              # also ornithopters / control-wing aircraft
    generic @9 :GenericSpec;         # unspecified drive; state carried by GenericState
  }
}

struct WingSpec {
  flapRange @0 :Range;            # flap angle limits, rad
  span @1 :Float32;               # semi-span of this wing, meters; 0 = unspecified
}

struct WheelSpec {
  radius @0 :Float32;              # meters
  driven @1 :Bool;                 # power delivered through this wheel
  steered @2 :Bool;
  union {
    # Inline struct fields are not nullable, so suspension optionality rides
    # this discriminant — the same pattern as the state structs.
    noSuspension @3 :Void;         # default: not applicable
    suspension @4 :SuspensionSpec; # travel / stiffness / damping
  }
}

struct PropellerSpec {
  diameter @0 :Float32;            # meters
  blades @1 :UInt16;
}

struct GenericSpec {
  ratedForce @0 :Float32;          # rated force magnitude, N; 0 = unspecified
}

# ---------------------------------------------------------------------------
# Motion frame (high rate)
# ---------------------------------------------------------------------------

struct MotionFrame {
  timestamp @0 :Float64;           # seconds since session start (anchor in discovery)
  objects @1 :List(MotionObject);  # primary object first
  generation @2 :UInt32;           # DiscoveryFrame.generation the channel and
                                   # drive-point ids in this frame refer to

  # Parts (implementation-udp.md § Datagram budget). A tick too large for one
  # datagram is sent as parts sharing this timestamp. Each object's pose,
  # dynamics, localGravity and drive points ride the first part listing it in
  # the tick (the primary object's ride part 0); a later part listing the same
  # object carries channel values only, and receivers ignore its other fields.
  part @3 :UInt16;                 # 0-based index of this part within the tick
  partCount @4 :UInt16;            # parts carrying this tick; 0 or 1 = single datagram
}

struct MotionObject {
  name @0 :Text;                   # matches ObjectDescriptor.name

  # Core pose — the OGS-TS minimal set.
  position @1 :Vector3;            # world position of the object's referencePoint
                                   # (object-local frame origin by default), meters,
                                   # left-handed, Z-forward, Y-up
  orientation @2 :Quaternion;      # unit quaternion: OGS-TS world -> object axes

  # Dynamics — optional; exactly one representation, whichever the sender
  # measures natively. Receivers convert between them using orientation.
  # Cap'n Proto struct fields are inline (not nullable), so absence is the
  # union's default variant.
  union {
    noDynamics @3 :Void;           # default: not provided — derive from pose
    kinematics @4 :Kinematics;     # velocity + acceleration, world space
    bodyDynamics @5 :BodyDynamics; # specific force + angular rates, body frame
  }

  drivePoints @6 :List(DrivePoint);   # only points with state this tick
  channels @7 :List(ChannelValue);    # only channels that changed / are streamed
  texts @10 :List(TextValue);         # text channel values, same rules as channels

  # Gravity at this object, when it differs from the environment's (planet
  # surfaces, rotating habitats, multi-body scenes). A named union, since the
  # struct's unnamed union carries the dynamics. Applies to this frame only:
  # a sender using it carries it in every motion frame (CONVENTIONS C-12).
  localGravity :union {
    noLocalGravity @8 :Void;       # default: the environment gravity applies
    vector @9 :Vector3;            # m/s^2, world frame, pointing the way gravity pulls
  }
}

struct Kinematics {
  velocity @0 :Vector3;            # m/s, world space
  acceleration @1 :Vector3;        # m/s^2, world space, coordinate acceleration
                                   # (gravity excluded; CONVENTIONS C-12)
}

struct BodyDynamics {
  # Native representation of accelerometer-class sources (e.g. community
  # memory offsets) and the direct input of motion-cueing washout filters.
  # Body axes: OGS-TS world frame rotated by orientation — x +right (sway),
  # y +up (heave), z +forward (surge).
  specificForce @0 :Vector3;      # m/s^2, accelerometer-style: q^-1 * (a - g), the
                                  # reaction to the object's effective gravity
                                  # included (CONVENTIONS C-12)
  angularVelocity @1 :Vector3;    # rad/s: x +nose-up pitch, y +nose-right yaw, z +roll right-down
}

struct DrivePoint {
  id @0 :UInt16;                   # matches DrivePointDescriptor.id
  union {
    # Dynamic state per drive-point type. Variants mirror the descriptor union.
    wheel @1 :WheelState;
    propeller @2 :PropellerState;
    jet @3 :JetState;
    sail @4 :SailState;
    leg @5 :LegState;
    wing @6 :WingState;
    generic @7 :GenericState;
  }
}

struct WheelState {
  rpm @0 :Float32;                # rpm (declared exception, C-3)
  slip @1 :Float32;                # slip ratio, 0 = rolling
  compression @2 :Float32;         # current suspension compression, meters
  contact @3 :ContactMedium;
  union {
    # Per-wheel extras arrive whole in practice (AC/iRacing-style physics
    # pages) or not at all — all-or-neither also fits Cap'n Proto's
    # single-unnamed-union rule. Inside extended, zeros are real values.
    core @4 :Void;                 # default: core fields only
    extended @5 :WheelExtended;    # steer angle, load force, tyre data
  }

  # Drive torque and brake pressure are measured independently and many
  # sources have neither (aircraft gear, arcade physics), so each is its
  # own named optionality union: absence is the Void default, never 0.
  torque :union {
    noTorque @6 :Void;             # default: not measured
    value @7 :Float32;             # Nm, drive torque at this wheel
  }
  brakePressure :union {
    noBrakePressure @8 :Void;      # default: not measured
    value @9 :Float32;             # Pa
  }
}

struct WheelExtended {
  steerAngle @0 :Float32;          # rad; positive = right, same sense as +yaw (C-4)
  loadForce @1 :Float32;           # N along suspension axis, measured (incl. damping)
  damperVelocity @2 :Float32;      # m/s compression rate (iRacing shockVel, Dirt 4
                                   # suspension_velocity — ≥2-game evidence)
  tyrePressure @3 :Float32;        # Pa
  tyreTemp @4 :Float32;            # °C (C-3), carcass/average (zone temps → channels)
  tyreWear @5 :Float32;            # 0..1 fraction remaining (1 = new)
}

struct PropellerState {
  rpm @0 :Float32;                # rpm (declared exception, C-3)
  union {
    core @1 :Void;                  # default: rpm only
    extended @2 :PropellerExtended; # pitch/thrust when measured
  }
}

struct PropellerExtended {
  pitch @0 :Float32;               # radians (variable-pitch props)
  thrust @1 :Float32;              # N, measured or well-estimated
}

struct JetState {
  throttle @0 :Float32;            # 0..1
  union {
    noThrust @1 :Void;             # default: not measured
    thrust @2 :Float32;            # N
  }
}

struct SailState {
  sheet @0 :Float32;               # 0..1
  angle @1 :Float32;               # radians relative to object
}

struct LegState {
  contact @0 :Bool;
  phase @1 :Float32;               # gait phase 0..1
  union {
    noForce @2 :Void;              # default: not available
    force @3 :Vector3;             # world space, N (mirrors GenericState)
  }
}

struct GenericState {
  # Escape hatch for drive-point types without a dedicated variant. Multi-instance
  # by design (four hover fans = four generic drive points): physical quantities
  # are per-point fields; game-flavored quantities ride object channels.
  engaged @0 :Bool;
  union {
    noForce @1 :Void;              # default: force not available
    force @2 :Vector3;             # world space, N
  }
}

struct WingState {
  flapAngle @0 :Float32;          # rad; positive = tip up (symmetric-pair
                                  # convention — see CONVENTIONS C-4)
  union {
    noForce @1 :Void;              # default: not available
    force @2 :Vector3;             # world space, N (mirrors LegState)
  }
}

struct ChannelValue {
  # Numbers and booleans: data only, so a list of them is 8 bytes per
  # value. Text values ride TextValue lists beside them.
  id @0 :UInt16;                   # matches ChannelDescriptor.id
  union {
    number @1 :Float32;
    boolean @2 :Bool;
  }
}

struct TextValue {
  # The value of a text channel (labels, mode names). Rare in motion
  # frames; session text (track, vehicle names) rides discovery.
  id @0 :UInt16;                   # matches ChannelDescriptor.id
  text @1 :Text;
}

# ---------------------------------------------------------------------------
# Event frame (irregular cadence)
# ---------------------------------------------------------------------------

struct Event {
  id @0 :UInt32;                   # session-monotonic; receivers dedup and
                                   # detect gaps (lossy transport — see
                                   # implementation-udp.md replay guidance)
  name @1 :Text;                   # dot-namespaced, e.g. "weapon.fire";
                                   # naming/ratification like channel names
  intensity @2 :Float32;           # 0..1 normalized (CONVENTIONS C-3)
  duration @3 :Float32;            # s; 0 = momentary impulse, >0 = sustain window
  union {
    noDirection @4 :Void;          # default: omnidirectional
    direction @5 :Vector3;         # body frame of `object`, pointing toward
                                   # the source of the stimulus (CONVENTIONS C-10)
  }
  object @6 :Text;                 # "" = primary object
}

struct EventFrame {
  timestamp @0 :Float64;           # seconds since session anchor (C-8)
  events @1 :List(Event);          # SHOULD re-carry recent events for redundancy
                                   # until ~100 ms old; receivers dedup by id
}
