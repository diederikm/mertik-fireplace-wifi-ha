# Mertik Maxitrol WiFi-Box protocol

Local protocol of the Mertik Maxitrol WiFi modules (B6R-WME, B6R-W2BE-0, B6R-WWN) used by the
MyFire app and its white-label versions (Barbas Gas, Gazco MyFire, Trimline, ...).

Every statement is tagged with where it comes from:

| Tag | Source |
|---|---|
| **M** | Measured on a Bellfires fireplace with a B6R-W2BE-0 module and a Bellfires handset (2026-10) |
| **A** | Static analysis of the Barbas Gas Android app 1.5.51 (`com.iqontrol.interfocos`) and MyFire 1.5.55 (`com.iqontrol.mertik`), which share the same Flutter `mertik` package. Only names, constants and structure are described here; no app code is reproduced |
| **V** | [`omarshahine/valor-fireplace-cli`](https://github.com/omarshahine/valor-fireplace-cli) `PROTOCOL.md` |
| **T** | [`tritter/homebridge-mertik-fireplace`](https://github.com/tritter/homebridge-mertik-fireplace) |
| **H** | Earlier Home Assistant / Homey integrations (this repository, `djerik/mertik-ha`, `erdebee/homey-mertik-wifi`) |

Unverified statements are marked as such.

## Transport

- Plain TCP on port **2000**, no authentication. **M**
- The module effectively serves **one client at a time**. While the app (or another client) holds a
  socket, a second client's socket gets stale or no data. **M**
- The module **pushes status frames unsolicited** on an open socket, and one `recv()` can return several
  frames or a partial frame. **A V M**
- The app keeps one long-lived socket with TCP keep-alive and a 4 s per-request timeout; after three
  timeouts in a row it reconnects. **A**
- Recommendation for integrations: open a short-lived connection per poll or command, read until a
  complete status frame arrives, take the newest one and close. This coexists with the app (verified
  with the Barbas Gas app open on a phone while Home Assistant polled every 10 s). **M**
- Discovery is a UDP broadcast (Lantronix style, `000100f6` to port 30718, replies on 30719) with an
  IP-scan fallback. **H A**

## Framing

```
STX(0x02)  "3030303080"  <command id: 2 chars>  <payload: uppercase hex chars>  ETX(0x03)
```

All bytes between STX and ETX are ASCII characters. **A**

- Requests start with `02 33 30 33 30 33 30 33 30 38 30` (`STX` + `"3030303080"`).
- Status responses start, after STX, with `030300000003` (seen in practice) or `303030300003`. **M H**
- Receivers must split on STX/ETX, drop bytes before an STX, and handle multiple frames per read. **A**

## Commands

The command id is the two ASCII characters after the header. A bare id reads a value; the same id
with a payload writes it. **A**

| Id | Hex after header | Meaning | Source |
|---|---|---|---|
| `03` | `303303` | Read status (see below) | A H M |
| `01` | `303103` | Read device info: capability mask, versions, serials. Not a handshake | A |
| `1A` | `314103` | Ignite | A H M |
| `10` | `313003` | Turn off completely (pilot out) | A H |
| `16` | `3136` + 2 hex + `03` | Set burner output; value `round(pct/100*127 + 128)`, so `80` (low) .. `FF` (high). `00` = standby | A H V |
| `B0` | `423003` | Manual mode | A H |
| `B3` | `4233303103` | Eco mode on. Full payload carries state, interval, step, position, temperature (layout unverified) | A H |
| `B2` | `4232303103` | Thermostat mode on. Payload carries state and set temperature (x10) | A T V |
| `A0` | | Program (week schedule): state, program no., day, on/off time and temperature | A |
| `B1` | | Countdown timer | A |
| `20` | `32303031030a` / `32303030030a` | Aux (second burner) on / off | A H |
| `30` | `3330303103` / `3330303003` | Light on / off; dimmer `33304645` + 2 chars + `03` | A H |
| `40` | | Fan state and level | A |
| `50` | | LED | A |
| `06` | | Clock (year, month, day, weekday, hour, minute, second) | A H |
| `05` | | Device name | A |
| `C0` `C1` `C2` | | Fault history, clear new error, last error | A |
| `0C` | | Reboot module | A |
| `D0`-`D5`, `EE`, `EF`, `FE`, `61`, `DE` | | Wi-Fi credentials, web update, production data, MQTT, labs, Matter | A |

The app's light slider maps 0-100 % to `pct/100*153 + 102`. **A**

## Status frame (command `03`)

Character offsets after stripping STX. Field order and widths from the app, offsets confirmed against
captured frames. **A M**

| Chars | Field | Notes |
|---|---|---|
| 0-11 | prefix | `030300000003` |
| 12-13 | setup state | Feature bits: fan, light, aux, LED0, LED1, cloud, setup complete, timer (bit values unverified) |
| 14-15 | **burner output** | Motor position `00`-`FF`, see below |
| 16-19 | **receiver state** | 16-bit status word, see below |
| 20-21 | light level | |
| 22-23 | fan level | |
| 24-25 | **system mode** | Char 24: `0` manual, `1` thermostat, `2` eco **T M**; `3` seen briefly during a mode change **M** |
| 26-27 | system flags | `01` countdown, `02` thermostat, `04` user profile, `08` child lock, `10` programmer, `20` programs invalid **A** |
| 28-31 | room temperature | x10, 16-bit (`00E1` = 22.5 °C) **A M** |
| 32-35 | set temperature | x10, 16-bit (`00C8` = 20.0 °C) **A M** |
| 36- | name | ASCII, padded with `FF` |
| | icon, Wi-Fi RSSI, handset mode, pilot mV, main mV, handset RSSI | Follow the name **A**; exact offsets unverified |

Parsers must pad the status word to **16 bits**. Padding to 8 bits shifts every bit index by four
whenever the top bit is clear.

### Receiver state bits

Index = position in the 16-character binary string, MSB first.

| Mask | Index | App name | Observed meaning **M** |
|---|---|---|---|
| `0x8000` | 0 | receiverConnected | Set in normal operation; drops briefly while igniting. Frames without it carry unreliable values |
| `0x0200` | 6 | handsetConnected | |
| `0x0100` | 7 | ignitionNotAllowed | Set while **shutting down** |
| `0x0080` | 8 | mainBurnerOn | Despite the name, set whenever the **pilot** burns: on **and** standby. Cleared only when fully off |
| `0x0040` | 9 | fanOn | |
| `0x0020` | 10 | mainBurner2ndTCOn | |
| `0x0010` | 11 | igniting | Set while igniting |
| `0x0008` | 12 | auxOn | Second burner enabled; stays set in standby |
| `0x0004` | 13 | lightOn | |
| `0x0002` | 14 | faulted | |
| `0x0001` | 15 | vModuleConnected | |

### Deriving the fireplace state

What this integration does, matching every measurement below:

1. Receiver link bit was seen before and is now clear: **unknown**, keep the last values.
2. `0x0100` set: **shutting down**.
3. `0x0010` set: **igniting**.
4. `0x0080` clear: **off** (pilot out).
5. Burner output above 64: **on**. Otherwise **standby** (pilot only).

The standby threshold sits between the measured standby output (0-32) and the lowest output of the
handset's flame wave (105), which is below the lowest manual step (`0x80`).

### Burner output

| Situation | Output | Source |
|---|---|---|
| Fully off, shutting down, igniting | `00` | M |
| Standby (pilot only) | `00`, then `20` (32) | M |
| Handset flame wave, low phase (real flames) | `69` (105) | M |
| Lowest manual step / app "Laag vuur" | `80` (128) | M A |
| Highest manual step / app "Hoog vuur" | `FF` (255) | M A |

The output is continuous; the 12 steps the handset and earlier integrations use are
`80 8B 97 A2 AE B9 C5 D0 DC E7 F3 FF`. **V H**

## Measured sequences (B6R-W2BE-0)

Polled every 10 s; `raw` is the burner output, `bits` the receiver state word.

**Shutting down from eco** (handset off button):

| raw | bits | mode | state |
|---|---|---|---|
| 141 | `828A` | 2 | on |
| 141 | `838A` | 0 | shutting down |
| 0 | `838A` | 0 | shutting down |
| 0 | `820A` | 0 | off |

**Relighting from fully off**: the pilot only held on the third attempt.

| raw | bits | state |
|---|---|---|
| 0 | `820A` | off |
| 0 | `821A` | igniting |
| 0 | `021A` | unknown (receiver link lost) |
| 255 | `828A` | on |
| 255 | `028A` | unknown |
| 255 | `008A` | unknown |
| 0 | `820A` | off: pilot did not hold, ignition retried |

**Handset flame wave** (flame button on the Bellfires handset): reported as **manual** mode (char 24
`0`). The output ramps down by about 10 every 10-30 s to 105, stays there for about 10 minutes, then
ramps back up by about 10 per minute. **M**

**App eco** (Barbas Gas "ECO", 20-minute cycle, standard savings): reported as mode `2`. The output
drifts slowly, for example 183 to 141 over 8 minutes. **M**

## Appendix: earlier notes

Kept from the original documentation in this repository.

### Payloads (date and time, light, settings)

#### Date and time

##### Request

```
[ACTION] [DATE TIME: xx xx xx xx xx xx xx xx xx xx xx xx xx xx]
```

##### Response

```
[DATE TIME: xx xx xx xx xx xx xx xx xx xx xx xx xx xx]
```

##### Values

| Action | HEX | Description |
|---|---|---|
| Set | `46 45` | Set the date and time |
| Get | `46 46` | Get the date and time |

| Date time | HEX | Description |
|---|---|---|
| Year | `xx xx` | The year<br />*Without the leading two digits* |
| Month | `xx xx` | The month |
| Day | `xx xx` | The day of the month |
| Weekday | `xx xx` | The day of the week<br />*Ranges from 1 (Monday) to 7 (Sunday)* |
| Hour | `xx xx` | The hour |
| Minute | `xx xx` | The minute |
| Second | `xx xx` | The second |

Each decimal value is encoded to the `xx xx` value by first encoding it to ASCII and then to HEX. Decoding is the other way around. Below you can see en example how the date time `2023-01-21 22:14:47` is encoded/decoded.

| | Year | Month | Day | Weekday | Hour | Minute | Second |
|---|---|---|---|---|---|---|---|
| Decimal | `23` | `1` | `21` | `6` | `22` | `14` | `47` |
| ASCII | `17` | `01` | `15` | `06` | `16` | `0E` | `2F` |
| HEX | `31 37` | `30 31` | `31 35` | `30 36` | `31 36` | `30 45` | `32 46` |

#### Light

##### Request

```
[ACTION] [BRIGHTNESS (optional)]
```

##### Response

```
[STATUS] [BRIGHTNESS]
```

##### Values

| Action | HEX | Description |
|---|---|---|
| Off | `30 30` | Turn the light off |
| On | `30 31` | Turn the light on |
| Set | `46 45` | Set the brightness |

| Brightness | HEX | Description |
|---|---|---|
| Off | `30 30` | Turn the light off using the set action |
| Value | `xx xx` | The brightness of the light (between `36 33` and `46 42`) |

| Status | HEX | Description |
|---|---|---|
| Off | `30 30` | The light is off |
| On | `30 31` | The light is on |

> TODO:
> - Check min/max range
> - Figure out how the HEX values are calculated

#### Settings

##### Request

```
[SETTING: xx xx] [xx] [FEATURES: xx xx] [xx xx xx xx] 30 30 30 30
```

##### Response

```
[SETTING: xx xx] [???: xx] [FEATURES: xx xx] [xx xx xx xx]
```

##### Values

| Setting | HEX | Description |
|---|---|---|
| Icon | `30 30` | Oven icon |
| | `30 31` | Single bed icon |
| | `30 32` | Double bed icon |
| | `30 33` | Chair icon |
| | `30 34` | Couch icon |
| Fireplace name | `46 46` | The name of the fireplace |

| Features | HEX | Bitmask | Description |
|---|---|---|---|
| Timer | `xx 3x` | `???? ???? 0011 ????` | [...] |
| Fan | `xx 3x` | `???? ???? 0011 0001` | [...] |
| Light | `xx 3x` | `???? ???? 0011 0010` | [...] |
| Aux | `xx 3x` | `???? ???? 0011 0100` | [...] |

> TODO:
> - Add bitmask explanation

| ??? | HEX | Description |
|---|---|---|
| [...] | `xx` | [...] |

