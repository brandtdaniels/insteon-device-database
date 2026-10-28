"""Validates the device profiles and bundles them into the published catalog.

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
import string
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

        identities = {(identity["category"], identity["subcategory"]) for identity in profile.get("identities", [])}

        for capability in profile.get("capabilities", []):
            scoped = [(scope["category"], scope["subcategory"]) for scope in capability.get("identities", [])]

            if not set(scoped) <= identities:
                problems.append(f"{path.name}: the {capability['kind']} capability names an identity the product doesn't have")

            if len(scoped) != len(set(scoped)):
                problems.append(f"{path.name}: the {capability['kind']} capability names an identity more than once")

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
    parser.add_argument("--output", type=pathlib.Path, help="where to write v1/catalog.json and v1/manifest.json")
    arguments = parser.parse_args()

    profiles, errors = load_profiles()

    for error in errors:
        print(error, file=sys.stderr)

    if errors:
        sys.exit(1)

    print(f"{len(profiles)} profiles are valid")

    if arguments.output is None:
        return

    catalog = json.dumps({"schemaVersion": SCHEMA_VERSION, "devices": profiles}, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "devices": len(profiles),
        "catalog": "catalog.json",
        "sha256": hashlib.sha256(catalog.encode()).hexdigest(),
    }

    directory = arguments.output / f"v{SCHEMA_VERSION}"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "catalog.json").write_text(catalog)
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (directory / "device-profile.schema.json").write_text((ROOT / "schema" / "device-profile.schema.json").read_text())
    (arguments.output / "index.html").write_text(index_page(profiles))


# The category names the Insteon Developer's Guide gives.
CATEGORY_NAMES = {
    "0x00": "Generalized Controllers",
    "0x01": "Dimmable Lighting Control",
    "0x02": "Switched Lighting Control",
    "0x03": "Network Bridges",
    "0x04": "Irrigation Control",
    "0x05": "Climate Control",
    "0x06": "Pool and Spa Control",
    "0x07": "Sensors and Actuators",
    "0x08": "Home Entertainment",
    "0x09": "Energy Management",
    "0x0A": "Built-In Appliance Control",
    "0x0B": "Plumbing",
    "0x0C": "Communication",
    "0x0D": "Computer Control",
    "0x0E": "Window Coverings",
    "0x0F": "Access Control",
    "0x10": "Security, Health, Safety",
    "0x11": "Surveillance",
    "0x12": "Automotive",
    "0x13": "Pet Care",
    "0x14": "Toys",
    "0x15": "Timekeeping",
    "0x16": "Holiday",
}


# What each category holds, for the page's sections.
CATEGORY_DESCRIPTIONS = {
    "0x00": "Controllers that send commands rather than switch a load of their own, such as remotes, tabletop controllers and range extenders.",
    "0x01": "Dimmers: wall switches, keypads, plug-in and in-line modules, outlets and bulbs that dim the light they control.",
    "0x02": "On/off switches: wall switches, keypads, plug-in and in-line modules, outlets and load controllers that switch what they control.",
    "0x03": "Network bridges that connect a computer, app or network to Insteon, such as modems, Hubs and USB adapters.",
    "0x04": "Irrigation controllers, such as sprinkler valve controllers.",
    "0x05": "Climate control: thermostats and thermostat adapters.",
    "0x06": "Pool and spa controls, such as pump and heater controllers.",
    "0x07": "Sensors and actuators: modules with inputs that sense contact closures and voltages, and relays that drive other equipment.",
    "0x08": "Home entertainment controls, such as audio and video equipment.",
    "0x09": "Energy management: power meters and high-current load controllers.",
    "0x0E": "Window coverings: modules and motors for drapes, shades and shutters.",
    "0x0F": "Access control: locks, deadbolts and garage door controls.",
    "0x10": "Security, health and safety: open/close, motion and leak sensors, and smoke alarm bridges.",
}

# How the page names each capability kind.
CAPABILITY_LABELS = {
    "onOff": "On/off",
    "dimmable": "Dimmable",
    "modem": "Modem",
    "hub": "Hub",
    "hubPro": "Hub Pro",
    "thermostat": "Thermostat",
    "groupEvents": "Group events",
    "heartbeat": "Heartbeat",
    "i2cs": "i2CS checksums",
}


def scope_note(scope):
    """How the page describes the identity and firmware versions a capability applies to."""
    identity = f"{scope['category']}/{scope['subcategory']}"
    selection = scope.get("firmware")

    if selection is None:
        return f"{identity}: every firmware version"

    if "only" in selection:
        return f"{identity}: firmware " + ", ".join(selection["only"])

    return f"{identity}: every firmware version except " + ", ".join(selection["except"])


def capability_descriptions():
    """Each capability kind's description, from the schema."""
    schema = json.loads((ROOT / "schema" / "device-profile.schema.json").read_text())

    return {option["properties"]["kind"]["const"]: option["description"] for option in schema["$defs"]["capability"]["oneOf"]}


def index_page(profiles):
    """The landing page: what the catalog is, its files, and a table of the profiles to search,
    sort and filter."""
    escape = html.escape
    descriptions = capability_descriptions()
    rows = []

    for profile in profiles:
        category = profile["identities"][0]["category"]
        kinds = [capability["kind"] for capability in profile["capabilities"]]
        aliases = profile.get("aliases", [])
        subcategories = []

        for identity in profile["identities"]:
            notes = [identity["region"]] if "region" in identity else []

            if "firmware" in identity:
                notes.append(f"firmware {identity['firmware']['from']}–{identity['firmware']['through']}")

            code = identity["subcategory"] if identity["category"] == category else f"{identity['category']}/{identity['subcategory']}"
            subcategories.append(code + (f" <small>{escape(', '.join(notes))}</small>" if notes else ""))

        search = " ".join([profile["model"], profile["name"], *aliases, *(f"{i['category']}/{i['subcategory']}" for i in profile["identities"])]).lower()
        name = escape(profile["name"])

        if aliases:
            name += '<div class="aliases">Also known as ' + ", ".join(f'<span class="alias">{escape(alias)}</span>' for alias in aliases) + "</div>"

        if "description" in profile:
            name += f'<p class="description">{escape(profile["description"])}</p>'

        chips = ""

        for capability in profile["capabilities"]:
            kind = capability["kind"]
            title = descriptions.get(kind, "")
            label = escape(CAPABILITY_LABELS.get(kind, kind))

            if "identities" in capability:
                title += " Applies to " + "; ".join(scope_note(scope) for scope in capability["identities"]) + "."
                label += ' <span class="firmware">some versions</span>'

            chips += f'<span class="chip" title="{escape(title)}">{label}</span>'

        attributes = {
            "search": search,
            "model": profile["model"],
            "name": profile["name"],
            "capabilities": " ".join(kinds),
            "radio": profile.get("radio", ""),
            "battery": "true" if profile.get("batteryPowered") else "false",
        }
        data = " ".join(f'data-{key}="{escape(value)}"' for key, value in attributes.items())
        rows.append(
            f"<tr {data}>"
            f'<td class="model">{escape(profile["model"])}</td>'
            f"<td>{name}</td>"
            f'<td class="ids">{"".join(f"<span>{subcategory}</span>" for subcategory in subcategories)}</td>'
            f"<td>{chips}</td>"
            "</tr>"
        )

    by_category = {}

    for profile, row in zip(profiles, rows):
        by_category.setdefault(profile["identities"][0]["category"], []).append(row)

    categories = sorted(by_category)
    sections = []

    for category in categories:
        name = escape(CATEGORY_NAMES.get(category, category))
        description = CATEGORY_DESCRIPTIONS.get(category)
        sections.append(
            f'<section class="category" id="category-{category}" data-category="{category}">'
            f"<h3>{name}</h3>"
            + (f'<p class="category-description">{escape(description)}</p>' if description else "")
            + f'<p class="category-count"><span class="products">{len(by_category[category])} products</span> · reported as category {category}</p>'
            '<div class="table-wrap"><table>'
            "<thead><tr><th>Model</th><th>Name</th><th>Subcategory</th><th>Capabilities</th></tr></thead>"
            f"<tbody>{''.join(by_category[category])}</tbody>"
            "</table></div></section>"
        )

    kinds = sorted({capability["kind"] for profile in profiles for capability in profile["capabilities"]})
    template = string.Template((ROOT / "templates" / "index.html").read_text())

    return template.substitute(
        version=SCHEMA_VERSION,
        count=len(profiles),
        sections="\n".join(sections),
        jump_links="".join(f'<a href="#category-{c}">{escape(CATEGORY_NAMES.get(c, c))}</a>' for c in categories),
        category_options="".join(f'<option value="{c}">{escape(CATEGORY_NAMES.get(c, c))}</option>' for c in categories),
        capability_options="".join(f'<option value="{k}">{escape(CAPABILITY_LABELS.get(k, k))}</option>' for k in kinds),
    )


if __name__ == "__main__":
    main()
