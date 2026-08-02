#!/usr/bin/env python3
"""Audit HEVY_TO_GARMIN exercise mappings against ground truth.

Two ground-truth sources are used:

* **Garmin / FIT** — the official ``exercise_category`` enum plus the
  per-category ``*_exercise_name`` tables, exported from the ``garmin-fit-sdk``
  package into ``fit_exercise_catalog.json`` (committed next to this script, so
  the audit runs without the SDK installed). Regenerate the export with
  ``--regenerate-catalog`` after installing the SDK via the ``audit`` extra
  (``pip install -e ".[audit]"``); a cloned SDK on ``PYTHONPATH`` also works.
  NB: the runtime ``fit-tool`` dependency carries
  a much older profile (categories capped at 32) and must NOT be used as the
  reference — it reports false "invalid" hits for every cardio-machine entry.

* **Hevy** — the canonical exercise titles from ``GET /v1/exercise_templates``,
  fetched live only when ``HEVY_API_KEY`` is set (Hevy Pro). Skipped otherwise.

Checks performed:
  1. invalid category / subcategory — the (cat, sub) pair does not exist in the
     current FIT profile, so Garmin renders it wrong or blank.
  2. comment vs reality — the inline ``# category / name`` comment names a
     different exercise than the (cat, sub) actually resolves to (stale docs;
     a few are genuinely the wrong number, e.g. a "generic" fallback to subcat
     0, which is always a *specific* named exercise, never generic).
  3. [Hevy] mapper keys that match no current Hevy title — typos like the
     "Cable Core Palloff Press" double-f that silently never matched.
  4. [Hevy] Hevy exercises with no mapping yet — the real unmapped backlog.

Usage:
  python scripts/audit_mappings.py                     # FIT audit (+ Hevy if key set)
  HEVY_API_KEY=... python scripts/audit_mappings.py    # include Hevy cross-check
  pip install -e ".[audit]" && python scripts/audit_mappings.py --regenerate-catalog
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CATALOG = HERE / "fit_exercise_catalog.json"
MAPPER = REPO / "src" / "hevy2garmin" / "mapper.py"

sys.path.insert(0, str(REPO / "src"))


def load_catalog() -> tuple[dict, dict[int, str], dict[int, dict[int, str]]]:
    data = json.loads(CATALOG.read_text())
    cats = {int(k): v for k, v in data["categories"].items()}
    names = {
        int(cv): {int(sv): sn for sv, sn in subs.items()}
        for cv, subs in data["exercise_names"].items()
    }
    return data.get("_provenance", {}), cats, names


def regenerate_catalog() -> None:
    try:
        import importlib.metadata as md

        import garmin_fit_sdk
        from garmin_fit_sdk import Profile
    except ImportError:
        sys.exit(
            "garmin-fit-sdk not importable. Run `pip install garmin-fit-sdk` or "
            "put the cloned SDK on PYTHONPATH, then retry --regenerate-catalog."
        )
    types = Profile["types"]
    cat_table = {k: v for k, v in types["exercise_category"].items() if isinstance(k, int)}
    names: dict[int, dict[int, str]] = {}
    for cval, cname in cat_table.items():
        tab = types.get(f"{cname}_exercise_name")
        if tab:
            names[cval] = {k: v for k, v in tab.items() if isinstance(k, int)}
    ver = getattr(garmin_fit_sdk, "__version__", None)
    if not ver:
        try:
            ver = md.version("garmin-fit-sdk")
        except Exception:
            ver = "unknown"
    out = {
        "_provenance": {"source": "garmin-fit-sdk", "version": ver},
        "categories": {str(k): v for k, v in cat_table.items()},
        "exercise_names": {
            str(cv): {str(sv): sn for sv, sn in subs.items()} for cv, subs in names.items()
        },
    }
    CATALOG.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    total = sum(len(s) for s in names.values())
    print(f"Wrote {CATALOG.name}: {len(cat_table)} categories, {total} names (SDK {ver})")


def parse_comments() -> dict[str, str]:
    src = MAPPER.read_text()
    rx = re.compile(
        r'^\s*"(?P<key>(?:[^"\\]|\\.)*)":\s*\(\d+,\s*\d+\),\s*#\s*(?P<cmt>.*?)\s*$', re.M
    )
    return {m.group("key"): m.group("cmt") for m in rx.finditer(src)}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def audit_fit(cats: dict, names: dict, comments: dict) -> tuple:
    from hevy2garmin.mapper import HEVY_TO_GARMIN

    bad_cat, bad_sub, mismatch = [], [], []
    for key, (cat, sub) in HEVY_TO_GARMIN.items():
        if cat == 65534:  # intentional UNKNOWN sentinel
            continue
        cmt = comments.get(key, "")
        claimed = cmt.split("/", 1)[1].strip().split("(")[0].strip() if "/" in cmt else ""
        if cat not in cats:
            bad_cat.append((key, cat, sub, cmt))
            continue
        subs = names.get(cat)
        if not subs or sub not in subs:
            bad_sub.append((key, cat, sub, cats.get(cat, "?"), cmt))
            continue
        real = subs[sub]
        if claimed and _norm(claimed) != _norm(real):
            mismatch.append((key, cat, sub, cats[cat], real, claimed))
    return HEVY_TO_GARMIN, bad_cat, bad_sub, mismatch


def audit_hevy(mapper_keys: set[str]) -> tuple | None:
    if not os.environ.get("HEVY_API_KEY"):
        return None
    from hevy2garmin.hevy import HevyClient

    client = HevyClient()
    templates: list[dict] = []
    page = 1
    while True:
        data = client.get_exercise_templates(page=page, page_size=100)
        batch = data.get("exercise_templates", [])
        templates.extend(batch)
        if page >= data.get("page_count", page) or not batch:
            break
        page += 1
    titles = {t["title"] for t in templates if t.get("title")}
    custom = {t["title"] for t in templates if t.get("title") and t.get("is_custom")}
    return titles, sorted(titles - mapper_keys), sorted(mapper_keys - titles), custom


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit exercise mappings against ground truth.")
    ap.add_argument(
        "--regenerate-catalog",
        action="store_true",
        help="rebuild fit_exercise_catalog.json from garmin-fit-sdk and exit",
    )
    args = ap.parse_args()
    if args.regenerate_catalog:
        regenerate_catalog()
        return 0

    prov, cats, names = load_catalog()
    comments = parse_comments()
    mapping, bad_cat, bad_sub, mismatch = audit_fit(cats, names, comments)

    total_names = sum(len(s) for s in names.values())
    print(f"FIT ground truth: {prov.get('source')} {prov.get('version')} "
          f"({len(cats)} categories, {total_names} names)")
    print(f"Mapper entries: {len(mapping)}")
    print(f"  invalid category:    {len(bad_cat)}")
    print(f"  invalid subcategory: {len(bad_sub)}")
    print(f"  comment mismatch:    {len(mismatch)}")

    if bad_cat:
        print("\n== INVALID CATEGORY (renders wrong/blank in Garmin) ==")
        for key, cat, sub, cmt in bad_cat:
            print(f"  {key!r}: ({cat},{sub})  # {cmt}")
    if bad_sub:
        print("\n== INVALID SUBCATEGORY (renders wrong/blank in Garmin) ==")
        for key, cat, sub, cname, cmt in bad_sub:
            print(f"  {key!r}: ({cat},{sub}) cat={cname}  # {cmt}")
    if mismatch:
        print("\n== COMMENT vs ACTUAL FIT NAME ==")
        for key, cat, sub, cname, real, claimed in mismatch:
            print(f"  {key!r}: ({cat},{sub}) = {cname}/{real}  (comment: {claimed!r})")

    hevy = audit_hevy(set(mapping))
    if hevy is None:
        print("\nHevy catalog: skipped (set HEVY_API_KEY to enable)")
    else:
        titles, unmapped, ghosts, custom = hevy
        # Custom templates are user-specific; being unmapped is expected, not a gap.
        unmapped_default = [t for t in unmapped if t not in custom]
        unmapped_custom = [t for t in unmapped if t in custom]
        print(f"\nHevy catalog: {len(titles)} titles ({len(custom)} custom)")
        print(f"  unmapped default exercises:  {len(unmapped_default)}  (real coverage gap)")
        print(f"  unmapped custom exercises:   {len(unmapped_custom)}  (expected; user-specific)")
        print(f"  mapper keys not in Hevy:     {len(ghosts)}")
        if unmapped_default:
            print("\n== UNMAPPED DEFAULT HEVY EXERCISES (real gap) ==")
            for t in unmapped_default:
                print(f"  {t}")
        if unmapped_custom:
            print("\n== UNMAPPED CUSTOM HEVY EXERCISES (expected) ==")
            for t in unmapped_custom:
                print(f"  {t}")
        if ghosts:
            print("\n== MAPPER KEYS MATCHING NO HEVY TITLE (typos / renamed / removed) ==")
            for k in ghosts:
                print(f"  {k!r}")

    # Non-zero exit only for genuinely broken (cat, sub) pairs, so this can gate CI.
    return 1 if (bad_cat or bad_sub) else 0


if __name__ == "__main__":
    raise SystemExit(main())
