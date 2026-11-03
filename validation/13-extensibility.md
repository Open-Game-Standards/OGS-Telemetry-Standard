# Test 13: extensibility (custom datapoints at two cadences)

Requirement source: design review — can a game add arbitrary custom
telemetry datapoints, some session-scaled and some high-frequency, without
schema changes? This is the standard's core extensibility promise, checked
against both cadences.

## Requirement

1. **High-frequency custom datapoints** — values changing per tick or
   several times per second (tyre temperatures, boost pressure, DRS state,
   weapon heat, zone loads).
2. **Session-based custom datapoints** — values that rarely or never change
   within a session (setup choices, session type, stage/server name,
   weather preset, mode labels), including for receivers that join
   mid-session.

## Mapping

| Requirement | OGS-TS mechanism |
|---|---|
| declare any datapoint | `ChannelDescriptor` in discovery: sender-assigned id, stable name, unit, optional range, description — no schema change, ever |
| high-frequency value | `ChannelValue` in `MotionObject.channels` per tick; ids cost 2 bytes; absence = unchanged (receivers hold latest known per id) |
| session value | current value in `ObjectDescriptor.values`; a change re-sends discovery, so **late joiners get complete session state from discovery alone** |
| session-global (no owning object) | attaches to the primary object's channel set |
| labels / mode names | text-valued channel, naturally in session `texts` |
| future datapoint kinds | channels are data, not schema — v1.x additions never gate them |

Evidence anchors from the validated set: streamed — F1
`revLightsPercent`/`drs` (test 10), `ctrl.*` families (tests 02–06);
session — WRC stage names, GTA5 weather, mode labels (tests 10–11),
`session.*`-style status (ED Status.json, test 07).

## Verdict

**Supported.** Fast datapoints stream as motion channels; session
datapoints carry current values in discovery (`values`), which makes
late-joining receivers whole from a single discovery frame — closing the
delta-stream gap where a value that stopped changing would otherwise never
be seen. A channel lives in one layer; its cadence decides which.

Validation set: **13 tests, 6 source classes, zero open gaps.**
