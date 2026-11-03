# Recordings

A recording captures an OGS-TS stream exactly as receivers saw it, so it
can be replayed into rigs, haptics and tools without running the game
(README scenario 13), shared between tools, and attached to bug reports.
It stores the datagrams themselves, with their arrival time and source,
so a replay is byte-identical to the original stream and several senders
stay apart (implementation-udp.md § Senders and sessions).

File extension: `.ogsrec`. All integers are little-endian.

## File header (16 bytes)

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | Magic `OGSR` |
| 4 | 2 | Format version: `1` |
| 6 | 2 | Reserved: write 0, ignore on read |
| 8 | 8 | Capture start, Unix time in microseconds (int64) |

## Records

Records follow the header back to back, in arrival order, until the end
of the file.

| Offset | Size | Field |
|---|---|---|
| 0 | 8 | Arrival time, microseconds since the capture start (int64, non-decreasing) |
| 8 | 4 | Datagram length in bytes (uint32) |
| 12 | 2 | Source port (uint16) |
| 14 | 1 | Source address family: `4` (IPv4) or `6` (IPv6) |
| 15 | 1 | Reserved: write 0, ignore on read |
| 16 | 4 or 16 | Source address (network byte order, as on the wire) |
| … | length | The datagram, envelope included |

- A recorder writes every OMT1 datagram it receives, foreign datagrams
  excluded. It never rewrites a datagram.
- A reader that meets an unknown format version stops; a truncated final
  record (a recorder cut off mid-write) is dropped, not an error.

## Replay

- **Timing.** Send each datagram when its arrival time (relative to the
  first record) is reached, at the original pace. A replayer may offer a
  speed factor, and should say so: the frames' own timestamps are not
  rewritten.
- **One socket per recorded source.** Every distinct source address and
  port in the recording is replayed from its own socket, so receivers
  still see the recorded senders as separate sessions.
- **Endpoint.** Replay to the default group and port unless the user
  chooses another. A replay is a live stream to receivers, so it is
  subject to the same safety rules (implementation-udp.md § Trust and
  safety); a replay tool should make it obvious that it is sending.
- **Replaying into one tool.** A tool may instead play a recording into
  its own receiving path without sending anything (a monitor showing a
  recording, a rig controller replaying a lap into its rig). Nothing
  reaches other receivers, so this is the safer default for such tools;
  the timing rule still applies.

The conformance corpus includes a sample recording
([conformance/recordings/sample.ogsrec](conformance/recordings/)) of
corpus vectors from two sources.
