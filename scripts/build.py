"""Validates the device profiles and bundles them into the published database.

Usage: python3 scripts/build.py [--output DIR]

Every file in devices/ must match schema/device-profile.schema.json, and no two profiles may
claim the same category, subcategory and firmware. The output is deterministic: the same
profiles always produce the same bytes, so the manifest's hash changes only when the data
does.
"""

import argparse
import hashlib
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


if __name__ == "__main__":
    main()
