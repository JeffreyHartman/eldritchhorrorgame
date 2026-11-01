#!/usr/bin/env python3
"""Audit and sync `src/pursuit/data` against the Eldritch Horror Fandom wiki.

The wiki's MediaWiki API is open even though the rendered pages sit behind
Cloudflare, so every card, encounter table, investigator, and Ancient One can be
read as a template. This script pulls those templates, converts the markup to
plain game text, and rewrites the prose fields in the JSON data. It never touches
the `effects` arrays: the wiki gives English, not this engine's effect DSL.

Usage:
    python scripts/sync_wiki.py                 # report differences, write nothing
    python scripts/sync_wiki.py --apply         # rewrite the prose fields
    python scripts/sync_wiki.py --apply-stats   # rewrite the monster stat lines
    python scripts/sync_wiki.py --offline       # reuse the cached pages

The cache lives in the system temp directory, so a second run needs no network.
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API_URL = "https://eldritchhorror.fandom.com/api.php"
DATA_DIR = Path(__file__).resolve().parent.parent / "src" / "pursuit" / "data"
CACHE_DIR = Path(tempfile.gettempdir()) / "eldritch-pursuit-wiki"
CACHE_FILE = CACHE_DIR / "pages.json"
USER_AGENT = "eldritch-pursuit-content-sync/1.0"

EXTRA_PAGES = (
    "Defeated",
    "General Encounter",
    "Location Encounter",
    "Expedition Encounters",
    "Other World Encounters",
    "Research Encounter",
    "Special Encounters",
    "Combat Encounter",
    "Debt",
    "Dark Pact",
    "Blessed",
    "Cursed",
)


# --- MediaWiki API --------------------------------------------------------------------


def _api(params: dict[str, str]) -> dict[str, Any]:
    params = {**params, "format": "json"}
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _category_members(category: str) -> list[str]:
    titles: list[str] = []
    params = {"action": "query", "list": "categorymembers", "cmtitle": category, "cmlimit": "500"}
    while True:
        data = _api(params)
        titles.extend(member["title"] for member in data["query"]["categorymembers"])
        if "continue" not in data:
            return titles
        params["cmcontinue"] = data["continue"]["cmcontinue"]


def fetch_pages(offline: bool = False) -> dict[str, str]:
    cache: dict[str, str] = {}
    if CACHE_FILE.exists():
        cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    titles = sorted(set(_category_members("Category:Core_Game")) | set(EXTRA_PAGES))
    missing = [title for title in titles if title not in cache]
    if offline and missing:
        raise SystemExit(f"{CACHE_FILE} is missing {len(missing)} pages; drop --offline to fetch them")
    for start in range(0, len(missing), 50):
        batch = missing[start : start + 50]
        data = _api(
            {
                "action": "query",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "titles": "|".join(batch),
            }
        )
        for page in data.get("query", {}).get("pages", {}).values():
            revisions = page.get("revisions") or []
            if not revisions:
                continue
            slots = revisions[0].get("slots", {})
            content = slots.get("main", {}).get("*") or revisions[0].get("*", "")
            cache[page["title"]] = content
        time.sleep(0.1)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    return cache


# --- wikitext to plain game text ------------------------------------------------------

ICON_NAMES = {
    "doom": "Doom",
    "clue": "Clue",
    "clues": "Clues",
    "et": "Eldritch token",
    "eldritch": "Eldritch token",
    "gate": "Gate",
    "gates": "Gates",
    "focus": "Focus",
    "resource": "Resource",
    "ship": "Ship",
    "ship ticket": "Ship travel ticket",
    "ship tickets": "Ship travel tickets",
    "train": "Train",
    "train ticket": "Train travel ticket",
    "train tickets": "Train travel tickets",
    "city": "City",
    "wilderness": "Wilderness",
    "sea": "Sea",
    "green": "green",
    "blue": "blue",
    "red": "red",
    "reckoning": "Reckoning",
    "action": "Action",
    "monster": "Monster",
    "players": "investigators",
    "noinvestigators": "investigators",
}


def _icon(match: re.Match[str]) -> str:
    parts = [part.strip() for part in match.group(1).split("|")]
    name = ICON_NAMES.get(parts[0].lower(), parts[0])
    count = parts[1] if len(parts) > 1 and parts[1].isdigit() else None
    if count:
        return f"{count} {name}{'s' if int(count) > 1 and not name.endswith('s') else ''}"
    return name


def plain(text: str | None) -> str:
    """Convert MediaWiki markup to the plain game text used in the JSON files."""
    if not text:
        return ""
    text = text.replace("\u200e", "").replace("\u200f", "").replace("\u200b", "")
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
    text = re.sub(r"<ref[^>]*/\s*>", "", text)
    text = re.sub(r"\{\{Ref\|[^}]*\}\}", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\{\{[Ff]lavor\|([^}]*)\}\}", r"\1", text)
    text = re.sub(r"\{\{[Rr]eckoning\}\}", "Reckoning", text)
    text = re.sub(r"\{\{[Ii]con\|([^}]+)\}\}", _icon, text)
    text = re.sub(r"\{\{[Nn]o[Ii]nvestigators\}\}", "investigators", text)
    text = re.sub(r"\{\{[Hh]ealth\|value=(\d+)\}\}", r"\1 Health", text)
    text = re.sub(r"\{\{[Ss]anity\|value=(\d+)\}\}", r"\1 Sanity", text)
    text = re.sub(r"\{\{[Hh]ealth\}\}", "Health", text)
    text = re.sub(r"\{\{[Ss]anity\}\}", "Sanity", text)
    for skill in ("Lore", "Influence", "Observation", "Strength", "Will"):
        text = re.sub(r"\{\{" + skill + r"\}\}", skill, text, flags=re.IGNORECASE)
    text = re.sub(r"\{\{[Ii]nvestigator\|([^}|]+)(?:\|([^}]+))?\}\}", lambda m: m.group(2) or m.group(1), text)
    text = re.sub(r"\{\{[Aa]o\|([^}]+)\}\}", r"\1", text)
    text = re.sub(r"\{\{(?:Core Game|FL imagelink|MoM imagelink)\}\}", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"<br\s*/?>", " ", text)
    text = text.replace("'''", "").replace("''", "")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+:", ":", text)
    return text.strip()


def template(wikitext: str, name: str) -> dict[str, str]:
    """Read the key=value fields of the first `{{name ...}}` template on a page."""
    match = re.search(r"\{\{\s*(?:Template:)?" + re.escape(name) + r"\b", wikitext, re.IGNORECASE)
    if match is None:
        return {}
    depth = 1
    index = match.end()
    while index < len(wikitext) and depth:
        if wikitext[index : index + 2] == "{{":
            depth += 1
            index += 2
        elif wikitext[index : index + 2] == "}}":
            depth -= 1
            index += 2
        else:
            index += 1
    body = wikitext[match.end() : index - 2]
    fields: dict[str, str] = {}
    chunk: list[str] = []
    depth = 0
    for char in body:
        if char in "{[":
            depth += 1
        elif char in "}]":
            depth = max(0, depth - 1)
        if char == "|" and depth == 0:
            _store(fields, "".join(chunk))
            chunk = []
        else:
            chunk.append(char)
    _store(fields, "".join(chunk))
    return fields


def _store(fields: dict[str, str], chunk: str) -> None:
    if "=" in chunk:
        key, value = chunk.split("=", 1)
        fields[key.strip()] = value.strip()


def strip_leading_flavor(text: str) -> str:
    """Drop the trailing `[[File:...]]` caption wikitext leaves behind."""
    return re.sub(r"^(?:thumb\|\d+px\|[a-z]+\|)?", "", text).strip()


def is_core(value: str | None) -> bool:
    return bool(value) and "Core Game" in value


def is_core_card(fields: dict[str, str]) -> bool:
    """Core cards mark the set per variant (`Expansion 1`, `Expansion 2`, ...)."""
    seen = False
    for key, value in fields.items():
        if key.lower().startswith("expansion"):
            seen = True
            if is_core(value):
                return True
    return not seen


# Wiki page titles that differ from the name the JSON data uses.
WIKI_ALIASES = {
    "Mi-Go": "Mi-go",
    "Chthonian": "Cthonian",
    "Silver Twilight Researcher": "Lodge Researcher",
    "Shrivelling": "Shriveling",
    "The Pallid Mask": "Pallid Mask",
}


# --- the wiki model -------------------------------------------------------------------


class Wiki:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.mythos = self._collect("Mythos", "Name")
        self.assets = self._collect("Assets", "Name")
        self.artifacts = self._collect("Artifact", "Name")
        self.spells = self._collect("Spells", "Name")
        self.conditions = self._collect("Conditions", "Name")
        self.monsters = self._collect("Monster", "Monster_Name")
        self.investigators = self._collect("Infobox Investigator", None)
        self.locations = self._collect("Infobox MapLocation", None)

    def _collect(self, template_name: str, name_field: str | None) -> dict[str, tuple[str, dict[str, str]]]:
        found: dict[str, tuple[str, dict[str, str]]] = {}
        core_only = template_name not in ("Infobox Investigator", "Infobox MapLocation")
        for title, wikitext in self.pages.items():
            if not re.search(r"\{\{\s*(?:Template:)?" + re.escape(template_name) + r"\b", wikitext, re.IGNORECASE):
                continue
            fields = template(wikitext, template_name)
            if core_only and not is_core_card(fields):
                continue
            name = plain(fields.get(name_field)) if name_field else title
            found[name or title] = (title, fields)
        return found

    def lookup(self, table: dict[str, tuple[str, dict[str, str]]], name: str) -> tuple[str, dict[str, str]] | None:
        for candidate in (name, WIKI_ALIASES.get(name, ""), name.removeprefix("The ")):
            if candidate and candidate in table:
                return table[candidate]
        return None

    def defeated(self, name: str) -> tuple[str, str]:
        """Return the health and sanity defeated-encounter text for an investigator."""
        wikitext = self.pages.get("Defeated", "")
        first = name.split()[0]
        out = []
        for kind in ("Health", "Sanity"):
            match = re.search(
                rf'<section begin="{re.escape(first)} {kind}"\s*/>(.*?)<section end="\1"\s*/>',
                wikitext,
                re.DOTALL,
            )
            out.append(plain(match.group(1)) if match else "")
        return out[0], out[1]


# --- report and apply -----------------------------------------------------------------


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def mythos_text(fields: dict[str, str]) -> str:
    effect = plain(fields.get("Effect")).removesuffix(" N/A").strip()
    reckoning = plain(fields.get("Reckoning")).strip()
    no_reckoning = ("", "N/A", "No", "None")
    parts = [part for part in (effect, "" if reckoning in no_reckoning else f"Reckoning: {reckoning}") if part]
    return " ".join(parts)


def asset_text(fields: dict[str, str]) -> str:
    effect = plain(fields.get("Card Effect") or fields.get("Effect")).strip()
    action = plain(fields.get("Action")).strip()
    reckoning = plain(fields.get("Reckoning")).strip()
    parts = [effect] if effect and effect != "N/A" else []
    if action and action != "N/A":
        parts.append(action if action.lower().startswith(("action:", "local action:")) else f"Action: {action}")
    if reckoning and reckoning not in ("N/A", "No", "None"):
        parts.append(f"Reckoning: {reckoning}")
    return " ".join(parts)


def condition_text(fields: dict[str, str]) -> str:
    effect = plain(fields.get("Effect")).strip()
    action_type = plain(fields.get("Action_Type")).strip() or "Action"
    action = plain(fields.get("Action")).strip()
    reckoning = plain(fields.get("Reckoning")).strip()
    parts = [effect] if effect and effect != "N/A" else []
    if action and action != "N/A":
        parts.append(f"{action_type}: {action}")
    if reckoning and reckoning not in ("N/A", "No", "None"):
        parts.append(f"Reckoning: {reckoning}")
    return " ".join(parts)


def monster_text(fields: dict[str, str]) -> str:
    ability = plain(fields.get("Special_Abilities")).strip()
    if ability in ("N/A", "None"):
        return ""
    return ability.replace("*", "").strip()


def _stat_modifier(test: str) -> int:
    match = re.search(r"([+-])\s*(\d+)", plain(test))
    if match is None:
        return 0
    return int(match.group(2)) * (-1 if match.group(1) == "-" else 1)


def _has_test(value: str) -> bool:
    return plain(value).strip().upper() != "N/A"


def _toughness(value: str) -> tuple[int, int]:
    text = value or ""
    if "NoInvestigators" in text or "investigators" in text:
        match = re.search(r"\+\s*(\d+)", text)
        return (int(match.group(1)) if match else 0), 1
    match = re.search(r"\d+", text)
    return (int(match.group(0)) if match else 1), 0


def apply_monster_stats(wiki: Wiki, apply: bool) -> int:
    """Write the horror/damage/toughness line and test booleans from the monster templates."""
    changes = 0
    records = load(DATA_DIR / "monsters.json")
    for record in records:
        entry = wiki.lookup(wiki.monsters, record["name"])
        if entry is None:
            continue
        _, fields = entry
        horror_test = _has_test(fields.get("horror_test", ""))
        damage_test = _has_test(fields.get("damage_test", ""))
        if "Varies" in fields.get("horror_value", "") or "Varies" in fields.get("toughness_value", ""):
            continue
        horror_value = plain(fields.get("horror_value", "0"))
        damage_value = plain(fields.get("damage_value", "0"))
        horror = int(re.search(r"\d+", horror_value).group(0)) if horror_test and re.search(r"\d+", horror_value) else 0
        damage = int(re.search(r"\d+", damage_value).group(0)) if damage_test and re.search(r"\d+", damage_value) else 0
        toughness, per_investigator = _toughness(fields.get("toughness_value", ""))
        new = {
            "horror": horror,
            "horror_mod": _stat_modifier(fields.get("horror_test", "")) if horror_test else 0,
            "horror_test": horror_test,
            "damage": damage,
            "fight_mod": _stat_modifier(fields.get("damage_test", "")) if damage_test else 0,
            "damage_test": damage_test,
            "toughness": toughness,
            "toughness_per_investigator": per_investigator,
        }
        delta = {key: value for key, value in new.items() if record.get(key) != value}
        if not delta:
            continue
        changes += 1
        print(f"  {record['id']}: {delta}")
        if apply:
            record.update(delta)
    if apply:
        save(DATA_DIR / "monsters.json", records)
    return changes


def rules_bullets(wikitext: str) -> list[str]:
    match = re.search(r"===\s*Gameplay\s*===\s*\n+(.*?)(?=\n====|\n===|\Z)", wikitext, re.DOTALL)
    if match is None:
        return []
    bullets = []
    for line in match.group(1).splitlines():
        line = line.strip()
        if line.startswith("*"):
            cleaned = plain(line.lstrip("*").strip())
            if cleaned:
                bullets.append(cleaned)
    return bullets


def description_of(wikitext: str, title: str) -> str:
    match = re.search(r"==\s*" + re.escape(title) + r"\s*==\s*\n+''(.+?)''", wikitext, re.IGNORECASE | re.DOTALL)
    if match is None:
        match = re.search(r"==\s*The [^\n=]+==\s*\n+''(.+?)''", wikitext, re.DOTALL)
    return plain(match.group(1)) if match else ""


def report_and_sync(wiki: Wiki, apply: bool, *, apply_stats: bool = False) -> int:
    changes = 0

    def update(where: str, record: dict[str, Any], key: str, value: str) -> None:
        nonlocal changes
        if not value or record.get(key) == value:
            return
        changes += 1
        print(f"  {where}: {key}")
        if record.get(key):
            print(f"    was: {record[key][:160]}")
        print(f"    new: {value[:160]}")
        if apply:
            record[key] = value

    print("== mythos.json ==")
    mythos = load(DATA_DIR / "mythos.json")
    for card in mythos:
        entry = wiki.lookup(wiki.mythos, card["name"])
        if entry is None:
            print(f"  [no wiki page] {card['id']} ({card['name']})")
            continue
        _, fields = entry
        update(card["id"], card, "flavor", plain(fields.get("Flavor")))
        update(card["id"], card, "text", mythos_text(fields))
        color = plain(fields.get("Color")).lower()
        if color in ("green", "yellow", "blue"):
            update(card["id"], card, "color", color)
        traits = [part.strip().lower() for part in plain(fields.get("Traits")).split(",") if part.strip()]
        traits = [part for part in traits if part in ("event", "ongoing", "rumor")]
        if traits and card.get("traits") != traits:
            changes += 1
            print(f"  {card['id']}: traits {card.get('traits')} -> {traits}")
            if apply:
                card["traits"] = traits
    if apply:
        save(DATA_DIR / "mythos.json", mythos)

    print("== assets, artifacts, spells, conditions, monsters ==")
    for filename, table, text_of in (
        ("assets.json", wiki.assets, asset_text),
        ("artifacts.json", wiki.artifacts, asset_text),
        ("spells.json", wiki.spells, asset_text),
        ("conditions.json", wiki.conditions, condition_text),
        ("monsters.json", wiki.monsters, monster_text),
    ):
        print(f"  -- {filename}")
        records = load(DATA_DIR / filename)
        for record in records:
            entry = wiki.lookup(table, record["name"])
            if entry is None:
                print(f"    [no wiki page] {record['id']} ({record['name']})")
                continue
            _, fields = entry
            update(record["id"], record, "text", text_of(fields))
            if "flavor" in record and "Flavor" not in fields:
                update(record["id"], record, "flavor", "")
        if apply:
            save(DATA_DIR / filename, records)

    if apply_stats:
        print("== monsters.json stats ==")
        changes += apply_monster_stats(wiki, apply or apply_stats)

    print("== investigators.json ==")
    investigators = load(DATA_DIR / "investigators.json")
    for record in investigators:
        entry = wiki.lookup(wiki.investigators, record["name"])
        if entry is None:
            print(f"  [no wiki page] {record['id']}")
            continue
        title, _ = entry
        wikitext = wiki.pages[title]
        quote = re.search(r"====\s*Quote\s*====\s*\n+(.+?)(?=\n=|\n====|\Z)", wikitext, re.DOTALL)
        bio = re.search(r"====\s*Bio\s*====\s*\n+(.+?)(?=\n=|\n====|\Z)", wikitext, re.DOTALL)
        update(record["id"], record, "quote", plain(quote.group(1)).strip('"') if quote else "")
        update(record["id"], record, "bio", plain(bio.group(1)) if bio else "")
        # Abilities are reported, not written: their English and this engine's effect
        # data disagree card by card, so changing the text alone would make it lie.
        abilities = _abilities(wikitext)
        if abilities:
            print(f"  {record['id']}: review abilities: {abilities}")
    if apply:
        save(DATA_DIR / "investigators.json", investigators)

    print("== old_ones.json ==")
    old_ones = load(DATA_DIR / "old_ones.json")
    for record in old_ones:
        wikitext = wiki.pages.get(record["name"])
        if wikitext is None:
            print(f"  [no wiki page] {record['id']}")
            continue
        update(record["id"], record, "description", description_of(wikitext, record["title"]))
        bullets = rules_bullets(wikitext)
        if bullets and record.get("rules_text") != bullets:
            changes += 1
            print(f"  {record['id']}: rules_text ({len(bullets)} lines)")
            if apply:
                record["rules_text"] = bullets
        awakening = template(wikitext, "AO Back")
        title = plain(awakening.get("Title"))
        flavor = plain(awakening.get("Flavor"))
        if title:
            joined = f"{title}{' ' if title.endswith('!') else '! '}{flavor}"
            update(record["id"], record["awakening"], "text", joined.strip())
    if apply:
        save(DATA_DIR / "old_ones.json", old_ones)

    print("== encounters (report only) ==")
    encounter_pages = (
        "General Encounter",
        "Location Encounter",
        "Expedition Encounters",
        "Other World Encounters",
        "Research Encounter",
        "Special Encounters",
    )
    core_entries = sum(
        wiki.pages.get(page, "").count("{{Core Game}}") for page in encounter_pages
    )
    encounter_files = sorted((DATA_DIR / "encounters").glob("*.json"))
    custom = sum(len(load(path)) for path in encounter_files)
    print(f"  wiki: {core_entries} Core Game encounter entries")
    print(f"  data: {custom} encounter cards across {len(encounter_files)} decks")
    print("  effects are engine data and are not rewritten from the wiki prose")

    print("== map.json (location action text) ==")
    map_data = load(DATA_DIR / "map.json")
    for location in map_data["locations"]:
        entry = wiki.lookup(wiki.locations, location["name"])
        if entry is None:
            continue
        _, fields = entry
        actions = plain(fields.get("actions"))
        if actions:
            update(location["id"], location, "text", actions)
    if apply:
        save(DATA_DIR / "map.json", map_data)

    return changes


def _abilities(wikitext: str) -> list[str]:
    match = re.search(r"===\s*Abilities\s*===\s*\n+(.*?)(?=\n===|\Z)", wikitext, re.DOTALL)
    if match is None:
        return []
    return [plain(line.lstrip("* ")) for line in match.group(1).splitlines() if line.strip().startswith("*")]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="rewrite the JSON prose fields")
    parser.add_argument("--apply-stats", action="store_true", help="rewrite the monster stat lines from the templates")
    parser.add_argument("--offline", action="store_true", help="reuse the cached wiki pages")
    args = parser.parse_args()
    pages = fetch_pages(offline=args.offline)
    wiki = Wiki(pages)
    changes = report_and_sync(wiki, apply=args.apply, apply_stats=args.apply_stats)
    verb = "changed" if args.apply else "would change"
    print(f"\n{verb} {changes} field(s). Cache: {CACHE_FILE}")


if __name__ == "__main__":
    main()
