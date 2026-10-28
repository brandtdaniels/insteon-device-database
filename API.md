# The database API

The database is three static JSON files on GitHub Pages. There's no server, no query
parameters and no authentication: a client downloads the database and looks devices up itself.

## Files

Every file is under `https://brandtdaniels.github.io/insteon-device-database/v1/` and is fetched
with a plain `GET` over HTTPS.

| File | Contents |
| --- | --- |
| `manifest.json` | The schema version, the number of profiles, the database's file name and its SHA-256 |
| `database.json` | The schema version and every profile, sorted by model |
| `device-profile.schema.json` | The JSON Schema every profile follows |

`manifest.json`:

```json
{
  "database": "database.json",
  "devices": 14,
  "schemaVersion": 1,
  "sha256": "8d824948278c3c03ffc12ccc994c3f78981de410ebaa3650b174e030de77cfe6"
}
```

`database.json`:

```json
{
  "devices": [ { "model": "2242", "name": "Hub", "…": "…" }, "…" ],
  "schemaVersion": 1
}
```

## A profile

Bytes are strings of `0x` and two uppercase hexadecimal digits, as INSTEON documents write them.

```json
{
  "model": "2852",
  "name": "Leak Sensor",
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

An identity can also carry a `firmware` range, `{ "from": "0x40", "through": "0xFF" }`, when a
product reports the same category and subcategory with different behavior across firmware
versions. Without one, the identity covers every version.

## Keeping a copy up to date

1. Fetch `manifest.json`.
2. If its `schemaVersion` isn't one the client understands, keep the copy it has.
3. If its `sha256` matches the copy the client has, stop: nothing changed.
4. Otherwise fetch `database.json`, check that its bytes hash to `sha256`, and only then replace
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
