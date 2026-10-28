# The catalog API

The catalog is three static JSON files on GitHub Pages. There's no server, no query
parameters and no authentication: a client downloads the catalog and looks devices up itself.

## Files

Every file is under `https://brandtdaniels.github.io/insteon-device-catalog/v1/` and is fetched
with a plain `GET` over HTTPS.

| File | Contents |
| --- | --- |
| `manifest.json` | The schema version, the number of profiles, the catalog's file name and its SHA-256 |
| `catalog.json` | The schema version and every profile, sorted by model |
| `device-profile.schema.json` | The JSON Schema every profile follows |

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
