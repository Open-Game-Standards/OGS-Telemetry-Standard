# Negative conformance corpus

Datagrams a receiver must survive: malformed, foreign, or valid in a
shape canonical senders never produce. The positive corpus
([../](../)) proves a receiver reads what senders send; this one proves
it does not fail, misread or follow what it must not.

- `manifest.json` — per vector: `expect` (what a receiver does, defined
  below), a description, and `after` when the vector applies on top of
  a positive vector's discovery
- `vectors/<id>.hex` — the raw datagram, envelope included, hex wrapped
  at 64 characters

## Expectations

| `expect` | A receiver… |
|---|---|
| `skip` | skips it silently before decoding (not a decode error) and keeps receiving |
| `decode-error` | counts a decode error, dispatches no frame, and keeps receiving |
| `accept` | decodes and applies it; unknown union variants read as the description says (implementation-capnproto.md § Receivers MUST) |
| `ignore-page` | decodes it but does not merge the page (implementation-udp.md § Paged discovery) |
| `drop-value` | decodes it but does not apply the value |
| `fault` | decodes it; a receiver driving hardware does not follow it (implementation-udp.md § Trust and safety) |

## Vectors

| id | expect | covers |
|---|---|---|
| `runt-datagram` | skip | shorter than the 8-byte envelope |
| `foreign-magic` | skip | another protocol on the shared group |
| `unknown-frame-type` | skip | frame type 0x07 |
| `truncated-message` | decode-error | the segment ends past the datagram |
| `segment-size-overflow` | decode-error | the segment table claims more words than the datagram holds |
| `multi-segment` | accept | `motion-pose` content in several segments |
| `non-canonical-null-text` | accept | null Text pointers read as `""` |
| `unknown-dynamics-variant` | accept | an undeclared dynamics discriminant reads as `noDynamics` |
| `unknown-drivepoint-variant` | accept | an undeclared drive-point kind: its state ignored, the others kept |
| `unknown-wheel-measurement-variant` | accept | an undeclared optionality variant reads as "not measured" |
| `page-index-out-of-range` | ignore-page | `page` not below `pageCount` |
| `type-mismatch-value` | drop-value | a number for a channel declared boolean |
| `undeclared-channel` | drop-value | a channel id nothing declares |
| `nonfinite-pose` | fault | NaN and infinite position |

## Generation and checking

`python conformance/negative/generate.py` derives every vector from
the positive corpus by mutating fields located through the schema
(pycapnp), so the bytes are a function of the positive corpus alone;
regenerate after the positive corpus changes. `python
conformance/negative/check.py` verifies each vector independently of
the generator.
