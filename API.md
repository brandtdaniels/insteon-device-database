# The catalog API

The catalog is three static JSON files on GitHub Pages. There's no server, no query
parameters and no authentication: a client downloads the catalog and looks devices up itself.

## Files

Every file is under `https://brandtdaniels.github.io/insteon-device-catalog/v1/` and is fetched
with a plain `GET` over HTTPS.

| File | Contents |
| --- | --- |
| `manifest.json` | The schema version, the number of profiles, the catalog's file name and its SHA-256 |
| `catalog.json` | The schema version, every profile sorted by model, and every command set |
| `device-profile.schema.json` | The JSON Schema every profile follows |
| `command-set.schema.json` | The JSON Schema every command set follows |

`manifest.json`:

```json
{
  "catalog": "catalog.json",
  "devices": 14,
  "schemaVersion": 1,
  "sha256": "8d824948278c3c03ffc12ccc994c3f78981de410ebaa3650b174e030de77cfe6"
}
```

`catalog.json`:

```json
{
  "commandSets": [ { "id": "keypadLinc", "name": "KeypadLinc", "…": "…" }, "…" ],
  "devices": [ { "model": "2242", "name": "Hub", "…": "…" }, "…" ],
  "schemaVersion": 1
}
```

## A profile

Bytes are strings of `0x` and two uppercase hexadecimal digits, as Insteon documents write them.

```json
{
  "model": "2852",
  "name": "Leak Sensor",
  "aliases": ["Water Leak Sensor"],
  "description": "Battery-powered sensor that reports when it detects water.",
  "identities": [{ "category": "0x10", "subcategory": "0x08" }],
  "radio": "rf",
  "role": "controller",
  "batteryPowered": true,
  "groups": [
    { "number": "0x01", "name": "Dry", "role": "controller" },
    { "number": "0x02", "name": "Wet", "role": "controller" },
    { "number": "0x04", "name": "Heartbeat", "role": "controller" }
  ],
  "capabilities": [
    {
      "kind": "groupEvents",
      "events": [
        { "group": "0x01", "command1": "0x11", "event": "dry" },
        { "group": "0x02", "command1": "0x11", "event": "wet" }
      ]
    },
    { "kind": "heartbeat", "group": "0x04", "intervalMinutes": 1428 }
  ],
  "sources": ["HouseLinc device catalog", "Insteon command workbook, HeartBeat Status sheet"]
}
```

`aliases` and `description` are optional, for showing and searching products: other names a
product is known by, and what it is.

An identity can also carry a `firmware` range, `{ "from": "0x40", "through": "0xFF" }`, when a
product reports the same category and subcategory with different behavior across firmware
versions. Without one, the identity covers every version.

`engines` says which Insteon engine the product runs under each identity, where a source states
it. Each entry names an `engine` (`i1`, `i2`, or `i2cs`, which rejects an extended message whose
D14 checksum is wrong), an identity's `category` and `subcategory`, and optionally a `firmware`
selection: `{ "only": ["0x41", "0xD1"] }` or `{ "except": ["0x22", "0x24"] }`. Without `firmware`,
every version of the identity runs the engine. For example, the 2476D SwitchLinc Dimmer runs
i2CS, and so expects a checksum in D14 of extended messages, only on the firmware versions its
entries list for each subcategory. A firmware version no entry covers runs an engine the
catalog doesn't know; the build makes sure no two entries cover the same one.

The device itself is the surest source: it reports its engine in reply to a get engine version
command (cmd1 `0x0D`). The catalog's entries are for deciding before asking, or for a device
that doesn't answer.

## Command sets

Many products share the same settings, so the catalog describes them once, as command sets, and
a profile's `commandSets` entries name the one each identity uses:

```json
"commandSets": [{ "commandSet": "switchLincDimmer", "category": "0x01", "subcategory": "0x20" }]
```

Like an engine entry, a command set entry can carry a `firmware` selection when only some
versions use it. A command set is organized by Insteon's own message types:

- **Operating flags**: bits of the reply to Get Operating Flags (cmd1 `0x1F`), each with the
  `query` that cmd2 asks for and the `bit` that holds it, and the Set Operating Flags (cmd1
  `0x20`) cmd2 values `on` and `off` that set it to 1 and 0. `readings` are queries whose whole
  reply is a value, such as the link database's delta, and `flagCommands` are Set Operating
  Flags values with no documented bit to read back.
- **Extended settings**: the `values` in the reply to an extended Get (cmd1 `0x2E`, D2 `0x00`),
  which arrives with `0x01` in D2, each at a `byte` from D3 to D14, and the `writes` that set
  them: an extended Set with the write's `selector` in D2 and its `bytes` from D3. When
  `perButton` is true, D1 chooses the button or group; otherwise D1 is `0x01`.
- **Standard commands**: other standard direct commands, each a `command1` with a fixed
  `command2`, a `parameter` the caller puts in cmd2, or neither for `0x00`. A `reply` is the
  value the acknowledgement carries in cmd2, and `followUps` counts the further direct messages
  with the same cmd1 that carry more. While the operating flag `extendedWhen` names is set, the
  command goes as an extended message with cmd1 and cmd2 again in D1 and D2.
- **Extended commands**: other extended direct commands, such as a Get with a cmd2 other than
  `0x00`. Each gives its `command1` and `command2`, its `fixed` user data bytes, the
  `parameters` the caller fills in, its `integrity`, and the extended `reply` that answers it,
  which its `match` bytes tell apart, with the `values` it carries.
- **Direct messages**: standard direct messages the device sends on its own, such as a
  thermostat's reports, each a `command1` with a `value` in cmd2.
- **Notes** on where Insteon's documents disagree, and the `sources` the values come from.

ALL-Link broadcasts aren't in command sets: a profile's `groupEvents` capability says what each
group's commands mean.

A value in a message names where it is: cmd2 in a standard message, or the user data `byte`, or
`bytes` most significant first, in an extended one. Its `mask`, if any, picks out its bits, and
it reads as:

| `kind` | Meaning |
| --- | --- |
| `number` (the default) | A number, two's complement if `signed`, times `scale`, in `unit` |
| `buttons` | One bit per button, button 1 in bit 0 |
| `enumeration` | A name from the command set's `enumerations` entry that `enumeration` names |
| `flags` | The named `bits` |
| `boolean` | True when nonzero |

A `range` gives the values a parameter can take, in its unit. The unit `displayDegrees` means
degrees in the scale the device displays: the command set's `displayScale` names the flag,
value or bit that is true when it displays Celsius. Without one, or before it's been read,
they're Fahrenheit.

`integrity` says how an extended message's user data is protected: `none`, a `checksum` in D14
(the two's complement of the sum of cmd1, cmd2 and D1 through D13), or a `crc`, a 16-bit CRC
over cmd1, cmd2 and D1 through D12 in D13 and D14.

For example, the reply to Get Operating Flags with cmd2 `0x00` from a device using
`switchLincDimmer` has bit `0x20` set when its key beep is on, and Set Operating Flags with cmd2
`0x0B` turns the beep off. An i2CS device expects these as extended messages with a checksum in
D14.

And a TempLinc Thermostat, which uses `tempLinc`, reports a new temperature with a direct
message whose cmd1 is `0x6E` and whose cmd2 is the temperature in half degrees of the scale it
displays. Its `readStatus` extended command asks for its status, and the reply carries the
temperature in D9 and D10, in tenths of a degree Celsius whatever the display shows.

## Keeping a copy up to date

1. Fetch `manifest.json`.
2. If its `schemaVersion` isn't one the client understands, keep the copy it has.
3. If its `sha256` matches the copy the client has, stop: nothing changed.
4. Otherwise fetch `catalog.json`, check that its bytes hash to `sha256`, and only then replace
   the copy.

Ship a copy with the software, so it works offline and fetching is optional.

## Looking a device up

1. Ask the device to identify itself. Its reply carries its category, subcategory and firmware
   version.
2. Find the profile with an identity whose `category` and `subcategory` match and whose
   `firmware` range, if it has one, includes the firmware version. The build makes sure no two
   identities overlap, so there's at most one.
3. With no match, fall back on what the category alone implies, such as dimming for category
   `0x01` and switching for `0x02`.

Example: a device replies with category `0x10`, subcategory `0x08`. That's the 2852 Leak
Sensor above, so an ALL-Link broadcast from it with cmd1 `0x11` to group `0x02` means `wet`, and
not hearing from it for longer than its 1428-minute heartbeat interval means it may have stopped
working.

## Versions

The `v1` in the path is the format's version. Adding profiles, or optional fields a `v1` client
can ignore, keeps `v1`. A change that would break a `v1` client is published under `v2`, and `v1`
stays where it is.
