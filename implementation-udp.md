# UDP Implementation

The OGS-TS transport is **plain UDP multicast**. At 60–120 Hz with sub-500-byte packets on a LAN or localhost, transport latency is a few hundred microseconds at most — negligible next to the game physics tick, motion cueing filters, and actuator response. A high-performance messaging layer would add a media driver process and client library to every integration for performance this use case cannot use. Plain UDP is trivial to ship in engine plugins and supports multicast, so multiple clients (dashboards, motion rigs, haptics, loggers) receive the same stream without extra ports or proxying.

Cap'n Proto handles serialization (see [implementation-capnproto.md](implementation-capnproto.md)).

## Wire format

Each UDP datagram is an 8-byte envelope followed by one Cap'n Proto message:

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | Magic `OMT1` — protocol id + wire-format version |
| 4 | 1 | Frame type: `0x00` = `DiscoveryFrame`, `0x01` = `MotionFrame`, `0x02` = `EventFrame` |
| 5 | 3 | Reserved — send 0, ignore on receive |
| 8 | … | Cap'n Proto message (already word-aligned — readable in place) |

Receivers check the magic and silently skip foreign packets (the multicast group may be shared). Datagrams stay within the datagram budget below.

## Datagram budget

Every datagram, envelope included, MUST be at most **1,400 bytes**, so it travels as one Ethernet frame (a lost IP fragment loses the whole datagram) and no single send costs the sender a long serialization. Most senders never come close: a pose-only motion frame is ~68 bytes and a typical discovery a few hundred. Senders with large descriptor sets (full simulator catalogues, multi-car grids) stay within the budget with three mechanisms.

### Paged discovery

Every sender maintains `generation`: it increments by one (wrapping) whenever any id, name, unit, range, value type, drive point or object identity changes, paged or not. A change to session `values` or `texts` alone keeps the generation.

A descriptor set that does not fit one datagram is split into **pages**: `DiscoveryFrame`s sharing one `generation`, each carrying `page` (0-based) and `pageCount`. `pageCount` 0 or 1 means the frame is the complete set.

- Every page repeats `schemaVersion`, `gameName`, `sessionStartUnixUs`, `instanceLabel`, `host`, `motionRateHz` and `environment` unchanged.
- An object's identity (type, location, typeLabel, primary, reference and named points, drive points) rides the lowest-numbered page that lists the object. Later pages listing it carry only further `channels`, `values` and `texts`.
- Each channel id is declared on exactly one page of a generation.
- Page 0 carries the primary object's identity and drive points, and the channels a motion consumer needs first (ratified annex channels, `session.paused`). Session `values` that change during a session SHOULD ride their own page.
- A change to session `values` or `texts` re-sends only the page carrying them.

A page whose `page` is not below its `pageCount` is malformed: receivers ignore it. Receivers merge the pages of a generation by object name and channel id; each page is usable as soon as it arrives, with no need to wait for the rest. A frame with a different `generation` (or a new `sessionStartUnixUs`) starts a new descriptor set. Receivers keep the previous generation's tables while motion frames still carry its `generation`, so a vehicle swap never misreads ids. An unpaged frame (`pageCount` 0 or 1) replaces the descriptor set whole.

### Motion parts

A tick whose motion frame does not fit one datagram is sent as **parts**: `MotionFrame`s sharing the tick's `timestamp`, each carrying `part` (0-based) and `partCount`, sent back-to-back.

- Each object's pose, dynamics, `localGravity` and drive points ride the first part that lists the object in the tick; the primary object rides part 0. A later part listing the same object carries channel and text values only, and receivers ignore its other fields.
- Receivers apply each part on arrival, never waiting for the rest of the tick. Every part counts as a heartbeat.

### Bounded refresh

Absence means unchanged (DESIGN.md § Two channel cadences), so a sender may carry only the channels that changed. Such a sender re-sends every streamed value at least once per discovery interval (2 s), spreading this refresh across ticks so no tick exceeds the budget. Changed values take precedence over refresh values; when changed values alone exceed the budget, the tick goes out in parts.

### Generations in motion frames

`MotionFrame.generation` names the descriptor set its channel and drive-point ids refer to. A receiver that does not yet hold that generation's descriptor for an id holds back the value (it arrives again with the next change or refresh); pose and dynamics never depend on descriptors and are always applied.

## Sender size envelope

Every receiver on the network pays for what a sender publishes: multicast reaches all of them, and on Wi-Fi the access point re-sends it to every wireless device. A sender SHOULD stay within this envelope:

| | Envelope | Typical capacity |
|---|---|---|
| Motion | one datagram (≤ 1,400 bytes) per tick at 60 Hz, or ~85 KB/s at other rates | pose, dynamics, drive points and ~150 changing channel values per tick |
| Discovery | ~30 KB per generation, every page re-sent within 2 s (~15 datagrams/s) | ~250–300 channel descriptors with descriptions |

The envelope comes to ~105 KB/s. On an access point that sends multicast at a 6 Mbit/s basic rate, the lowest common setting on 5 and 6 GHz, that is ~15 % of the channel's airtime; at a 24 Mbit/s basic rate, ~5 %; with multicast-to-unicast conversion, ~1.5 % per device that joined the group. A pose-only or typical game sender uses a fraction of it.

Before cutting channels, a large sender uses the savings the format already allows:

- **Changed values only.** Absence means unchanged, so a value rides a motion frame only when it changes, plus the bounded refresh (§ Bounded refresh) that heals loss and serves late joiners.
- **Session values for what rarely changes.** Switches, lights, radio frequencies, autopilot settings and identity strings go in `ObjectDescriptor.values` and `texts` (DESIGN.md § Two channel cadences). They cost nothing per tick and travel in discovery only when they change.
- **Descriptions where they carry meaning.** A description is display text that nothing binds on. Keep it where name and unit do not explain the value (enums, bitfields, values passed on as the game sends them, unknown units) and leave it empty where it would restate the name.
- **Nothing for what is not there.** Empty lists stay null, unset optionality unions stay at their `Void` default, and a paused sender sends `noDynamics` (CONVENTIONS C-11); canonical encoding (implementation-capnproto.md § Encoding rules) then spends no bytes on them.

A game or simulator whose consumers need more than this (thousands of values, every cockpit switch, values written back into the game) offers a dedicated API for that depth, as X-Plane, MSFS and DCS do, **and still publishes over OGS-TS** the core schema, the channels ratified in CHANNELS.md, and a curated set of further channels within the envelope. OGS-TS is the stream every device can use without game-specific code; the dedicated API serves the consumers written for that game. The sender references (reference-xplane12.md, reference-msfs2024.md) are curated this way.

## Event frames

`EventFrame`s are sent on demand (irregular cadence, often bursty) and
carry discrete stimuli — impacts, gunfire, footsteps — for haptic and
cueing consumers (CONVENTIONS C-10). Because the transport is lossy and
an event must not be silently missed, senders SHOULD re-carry recent
events in subsequent `EventFrame`s for ~100 ms (or until the next frame
if quieter); receivers MUST dedup by the session-monotonic `id`. Events
are self-contained (intensity, duration, optional body-frame direction),
so a late-joined receiver misses only events from before it joined —
by design, as with motion.

Event frames are auxiliary: they do not count as the heartbeat and do
not participate in liveness detection; motion frames remain the sole
liveness signal.

## Default endpoint

| Setting | Value | Notes |
|---|---|---|
| Multicast group | `239.255.17.17` | Organization-local scope; avoids link-local reserved ranges |
| IPv6 multicast group | `ff12::4f47:5453` | Transient, link-local scope (`4f47:5453` is "OGTS") |
| Port | `40123` | Both address families |
| TTL / hop limit | 1 | Local network only |
| Unicast alternative | `127.0.0.1:40123` (`[::1]:40123`) | Single-client setups and testing |

All values are defaults — every implementation should make endpoint and mode configurable.

IPv4 is the default. A sender uses **one** address family for a session: IPv4, or IPv6 on a network without IPv4. Never both at once, since a receiver joined to both groups would see the two copies as two senders (§ Senders and sessions). Receivers SHOULD join both groups so that IPv6-only senders are found. The IPv6 group is link-local: join and send on the interface facing the LAN (its interface index), as for any link-local multicast.

## Network interfaces

Receiving telemetry from other machines on the network is a core use of OGS-TS, and it depends on the sender's datagrams leaving on a real network interface. Multicast traffic is routed by group address, not port, and an operating system's choice of interface for a group can change while a stream is running: on Windows, once anything on a host has sent to a group over loopback, the system's default for that group on that host is loopback. Default-route senders on that host then stop reaching the network, and receivers joined on the network interface stop hearing them, with no error on either end, even after the loopback sender has closed.

- **Senders MUST NOT send to the default groups over loopback.** Traffic meant to stay on one machine, such as a demo or a test, uses a different group or the unicast alternative.
- **Senders SHOULD name their interface** (`IP_MULTICAST_IF`): the one the user configured, otherwise the default route's, rather than leaving the choice to the system.
- **Receivers SHOULD join by name on the same interface, and also on loopback** where the host allows it, so they keep hearing senders on the same machine whichever way those senders' traffic is routed. A failure to join on loopback is not an error: some systems ship with multicast disabled there.
- **For the IPv6 group,** which has no route to look up, the interface is the IPv4 default route's if it has IPv6, otherwise the first interface with an IPv6 gateway, otherwise the first with IPv6 that isn't loopback or a tunnel.
- On a host with several interfaces the default route may not face the LAN, so implementations make the interface configurable.

## Wireless networks

OGS-TS works over Wi-Fi, so standalone VR headsets, handhelds and battery-powered devices can send or receive it. The expected network is Wi-Fi 5 (802.11ac) or newer on 5 or 6 GHz. Wi-Fi handles multicast less well than a wired network, and these points apply:

- **Wired where possible.** Access points typically send multicast at the lowest basic data rate and without retransmission, so loss and airtime cost are higher than for unicast. Keep at least the receiver wired when it can be.
- **Access point settings.** Client isolation (common on guest networks) blocks traffic between devices entirely. IGMP snooping without a querier can stop multicast reaching receivers after a few minutes. Some access points offer multicast-to-unicast conversion (also sold as multicast enhancement), which improves reliability and spares devices that have not joined the group. Where the access point allows it, a minimum basic rate of 12–24 Mbit/s cuts the airtime multicast costs every other device. 2.4 GHz with 802.11b rates enabled sends multicast at 1 Mbit/s, where even a typical sender takes over a quarter of the airtime.
- **Android-based devices** (including standalone VR headsets) drop incoming multicast unless the app holds a `WifiManager.MulticastLock`, and need the `CHANGE_WIFI_MULTICAST_STATE` permission to take it. Senders need the `INTERNET` permission.
- **Power saving** on battery devices can delay multicast delivery; receivers that need consistent timing should disable Wi-Fi power saving while active. While any device on an access point is in power save, the access point holds all multicast until its next DTIM beacon, typically ~100 ms and up to ~300 ms, which delays every wireless receiver on it; unicast is not held.

Event replay (CONVENTIONS C-10) and receiver interpolation already absorb occasional loss; these points keep loss occasional.

## Send cadence

| Frame | When to send |
|---|---|
| `DiscoveryFrame` | session start, on any declared change (vehicle swap, channel set change, medium change), and **re-sent every 2 seconds** — all pages of the current generation |
| `MotionFrame` | every telemetry tick, ~60 Hz, at the rate discovery declares in `motionRateHz` — **including while the game is paused** (CONVENTIONS C-11) |

The 2-second discovery re-send bounds late-joiner wait time at ~1.6 kbit/s of extra traffic for a typical single-page discovery — negligible, and it heals any lost discovery packet. Motion frames are fire-and-forget: receivers hold the last known pose and interpolate across occasional loss.

Paged discovery is paced so that no tick pays for the whole set:

- **Periodic re-send:** spread evenly across the 2-second interval — one page per motion tick, or the few per tick a very large set needs to complete within the interval.
- **Session start and generation change:** all pages back-to-back, since motion frames naming the new generation are already flowing.
- **Session value change:** the page carrying the changed values, at once.

## Sender (game side)

```cpp
#include "ogs_telemetry.capnp.h"
#include <capnp/message.h>
#include <capnp/serialize.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <cstring>

// This host's address on its default route, or INADDR_ANY (the system chooses)
// when it has none. Connecting a UDP socket only looks up the route: nothing is
// sent. 192.0.2.1 is reserved for documentation (RFC 5737).
inline in_addr defaultRouteAddress() {
    in_addr result{};
    result.s_addr = htonl(INADDR_ANY);
    int probe = socket(AF_INET, SOCK_DGRAM, 0);
    sockaddr_in remote{};
    remote.sin_family = AF_INET;
    remote.sin_port = htons(9);
    remote.sin_addr.s_addr = inet_addr("192.0.2.1");
    sockaddr_in local{};
    socklen_t length = sizeof(local);
    if (connect(probe, reinterpret_cast<sockaddr*>(&remote), sizeof(remote)) == 0 &&
        getsockname(probe, reinterpret_cast<sockaddr*>(&local), &length) == 0 &&
        (ntohl(local.sin_addr.s_addr) >> 24) != 127) {
        result = local.sin_addr;
    }
    close(probe);
    return result;
}

class UdpTelemetrySender {
public:
    UdpTelemetrySender(const char* group = "239.255.17.17", uint16_t port = 40123) {
        fd_ = socket(AF_INET, SOCK_DGRAM, 0);

        // Local network only
        unsigned char ttl = 1;
        setsockopt(fd_, IPPROTO_IP, IP_MULTICAST_TTL, &ttl, sizeof(ttl));

        // Enable loopback so dashboards on the same machine see the stream
        unsigned char loop = 1;
        setsockopt(fd_, IPPROTO_IP, IP_MULTICAST_LOOP, &loop, sizeof(loop));

        // Leave on a real interface (§ Network interfaces)
        in_addr nic = defaultRouteAddress();
        setsockopt(fd_, IPPROTO_IP, IP_MULTICAST_IF, &nic, sizeof(nic));

        addr_.sin_family = AF_INET;
        addr_.sin_port = htons(port);
        addr_.sin_addr.s_addr = inet_addr(group);
    }

    void sendDiscovery() {
        // buildDiscovery() as shown in implementation-capnproto.md
        send(0x00, buildDiscovery());
    }

    void sendMotion(double timestampSeconds) {
        // buildMotion() as shown in implementation-capnproto.md
        send(0x01, buildMotion(timestampSeconds));
    }

private:
    void send(uint8_t frameType, kj::Array<capnp::word> words) {
        uint8_t buf[1400];
        std::memcpy(buf, "OMT1", 4);          // magic + wire version
        buf[4] = frameType;
        buf[5] = buf[6] = buf[7] = 0;         // reserved
        size_t payload = words.size() * sizeof(capnp::word);
        std::memcpy(buf + 8, words.begin(), payload);
        sendto(fd_, buf, 8 + payload, 0,
               reinterpret_cast<sockaddr*>(&addr_), sizeof(addr_));
    }

    int fd_;
    sockaddr_in addr_{};
};

int main() {
    UdpTelemetrySender sender;
    sender.sendDiscovery();

    double t = 0.0;
    int tick = 0;
    while (true) {
        sender.sendMotion(t);
        t += 1.0 / 60.0;
        if (++tick % 120 == 0)                // discovery re-send every 2 s
            sender.sendDiscovery();
        usleep(16667);                        // ~60 Hz
    }
}
```

## Receiver (motion software side)

```cpp
#include "ogs_telemetry.capnp.h"
#include <capnp/message.h>
#include <capnp/serialize.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unordered_map>

class UdpTelemetryReceiver {
public:
    UdpTelemetryReceiver(const char* group = "239.255.17.17",
                         uint16_t port = 40123) {
        fd_ = socket(AF_INET, SOCK_DGRAM, 0);

        // Multiple subscribers may live on the same host
        int reuse = 1;
        setsockopt(fd_, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
#ifdef SO_REUSEPORT
        setsockopt(fd_, SOL_SOCKET, SO_REUSEPORT, &reuse, sizeof(reuse));
#endif

        sockaddr_in local{};
        local.sin_family = AF_INET;
        local.sin_port = htons(port);
        local.sin_addr.s_addr = htonl(INADDR_ANY);
        bind(fd_, reinterpret_cast<sockaddr*>(&local), sizeof(local));

        ip_mreq mreq{};
        mreq.imr_multiaddr.s_addr = inet_addr(group);
        // defaultRouteAddress() as in the sender (§ Network interfaces)
        mreq.imr_interface = defaultRouteAddress();
        setsockopt(fd_, IPPROTO_IP, IP_ADD_MEMBERSHIP, &mreq, sizeof(mreq));

        // Also hear senders on this machine if their traffic moves to loopback
        mreq.imr_interface.s_addr = htonl(INADDR_LOOPBACK);
        setsockopt(fd_, IPPROTO_IP, IP_ADD_MEMBERSHIP, &mreq, sizeof(mreq));
    }

    // Call from your main loop; returns true when a frame was processed.
    bool poll() {
        uint8_t buf[1400];
        ssize_t n = recv(fd_, buf, sizeof(buf), MSG_DONTWAIT);
        if (n < 9) return false;                          // nothing / runt
        if (std::memcmp(buf, "OMT1", 4) != 0) return false; // foreign packet

        // Payload starts at offset 8 — already word-aligned, readable in place
        size_t wordCount = (n - 8 + 7) / 8;
        kj::ArrayPtr<const capnp::word> words(
            reinterpret_cast<const capnp::word*>(buf + 8), wordCount);
        ::capnp::FlatArrayMessageReader message(words);

        switch (buf[4]) {
            case 0x00: return onDiscovery(message.getRoot<DiscoveryFrame>());
            case 0x01: return onMotion(message.getRoot<MotionFrame>());
        }
        return false;
    }

private:
    bool onDiscovery(DiscoveryFrame::Reader d) {
        // Build the id -> descriptor tables: channel names/units/ranges,
        // drive-point geometry, environment. Idempotent — a re-sent page
        // simply overwrites its own entries. If the primary object's
        // ObjectType changed (player entered a vehicle/aircraft), switch the
        // cueing preset — discovery re-sends are the within-game
        // auto-switching signal.
        bool paged = d.getPageCount() > 1;
        auto& tables = generations_[d.getGeneration()];
        if (!paged) tables.clear();               // unpaged: the complete set
        for (ObjectDescriptor::Reader obj : d.getObjects())
            for (ChannelDescriptor::Reader ch : obj.getChannels())
                tables[ch.getId()] = ch.getName().cStr();   // pages merge
        // Keep only this generation and the one motion frames may still name.
        pruneGenerationsOlderThan(d.getGeneration());
        return true;
    }

    bool onMotion(MotionFrame::Reader f) {
        auto tables = generations_.find(f.getGeneration());
        for (MotionObject::Reader obj : f.getObjects()) {
            // Pose and dynamics never depend on descriptors — always apply
            // (from the first part listing the object in this tick).
            // obj.getPosition(), obj.getOrientation() …
            // Derive velocity/acceleration from pose deltas when absent.
            // Channel values: apply those whose id is known in
            // tables->second; hold back the rest until their page arrives.
            // If a descriptor declared a range, drop out-of-range values.
        }
        return true;
    }

    void pruneGenerationsOlderThan(uint32_t generation);   // keeps generation and its predecessor

    int fd_;
    // generation -> (channel id -> name); a real receiver keys per sender
    // (source address and port, § Senders and sessions) and per object too
    std::unordered_map<uint32_t, std::unordered_map<uint16_t, std::string>> generations_;
};
```

## Senders and sessions

Several senders can share one multicast group: two games on one PC, a sim and its instructor station, a venue with several rigs. Discovery carries the session identity; motion and event frames do not, so receivers tell senders apart by where datagrams come from.

Senders:

- A sender sends all its frames (discovery, motion, events) from **one UDP socket** for its lifetime, so they share one source address and port.
- `instanceLabel` (user-set, e.g. "Rig 2") and `host` (the sender's host name) identify the instance for pickers. They stay fixed for a session (changing them starts a new session with a new `sessionStartUnixUs`). Both are optional; when a sender can run as more than one instance on a network, it SHOULD let the user set `instanceLabel`.

Receivers:

- A **sender** is a source address and port. Each sender has its own descriptor tables, generations, liveness and event dedup; ids never resolve across senders.
- A **session** is a sender plus `sessionStartUnixUs`. A discovery frame with a new `sessionStartUnixUs` from the same sender starts a new session; a sender that restarts on a new socket appears as a new sender.
- Motion and event frames belong to the session of their source. A frame from a sender with no discovery yet is held back like any unresolved id (§ Generations in motion frames); its pose is still usable once the receiver binds to that sender.
- A receiver that drives one output (a motion rig, a haptic device) binds to **one** session at a time and never blends frames from two senders. Monitors, loggers and recorders may follow every session.
- Choosing a session:
  1. **User choice.** A picker lists sessions by `gameName`, `instanceLabel` and `host` (or the source address).
  2. **Pinned.** A remembered choice is stored as (`gameName`, `instanceLabel`, `host`), never as address and port, which change between runs, and is re-acquired when a matching sender appears. When two live sessions match one pin (two unlabelled instances of a game on one host), the pin is ambiguous: the receiver says so and asks, rather than picking one.
  3. **Automatic**, with nothing pinned: prefer a sender on the receiver's own host, then the session that started most recently. When more than one session is available, the receiver says so rather than choosing silently.

## Trust and safety

OGS-TS has no authentication. Any device on the network can send datagrams that look like any sender's, including frames crafted to drive hardware. The threat to plan for is not data theft (the stream is read-only telemetry) but a spoofed or faulty stream moving physical equipment: a motion platform, a force-feedback wheel, a fan or a shaker.

Receivers that drive hardware:

- MUST bind to one session (§ Senders and sessions) and ignore frames from every other source while bound.
- MUST limit their output to the device's safe range, rate and acceleration, whatever the stream says. A frame is never a command to exceed the device's limits.
- SHOULD treat physically implausible input as a fault rather than follow it: a pose jump far beyond the declared motion rate allows, a specific force far beyond any vehicle's, non-finite values. On a fault, hold or ease to rest as for a stale session (§ Liveness and session end).
- SHOULD let the user arm the device before it follows a new session, rather than starting on the first frame from an unknown source.

Senders cannot prevent spoofing; they keep to TTL 1 (or the user's configured scope) so the stream stays on the local network. Networks that need stronger guarantees (venues, shared spaces) isolate telemetry on their own VLAN or Wi-Fi network.

## Liveness and session end

The sender gives no explicit goodbye, so receivers detect liveness from
the stream itself, per sender (§ Senders and sessions):

- A paused game keeps streaming, with `session.paused` set (CONVENTIONS
  C-11), so a pause never trips the rules below: silence means the
  sender stopped, not that the player paused.
- Motion frames (any part) are the heartbeat. If no motion frame arrives for ~5×
  the tick interval (from the declared `motionRateHz`; 1 s when it is
  not declared), mark the
  session stale: hold the last pose, stop driving actuators toward new
  targets, and surface the state in UI.
- Discovery re-sends (every 2 s) confirm session identity; a discovery
  frame with a new `sessionStartUnixUs` is a new session — reset state.
- After 10 s with no frame of any type, treat the session as ended and
  release per-sender resources.

## Engine integration (Unity / Unreal / Godot)

The schema and wire format are engine-agnostic; the integration path is a
small plugin embedding the C API below. Language support: **C++** (Unreal,
Godot GDExtension) is first-class for Cap'n Proto; **C#** (Unity, Godot) is
usable via Cap'n Proto C# bindings or by binding the C API in a native
plugin; **GDScript** should call the exposed plugin API rather than
re-implement serialization.

- **Unreal (C++)**: pre-generated Cap'n Proto sources compile into a module;
  wrap the C API in Blueprint-callable functions (e.g. a Blueprint Function
  Library) so visual scripting can set pose, drive points, and channels.
- **Unity (C#)**: bind the C API in a native plugin (or use Cap'n Proto C#
  bindings) and expose a manager component; the UDP sender is a plain
  `UdpClient`.
- **Godot**: a GDExtension (C++) wraps the C API natively; C# builds can use
  the same bindings as Unity.

Every reference plugin ships with:

1. **Pre-generated Cap'n Proto code** — no schema compiler step at game-dev
   time; the plugin is drop-in.
2. **A thin UDP sender** — endpoint, port, and send rate configurable;
   sensible defaults (see [Default endpoint](#default-endpoint)).
3. **Field-level toggles** — games start with the pose core only and enable
   drive points/channels as needed.
4. **Blueprint / visual-scripting friendly wrappers** — setting position or
   a channel is one node call.

Start minimal: a game streaming position/orientation per tick is fully
compliant and useful (~68 bytes/frame) — see "The minimal sender" in
[implementation-capnproto.md](implementation-capnproto.md).

Operational notes:

- **Socket hygiene**: send from one dedicated thread or the engine's network
  tick; never block the render or physics thread on socket calls.
- **Keep ticking while paused**: drive the sender from a real-time clock
  and an update that runs while the game is paused (Unity `LateUpdate`
  with unscaled time, Unreal `bTickEvenWhenPaused`, Godot's
  `SceneTree.ProcessFrame`). A sender ticked on game time goes silent on
  pause, which receivers read as a dead session (CONVENTIONS C-11).
- **Windows Firewall**: the first multicast send may prompt — document it for
  end users.

## Transport abstraction and the high-level C API

For game integration, the transport is abstracted behind a C++ `Transport` base class (`UdpTransport` is the reference implementation), and the whole system — discovery bookkeeping, serialization, envelope framing, derived values — is exposed through a simple C API in `motion_telemetry.h`.

```cpp
class Transport {
public:
    virtual ~Transport() = default;
    virtual void publishDiscovery() = 0;   // builds + sends the DiscoveryFrame
    virtual void send() = 0;               // sends one MotionFrame tick
    virtual void registerCallback(TelemetryCallback callback) = 0;
    virtual void startReceiving() = 0;
    // … per-field setters for pose, drive points, and channels
};
```

The C API hides both layers from game code:

```c
typedef struct MotionTelemetryHandle MotionTelemetryHandle;
typedef void (*TelemetryCallback)(void* userData);

// Lifecycle — transportType: "udp"
MotionTelemetryHandle* motion_telemetry_create_sender(const char* transportType, const char* endpoint, int port);
MotionTelemetryHandle* motion_telemetry_create_receiver(const char* transportType, const char* endpoint, int port);
void motion_telemetry_destroy(MotionTelemetryHandle* handle);

// Declaring the session (feeds the DiscoveryFrame; call before send loop)
void motion_telemetry_set_game_name(MotionTelemetryHandle* handle, const char* name);
int  motion_telemetry_declare_drive_point(MotionTelemetryHandle* handle, const char* objectName, const char* pointName, const char* type);
int  motion_telemetry_declare_channel(MotionTelemetryHandle* handle, const char* objectName, const char* channelName, const char* unit, double min, double max);
void motion_telemetry_publish_discovery(MotionTelemetryHandle* handle);   // also re-sends on change; periodic re-send is automatic

// Per-tick data (feeds the MotionFrame)
void motion_telemetry_set_position(MotionTelemetryHandle* handle, float x, float y, float z);
void motion_telemetry_set_orientation(MotionTelemetryHandle* handle, float fx, float fy, float fz, float ux, float uy, float uz);
void motion_telemetry_set_drive_point_number(MotionTelemetryHandle* handle, const char* pointName, const char* field, float value);
void motion_telemetry_set_channel_number(MotionTelemetryHandle* handle, const char* channelName, float value);
void motion_telemetry_set_channel_boolean(MotionTelemetryHandle* handle, const char* channelName, int value);
void motion_telemetry_send(MotionTelemetryHandle* handle);

// Receiving (callback fires on new motion frames; discovery is handled internally)
void motion_telemetry_register_callback(MotionTelemetryHandle* handle, TelemetryCallback callback, void* userData);
void motion_telemetry_start_receiving(MotionTelemetryHandle* handle);

// Getters, including derived values the library computes from pose deltas
float motion_telemetry_get_velocity_x(MotionTelemetryHandle* handle);   // …_y, …_z
float motion_telemetry_get_acceleration_x(MotionTelemetryHandle* handle); // …_y, …_z
const char* motion_telemetry_get_channel_unit(MotionTelemetryHandle* handle, const char* channelName);
```

A sender loop is then just: declare once → `publish_discovery()` → set fields → `send()` at 60 Hz. Receivers register a callback and read raw and derived values through getters; channel names, units, and ranges arrive via discovery and are queryable by name.
