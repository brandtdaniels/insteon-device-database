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
import re
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

        # The checks below read fields the schema requires, so they wait until it passes.
        if problems:
            errors += problems
            continue

        if path.stem != profile.get("model"):
            problems.append(f"{path.name}: the file name must be the model, {profile.get('model')!r}")

        kinds = [capability["kind"] for capability in profile.get("capabilities", [])]

        if len(kinds) != len(set(kinds)):
            problems.append(f"{path.name}: a capability kind appears more than once")

        problems += [f"{path.name}: {problem}" for problem in scoped_entry_problems(profile, "engines", "engine")]
        problems += [f"{path.name}: {problem}" for problem in scoped_entry_problems(profile, "commandSets", "command set")]

        errors += problems
        profiles.append(profile)

    errors += overlapping_identities(profiles)

    return profiles, errors


def selected_firmware(selection):
    """The firmware versions a selection includes, or every version for none."""
    if selection is None:
        return set(range(0x100))

    if "only" in selection:
        return {int(version, 16) for version in selection["only"]}

    return set(range(0x100)) - {int(version, 16) for version in selection["except"]}


def scoped_entry_problems(profile, field, label):
    """Reports entries of a field such as engines for identities the product doesn't have, and
    firmware versions two entries cover under the same identity."""
    identities = {(identity["category"], identity["subcategory"]) for identity in profile.get("identities", [])}
    claimed = {}
    problems = []

    for entry in profile.get(field, []):
        key = (entry["category"], entry["subcategory"])

        if key not in identities:
            problems.append(f"the {label} entry for {key[0]}/{key[1]} names an identity the product doesn't report")
            continue

        versions = selected_firmware(entry.get("firmware"))

        if versions & claimed.get(key, set()):
            problems.append(f"two {label} entries cover the same firmware under {key[0]}/{key[1]}")

        claimed[key] = claimed.get(key, set()) | versions

    return problems


def load_command_sets(profiles):
    """Loads the command sets, and reports those that don't match the schema and profiles that
    name a command set that doesn't exist."""
    schema = json.loads((ROOT / "schema" / "command-set.schema.json").read_text())
    validator = jsonschema.Draft202012Validator(schema)
    command_sets = []
    errors = []

    for path in sorted((ROOT / "commandSets").glob("*.json")):
        command_set = json.loads(path.read_text())
        schema_errors = [f"{path.name}: {error.json_path}: {error.message}" for error in validator.iter_errors(command_set)]

        # The checks below read fields the schema requires, so they wait until it passes.
        if schema_errors:
            errors += schema_errors
            continue

        if path.stem != command_set.get("id"):
            errors.append(f"{path.name}: the file name must be the id, {command_set.get('id')!r}")

        errors += [f"{path.name}: {problem}" for problem in command_set_problems(command_set)]
        command_sets.append(command_set)

    ids = {command_set.get("id") for command_set in command_sets}

    for profile in profiles:
        for entry in profile.get("commandSets", []):
            if entry["commandSet"] not in ids:
                errors.append(f"{profile['model']}.json: it names the command set {entry['commandSet']!r}, which doesn't exist")

    return command_sets, errors


def command_set_problems(command_set):
    """Reports names used twice, flags sharing a bit or a command, values sharing a byte, writes
    sharing a selector, and writes that fill a byte twice."""
    problems = []
    flags = command_set.get("operatingFlags", [])
    flag_commands = command_set.get("flagCommands", [])
    settings = command_set.get("extendedSettings", {})
    values = settings.get("values", [])
    writes = settings.get("writes", [])

    for kind, items in [("flag", flags + command_set.get("readings", []) + flag_commands), ("value", values), ("write", writes)]:
        names = [item["name"] for item in items]

        if len(names) != len(set(names)):
            problems.append(f"a {kind} name appears more than once")

    bits = [(flag["query"], flag["bit"]) for flag in flags]

    if len(bits) != len(set(bits)):
        problems.append("two operating flags share a bit")

    commands = [flag[key] for flag in flags for key in ("on", "off") if key in flag] + [command["command2"] for command in flag_commands]

    if len(commands) != len(set(commands)):
        problems.append("two Set Operating Flags commands share a cmd2")

    if len({value["byte"] for value in values}) != len(values):
        problems.append("two values share a byte")

    if len({write["selector"] for write in writes}) != len(writes):
        problems.append("two writes share a selector")

    for write in writes:
        positions = [byte["position"] for byte in write["bytes"]]

        if len(positions) != len(set(positions)):
            problems.append(f"the {write['name']} write fills a byte twice")

    return problems + message_problems(command_set)


def message_problems(command_set):
    """Reports message names used twice, standard commands and direct messages that share a
    command, values in the wrong place or with an encoding that doesn't fit their kind, user data
    bytes filled twice, and names of flags and enumerations that don't exist."""
    problems = []
    standard = command_set.get("standardCommands", [])
    extended = command_set.get("extendedCommands", [])
    direct = command_set.get("directMessages", [])
    enumerations = {enumeration["name"]: enumeration for enumeration in command_set.get("enumerations", [])}
    flag_names = {flag["name"] for flag in command_set.get("operatingFlags", [])}

    names = [item["name"] for item in standard + extended + direct]

    if len(names) != len(set(names)):
        problems.append("a command or message name appears more than once")

    if len(enumerations) != len(command_set.get("enumerations", [])):
        problems.append("an enumeration name appears more than once")

    for enumeration in enumerations.values():
        if len({value["value"] for value in enumeration["values"]}) != len(enumeration["values"]):
            problems.append(f"the {enumeration['name']} enumeration names a value twice")

        if len({value["name"] for value in enumeration["values"]}) != len(enumeration["values"]):
            problems.append(f"the {enumeration['name']} enumeration uses a name twice")

    def command2s(command):
        """The cmd2 values a standard command sends, or None for any."""
        if "parameter" not in command:
            return {command.get("command2", "0x00")}

        enumeration = enumerations.get(command["parameter"].get("enumeration"))

        return {value["value"] for value in enumeration["values"]} if enumeration else None

    for index, command in enumerate(standard):
        for other in standard[index + 1:]:
            if command["command1"] != other["command1"]:
                continue

            mine, theirs = command2s(command), command2s(other)

            if mine is None or theirs is None or mine & theirs:
                problems.append(f"the {command['name']} and {other['name']} commands share a cmd1 and cmd2")

    def extended_key(command1, command2, fixed_bytes):
        return (command1, command2, tuple(sorted((byte["position"], byte["value"]) for byte in fixed_bytes)))

    requests = [extended_key(command["command1"], command["command2"], command.get("fixed", [])) for command in extended]
    replies = [extended_key(command["reply"].get("command1", command["command1"]), command["reply"]["command2"], command["reply"].get("match", [])) for command in extended if "reply" in command]

    if len(requests) != len(set(requests)):
        problems.append("two extended commands send the same cmd1, cmd2 and fixed bytes")

    if len(replies) != len(set(replies)):
        problems.append("two extended replies can't be told apart by their cmd1, cmd2 and match bytes")

    for item in command_set.get("operatingFlags", []) + command_set.get("flagCommands", []):
        if "extendedWhen" in item and item["extendedWhen"] not in flag_names:
            problems.append(f"the {item['name']} flag names the operating flag {item['extendedWhen']!r}, which doesn't exist")

    if len({message["command1"] for message in direct}) != len(direct):
        problems.append("two direct messages share a cmd1")

    def field_problems(field, owner, extended_message):
        found = []
        located = ("byte" in field) + ("bytes" in field)

        if extended_message and located != 1:
            found.append(f"{owner}: the {field['name']} value needs a byte or bytes")

        if not extended_message and located:
            found.append(f"{owner}: the {field['name']} value is in cmd2, so it can't name user data bytes")

        kind = field.get("kind", "number")

        if (kind == "enumeration") != ("enumeration" in field):
            found.append(f"{owner}: the {field['name']} value names an enumeration only if its kind is enumeration")
        elif "enumeration" in field and field["enumeration"] not in enumerations:
            found.append(f"{owner}: the {field['name']} value names the enumeration {field['enumeration']!r}, which doesn't exist")

        if (kind == "flags") != ("bits" in field):
            found.append(f"{owner}: the {field['name']} value names bits only if its kind is flags")

        if "mask" in field and (int(field["mask"], 16) == 0 or "bytes" in field):
            found.append(f"{owner}: the {field['name']} value's mask must pick out some bits of a single byte")

        if kind != "number" and any(key in field for key in ("scale", "unit", "signed")):
            found.append(f"{owner}: the {field['name']} value has a scale, unit or sign, which only a number can have")

        if "range" in field and field["range"]["from"] > field["range"]["through"]:
            found.append(f"{owner}: the {field['name']} value's range runs backward")

        bits = field.get("bits", [])

        if any(int(bit["mask"], 16) == 0 for bit in bits) or len({bit["mask"] for bit in bits}) != len(bits) or len({bit["name"] for bit in bits}) != len(bits):
            found.append(f"{owner}: the {field['name']} value's bits must have distinct, nonzero masks and distinct names")

        if kind == "buttons" and not extended_message:
            found.append(f"{owner}: the {field['name']} value can't be buttons in cmd2")

        return found

    def reserved(integrity):
        return [(position, 0xFF) for position in {"checksum": [14], "crc": [13, 14]}.get(integrity, [])]

    def positions(fields):
        """The user data bytes the values fill, each with the bits it fills."""
        found = []

        for field in fields:
            for position in [field["byte"]] if "byte" in field else field.get("bytes", []):
                found.append((position, int(field.get("mask", "0xFF"), 16)))

        return found

    def overlaps(filled):
        return any(a[0] == b[0] and a[1] & b[1] for index, a in enumerate(filled) for b in filled[index + 1:])

    for command in standard:
        owner = f"the {command['name']} command"

        for key in ("parameter", "reply", "followUp"):
            if key in command:
                problems += field_problems(command[key], owner, False)

        if "extendedWhen" in command and command["extendedWhen"] not in flag_names:
            problems.append(f"{owner}: it names the operating flag {command['extendedWhen']!r}, which doesn't exist")

    for command in extended:
        owner = f"the {command['name']} command"
        parameters = command.get("parameters", [])

        for field in parameters:
            problems += field_problems(field, owner, True)

        filled = positions(parameters) + [(byte["position"], 0xFF) for byte in command.get("fixed", [])] + reserved(command.get("integrity")) + ([(1, 0xFF)] if command.get("perButton") else [])

        if overlaps(filled):
            problems.append(f"{owner}: it fills a user data byte twice")

        if "reply" in command:
            reply = command["reply"]

            for field in reply["values"]:
                problems += field_problems(field, f"{owner}'s reply", True)

            read = positions(reply["values"]) + [(byte["position"], 0xFF) for byte in reply.get("match", [])] + reserved(reply.get("integrity"))

            if overlaps(read):
                problems.append(f"{owner}'s reply reads a user data byte twice")

    for message in direct:
        problems += field_problems(message["value"], f"the {message['name']} message", False)

    if "displayScale" in command_set:
        known = flag_names | {field["name"] for command in extended for field in command.get("reply", {}).get("values", [])}
        known |= {bit["name"] for command in extended for field in command.get("reply", {}).get("values", []) for bit in field.get("bits", [])}
        known |= {value["name"] for value in command_set.get("extendedSettings", {}).get("values", [])}

        if command_set["displayScale"]["celsiusWhen"] not in known:
            problems.append(f"the displayScale names {command_set['displayScale']['celsiusWhen']!r}, which isn't a flag, value or bit")

    return problems


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


# Forms CONVENTIONS.md rules out of the catalog's prose, and what to write instead.
RULED_OUT_TERMS = [
    (r"\bINSTEON\b", "Insteon"),
    (r"(?<![.\w])[iI]2cs\b|\bI2CS\b", "i2CS"),
    (r"\b[Aa]cknowledgement", "acknowledgment"),
    (r"\b[Pp]ower line", "powerline"),
    (r"\bon level\b", "on-level"),
    (r"\b(2242|2245) Hub\b", "Hub 2242, Hub 2245"),
    (r"\bAll-Link|\ball-link", "ALL-Link"),
    (r"(?<!ALL-)\b[Ll]ink database", "ALL-Link database"),
    (r"\bclean-up", "cleanup"),
    (r"\b[Ss]et button\b", "SET button"),
]


def term_problems(label, value, key=None):
    """The ruled-out terms in a profile's or command set's descriptions, notes and names."""

    problems = []

    if isinstance(value, dict):
        for child_key, child in value.items():
            problems += term_problems(label, child, child_key)
    elif isinstance(value, list):
        for child in value:
            problems += term_problems(label, child, key)
    elif isinstance(value, str) and (key in {"description", "note", "notes"} or (key == "name" and " " in value)):
        prose = re.sub(r"`[^`]*`", "", value)

        for pattern, replacement in RULED_OUT_TERMS:
            if found := re.search(pattern, prose):
                problems.append(f"{label}: {found.group(0)!r} in {key}; use {replacement}")

    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=pathlib.Path, help="where to write v1/catalog.json and v1/manifest.json")
    arguments = parser.parse_args()

    profiles, errors = load_profiles()
    command_sets, command_set_errors = load_command_sets(profiles)
    errors += command_set_errors

    for profile in profiles:
        errors += term_problems(f"{profile['model']}.json", profile)

    for command_set in command_sets:
        errors += term_problems(f"{command_set['id']}.json", command_set)

    for error in errors:
        print(error, file=sys.stderr)

    if errors:
        sys.exit(1)

    print(f"{len(profiles)} profiles and {len(command_sets)} command sets are valid")

    if arguments.output is None:
        return

    catalog = json.dumps({"schemaVersion": SCHEMA_VERSION, "devices": profiles, "commandSets": command_sets}, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
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
    (directory / "command-set.schema.json").write_text((ROOT / "schema" / "command-set.schema.json").read_text())
    (arguments.output / "index.html").write_text(index_page(profiles, command_sets))


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
}

# How the page names each engine.
ENGINE_LABELS = {"i1": "i1", "i2": "i2", "i2cs": "i2CS"}


def engine_note(entry):
    """How the page shows an identity's engine, with the firmware versions in its tooltip."""
    label = ENGINE_LABELS[entry["engine"]]
    selection = entry.get("firmware")

    if selection is None:
        return label, f"Every firmware version runs {label}."

    if "only" in selection:
        return f"{label} on some firmware", f"Firmware {', '.join(selection['only'])} runs {label}."

    return f"{label} on most firmware", f"Every firmware version except {', '.join(selection['except'])} runs {label}."


def capability_descriptions():
    """Each capability kind's description, from the schema."""
    schema = json.loads((ROOT / "schema" / "device-profile.schema.json").read_text())

    return {option["properties"]["kind"]["const"]: option["description"] for option in schema["$defs"]["capability"]["oneOf"]}


def index_page(profiles, command_sets):
    """The landing page: what the catalog is, its files, and a table of the profiles to search,
    sort and filter."""
    escape = html.escape
    descriptions = capability_descriptions()
    names = {command_set["id"]: command_set for command_set in command_sets}
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
            engines = ""

            for entry in profile.get("commandSets", []):
                if (entry["category"], entry["subcategory"]) == (identity["category"], identity["subcategory"]):
                    command_set = names[entry["commandSet"]]
                    label = f'{command_set["name"]} settings'
                    title = command_set["description"]

                    if "firmware" in entry:
                        selection = entry["firmware"]
                        versions = ", ".join(selection.get("only", selection.get("except", [])))
                        label += " on some firmware" if "only" in selection else " on most firmware"
                        title += f" Firmware {versions}." if "only" in selection else f" Every firmware version except {versions}."

                    engines += f' <small class="engine" title="{escape(title)}">{escape(label)}</small>'

            for entry in profile.get("engines", []):
                if (entry["category"], entry["subcategory"]) == (identity["category"], identity["subcategory"]):
                    label, title = engine_note(entry)
                    engines += f' <small class="engine" title="{escape(title)}">{escape(label)}</small>'

            subcategories.append(code + (f" <small>{escape(', '.join(notes))}</small>" if notes else "") + engines)

        search = " ".join([
            profile["model"],
            profile["name"],
            *aliases,
            *(f"{i['category']}/{i['subcategory']}" for i in profile["identities"]),
            *(entry["engine"] for entry in profile.get("engines", [])),
        ]).lower()
        name = escape(profile["name"])

        if aliases:
            name += '<div class="aliases">Also known as ' + ", ".join(f'<span class="alias">{escape(alias)}</span>' for alias in aliases) + "</div>"

        if "description" in profile:
            name += f'<p class="description">{escape(profile["description"])}</p>'

        chips = ""

        for kind in kinds:
            title = descriptions.get(kind, "")
            chips += f'<span class="chip" title="{escape(title)}">{escape(CAPABILITY_LABELS.get(kind, kind))}</span>'

        attributes = {
            "search": search,
            "model": profile["model"],
            "name": profile["name"],
            "capabilities": " ".join(kinds),
            "engines": " ".join(sorted({entry["engine"] for entry in profile.get("engines", [])})),
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
            f'<p class="category-code">Category {category}</p>'
            + (f'<p class="category-description">{escape(description)}</p>' if description else "")
            + f'<p class="category-count"><span class="products">{len(by_category[category])} products</span></p>'
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
        engine_options="".join(
            f'<option value="{e}">{ENGINE_LABELS[e]}</option>'
            for e in ENGINE_LABELS
            if any(entry["engine"] == e for profile in profiles for entry in profile.get("engines", []))
        ),
        capability_options="".join(f'<option value="{k}">{escape(CAPABILITY_LABELS.get(k, k))}</option>' for k in kinds),
    )


if __name__ == "__main__":
    main()
