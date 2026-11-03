# AGENTS.md — OGS-Telemetry-Standard

Working conventions for agents editing this repo. The short version:
**product docs describe what is; process (what was considered, what changed,
what got fixed) lives exclusively in the knowledge base.**

## Documentation policy: current state only

- All repo docs (`README.md`, `DESIGN.md`, `implementation-*.md`,
  `validation/`, `CHANNELS.md`, schema comments) describe the current state
  of the standard only.
- Never add process history to docs: no gap/resolution narratives, no
  "previously/now/added in", no adoption notes, no supersession references.
- If a doc change would explain *why* something changed, state what the
  standard *is* in the doc and file the why in the sibling knowledge base
  (`../Open-Game-Standards-Knowledge`) as a span-cited claim — see
  `knowledge/README.md` for the bridge and its `schema/AGENTS.md` for the KB
  contract.
- Commit messages describe the change, not the deliberation.

## Schema rules
- `conformance/` is the byte-level conformance corpus: golden datagrams +
  manifest, generated deterministically by
  [ogs-ts-dotnet](https://github.com/Open-Game-Standards/ogs-ts-dotnet)
  `src/ConformanceGen`. Regenerate there; a non-empty diff without a
  deliberate wire change is a bug. Every vector is in canonical OGS
  encoding (`implementation-capnproto.md` § Encoding rules);
  `conformance/validate.py` checks that independently of the generator.

- `ogs_telemetry.capnp` is the single source of truth. A JSON
  mirror, if ever needed for tooling, must be *generated* from the capnp —
  never hand-maintained.
- **Optionality rule**: optional measured quantities use a union with a
  `Void` default variant ("not provided"), declared first so it is
  discriminant 0 — a zero-initialized union means "not provided". A
  struct's one unnamed union takes the first optional; further ones are
  named unions of the same shape (`MotionObject.localGravity`,
  `WheelState.rpm`). Quantities sources report together bundle
  all-or-neither into a sub-struct (`TyreState`, `Atmosphere`,
  `PropellerExtended`); quantities sources report independently get a
  union each (every `WheelState` measurement). Never introduce sentinel
  values — zeros are real readings; Cap'n Proto struct fields are inline
  and not nullable.
- **Evolution**: adding fields, enum values, or union variants is v1.x-safe
  (unknown-field/unknown-discriminant skipping); renaming or renumbering
  existing fields is a major revision.
- **Channels**: ratified `CHANNELS.md` entries have required units — never
  reuse a ratified name with a different unit. New entries need ≥2-game
  evidence and PR review; entries are never renamed or re-united.
  `ctrl.*` / `wind.*` / `air.*` are convention families, not entries.
- Transport is plain UDP multicast with the 8-byte `OMT1` envelope.

## Validation docs

- Mapping tests classify each game field: direct / annex / convention
  channel / custom channel / GAP (graded deferred-safe vs blocking).
- Resolve or record GAPs before merging — validation docs stay
  current-state; the GAP→fix story goes to the KB.
- Tests map *documented semantics*, not packet captures; real senders must
  verify layouts against official game docs.

## Filing findings

Durable conclusions (design decisions, schema findings, validation results,
history rewrites) are filed in the family KB: ingest sources, append spans,
append claims with validity intervals, run `tools/verify.sh` (must print
VERIFY OK), commit. Never write that history into this repo.
