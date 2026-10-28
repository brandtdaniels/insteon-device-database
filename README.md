# Insteon Device Catalog

[![Catalog](https://github.com/brandtdaniels/insteon-device-catalog/actions/workflows/catalog.yml/badge.svg?branch=main)](https://github.com/brandtdaniels/insteon-device-catalog/actions/workflows/catalog.yml)
[![Device profiles](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fbrandtdaniels.github.io%2Finsteon-device-catalog%2Fv1%2Fmanifest.json&query=%24.devices&label=device%20profiles)](https://brandtdaniels.github.io/insteon-device-catalog/v1/catalog.json)
[![Schema](https://img.shields.io/badge/schema-v1-blue.svg)](schema/device-profile.schema.json)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

What each Insteon product is and what it can do, as data, so software can support a device by
looking it up instead of carrying code for it.

Each product has a profile in [`devices/`](devices), named by its model number. A profile lists:

- **Name, aliases and description:** the product's name, other names it's known by, and what
  it is.
- **Identities:** the category and subcategory the product reports when asked to identify
  itself, and the firmware versions they cover where those matter.
- **Radio and role:** where a source states them, how it communicates (powerline, RF or both), and whether it can be an
  ALL-Link controller, a responder, or both.
- **Groups:** its ALL-Link groups, and whether software must link a group.
- **Capabilities:** what it can do, chosen from a fixed set: `onOff`, `dimmable`, `modem`,
  `hub`, `hubPro`, `thermostat`, `groupEvents` and `heartbeat`. A capability is a description,
  never code.
- **Engines:** where a source states it, the Insteon engine (i1, i2 or i2CS) the product runs
  under each identity and firmware version.
- **Sources:** the documents its values come from.

[`schema/device-profile.schema.json`](schema/device-profile.schema.json) defines the format.

## Using the catalog

Every change to `main` publishes the profiles to GitHub Pages:

- `https://brandtdaniels.github.io/insteon-device-catalog/v1/catalog.json`: every profile,
  sorted by model
- `https://brandtdaniels.github.io/insteon-device-catalog/v1/manifest.json`: the schema version,
  the number of profiles and the catalog's SHA-256
- `https://brandtdaniels.github.io/insteon-device-catalog/v1/device-profile.schema.json`: the
  schema
- `https://brandtdaniels.github.io/insteon-device-catalog/`: a page listing the files and every
  profile, for people rather than software

See [API.md](API.md) for the files' formats, how to keep a copy up to date and how to look a
device up. In short: read the manifest first, check that its schema version is one you
understand, then download the catalog and check its hash. A breaking change to the format gets a new version path, so `v1`
keeps working for software built against it. Software should ship a copy of the catalog and
treat downloading a newer one as optional.

## Adding or changing a profile

1. Add or edit `devices/<model>.json`. Check every value against a document, and list the
   document in `sources`.
2. Run `pip install -r requirements.txt` and `python3 -I scripts/build.py` to validate. It checks
   each profile against the schema, that the file is named for its model, that no capability
   appears twice, that no two profiles claim the same identity for the same firmware, and that
   each engine entry names one of the product's identities and no firmware version twice.
3. Open a pull request. CI runs the same check.
