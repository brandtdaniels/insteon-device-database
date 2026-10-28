"""Validates the device profiles and bundles them into the published database.

Usage: python3 scripts/build.py [--output DIR]

Every file in devices/ must match schema/device-profile.schema.json, and no two profiles may
claim the same category, subcategory and firmware. The output is deterministic: the same
profiles always produce the same bytes, so the manifest's hash changes only when the data
does.
"""

import argparse
import hashlib
import html
import json
import pathlib
import sys

import jsonschema

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA_VERSION = 1


def load_profiles():
    schema = json.loads((ROOT / "schema" / "device-profile.schema.json").read_text())
    validator = jsonschema.Draft202012Validator(schema)
    profiles = []
    errors = []

    for path in sorted((ROOT / "devices").glob("*.json")):
        profile = json.loads(path.read_text())
        problems = [f"{path.name}: {error.json_path}: {error.message}" for error in validator.iter_errors(profile)]

        if path.stem != profile.get("model"):
            problems.append(f"{path.name}: the file name must be the model, {profile.get('model')!r}")

        kinds = [capability["kind"] for capability in profile.get("capabilities", [])]

        if len(kinds) != len(set(kinds)):
            problems.append(f"{path.name}: a capability kind appears more than once")

        errors += problems
        profiles.append(profile)

    errors += overlapping_identities(profiles)

    return profiles, errors


def firmware_range(identity):
    firmware = identity.get("firmware")

    if firmware is None:
        return 0x00, 0xFF

    return int(firmware["from"], 16), int(firmware["through"], 16)


def overlapping_identities(profiles):
    """Reports identities that two profiles, or one profile twice, claim for the same firmware."""
    claimed = {}
    errors = []

    for profile in profiles:
        for identity in profile["identities"]:
            key = (identity["category"], identity["subcategory"])
            low, high = firmware_range(identity)

            for other_model, other_low, other_high in claimed.get(key, []):
                if low <= other_high and other_low <= high:
                    errors.append(f"{profile['model']} and {other_model} both claim {key[0]}/{key[1]} for overlapping firmware")

            claimed.setdefault(key, []).append((profile["model"], low, high))

    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=pathlib.Path, help="where to write v1/database.json and v1/manifest.json")
    arguments = parser.parse_args()

    profiles, errors = load_profiles()

    for error in errors:
        print(error, file=sys.stderr)

    if errors:
        sys.exit(1)

    print(f"{len(profiles)} profiles are valid")

    if arguments.output is None:
        return

    database = json.dumps({"schemaVersion": SCHEMA_VERSION, "devices": profiles}, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "devices": len(profiles),
        "database": "database.json",
        "sha256": hashlib.sha256(database.encode()).hexdigest(),
    }

    directory = arguments.output / f"v{SCHEMA_VERSION}"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "database.json").write_text(database)
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (directory / "device-profile.schema.json").write_text((ROOT / "schema" / "device-profile.schema.json").read_text())
    (arguments.output / "index.html").write_text(index_page(profiles))


INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>INSTEON Device Database</title>
<style>
  :root {{ color-scheme: light dark; font-family: system-ui, sans-serif; line-height: 1.5; }}
  body {{ max-width: 60rem; margin: 2rem auto; padding: 0 1rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: 0.25rem 0.75rem 0.25rem 0; border-bottom: 1px solid color-mix(in srgb, currentColor 20%, transparent); vertical-align: top; }}
  code {{ font-size: 0.9em; }}
</style>
</head>
<body>
<h1>INSTEON Device Database</h1>
<p>What each INSTEON product is and what it can do, keyed by the category, subcategory and
firmware version a device reports. Software downloads the database and looks devices up itself.</p>
<ul>
  <li><a href="v{version}/manifest.json"><code>v{version}/manifest.json</code></a>: the schema version, the number of profiles and the database's SHA-256</li>
  <li><a href="v{version}/database.json"><code>v{version}/database.json</code></a>: every profile</li>
  <li><a href="v{version}/device-profile.schema.json"><code>v{version}/device-profile.schema.json</code></a>: the JSON Schema each profile follows</li>
  <li><a href="https://github.com/brandtdaniels/insteon-device-database/blob/main/API.md">How to use the database</a> and <a href="https://github.com/brandtdaniels/insteon-device-database">the source</a></li>
</ul>
<h2>{count} profiles</h2>
<table>
<thead><tr><th>Model</th><th>Name</th><th>Category / subcategory</th><th>Capabilities</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
</body>
</html>
"""


def index_page(profiles):
    """The landing page: what the database is, its files, and a table of the profiles."""
    rows = []

    for profile in profiles:
        identities = ", ".join(f"{identity['category']}/{identity['subcategory']}" for identity in profile["identities"])
        capabilities = ", ".join(capability["kind"] for capability in profile["capabilities"])
        cells = [profile["model"], profile["name"], identities, capabilities]
        rows.append("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in cells) + "</tr>")

    return INDEX_TEMPLATE.format(version=SCHEMA_VERSION, count=len(profiles), rows="\n".join(rows))


if __name__ == "__main__":
    main()
