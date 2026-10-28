# INSTEON Device Database

What each INSTEON product is and what it can do, as data, so software can support a device by
looking it up instead of carrying code for it.

Each product has a profile in [`devices/`](devices), named by its model number. A profile lists:

- **Identities:** the category and subcategory the product reports when asked to identify
  itself, and the firmware versions they cover where those matter.
- **Radio and role:** how it communicates (powerline, RF or both), and whether it can be an
  ALL-Link controller, a responder, or both.
- **Groups:** its ALL-Link groups, and whether software must link a group.
- **Capabilities:** what it can do, chosen from a fixed set: `onOff`, `dimmable`, `modem`,
  `hub`, `hubPro`, `thermostat`, `groupEvents` and `heartbeat`. A capability is a description,
  never code.
- **Sources:** the documents its values come from.

[`schema/device-profile.schema.json`](schema/device-profile.schema.json) defines the format.

## Using the database

Every change to `master` publishes the profiles to GitHub Pages:

- `https://brandtdaniels.github.io/insteon-device-database/v1/database.json`: every profile,
  sorted by model
- `https://brandtdaniels.github.io/insteon-device-database/v1/manifest.json`: the schema version,
  the number of profiles and the database's SHA-256
- `https://brandtdaniels.github.io/insteon-device-database/v1/device-profile.schema.json`: the
  schema

Read the manifest first, check that its schema version is one you understand, then download the
database and check its hash. A breaking change to the format gets a new version path, so `v1`
keeps working for software built against it. Software should ship a copy of the database and
treat downloading a newer one as optional.

## Adding or changing a profile

1. Add or edit `devices/<model>.json`. Check every value against a document, and list the
   document in `sources`.
2. Run `pip install -r requirements.txt` and `python3 -I scripts/build.py` to validate. It checks
   each profile against the schema, that the file is named for its model, that no capability
   appears twice, and that no two profiles claim the same identity for the same firmware.
3. Open a pull request. CI runs the same check.
