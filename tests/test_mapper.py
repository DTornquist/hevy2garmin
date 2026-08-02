"""Tests for exercise mapper."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from hevy2garmin.mapper import (
    HEVY_TO_GARMIN,
    _UNKNOWN_CATEGORY,
    lookup_exercise,
    save_custom_mapping,
    _custom_mappings,
    _ensure_custom_loaded,
)


class TestLookupBuiltIn:
    def test_known_exercise(self) -> None:
        cat, subcat, name = lookup_exercise("Bench Press (Barbell)")
        assert cat == 0
        assert subcat == 1
        assert name == "Bench Press (Barbell)"

    def test_squat(self) -> None:
        cat, subcat, name = lookup_exercise("Squat (Barbell)")
        assert cat == 28
        assert name == "Squat (Barbell)"

    def test_unknown_exercise(self) -> None:
        cat, subcat, name = lookup_exercise("Made Up Exercise 12345")
        assert cat == _UNKNOWN_CATEGORY
        assert subcat == 0
        assert name == "Made Up Exercise 12345"

    def test_empty_string(self) -> None:
        cat, subcat, name = lookup_exercise("")
        assert cat == _UNKNOWN_CATEGORY
        assert name == ""

    def test_mapping_count_minimum(self) -> None:
        assert len(HEVY_TO_GARMIN) >= 400

    def test_preserves_original_name(self) -> None:
        _, _, name = lookup_exercise("Deadlift (Barbell)")
        assert name == "Deadlift (Barbell)"


class TestCustomMappings:
    def test_custom_overrides_builtin(self, tmp_path: Path) -> None:
        mappings_file = tmp_path / "custom_mappings.json"
        mappings_file.write_text(json.dumps({"Bench Press (Barbell)": [99, 88]}))

        # Reset custom state
        _custom_mappings.clear()
        import hevy2garmin.mapper as m
        m._custom_loaded = False

        with patch.object(Path, "expanduser", return_value=mappings_file):
            with patch("hevy2garmin.mapper._custom_loaded", False):
                # Force reload
                m._custom_loaded = False
                m._custom_mappings.clear()
                m._custom_mappings["Bench Press (Barbell)"] = (99, 88)
                cat, subcat, _ = lookup_exercise("Bench Press (Barbell)")
                assert cat == 99
                assert subcat == 88

        # Cleanup
        m._custom_mappings.clear()

    def test_custom_does_not_affect_other_exercises(self) -> None:
        import hevy2garmin.mapper as m
        m._custom_mappings["Only This One"] = (1, 2)
        cat, _, _ = lookup_exercise("Squat (Barbell)")
        assert cat == 28  # unchanged
        m._custom_mappings.clear()

    def test_save_custom_mapping_in_memory(self) -> None:
        import hevy2garmin.mapper as m
        m._custom_mappings["Test Exercise"] = (5, 10)
        cat, subcat, _ = lookup_exercise("Test Exercise")
        assert cat == 5
        assert subcat == 10
        m._custom_mappings.clear()

    def test_missing_custom_file_no_crash(self) -> None:
        import hevy2garmin.mapper as m
        m._custom_loaded = False
        m._custom_mappings.clear()
        # Should not crash when file doesn't exist
        _ensure_custom_loaded()


class TestSaveCustomMappingCloud:
    """save_custom_mapping must write to the DB on cloud (#142, #145).

    The old file-only write 500'd on Vercel's read-only filesystem, so custom
    mappings silently failed to persist (u/Zephyro7, u/fastcoconut).
    """

    def test_writes_to_db_on_cloud(self) -> None:
        from unittest.mock import MagicMock
        import hevy2garmin.mapper as m
        m._custom_mappings.clear()
        fake_db = MagicMock()
        with patch("hevy2garmin.db.get_database_url", return_value="postgresql://x"), \
             patch("hevy2garmin.db.get_db", return_value=fake_db):
            save_custom_mapping("Agachamento Búlgaro", 28, 9)
        fake_db.save_custom_mapping.assert_called_once_with("Agachamento Búlgaro", 28, 9)
        assert m._custom_mappings["Agachamento Búlgaro"] == (28, 9)
        m._custom_mappings.clear()

    def test_does_not_touch_filesystem_on_cloud(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock
        import hevy2garmin.mapper as m
        m._custom_mappings.clear()
        target = tmp_path / "custom_mappings.json"
        with patch("hevy2garmin.db.get_database_url", return_value="postgresql://x"), \
             patch("hevy2garmin.db.get_db", return_value=MagicMock()), \
             patch.object(Path, "expanduser", return_value=target):
            save_custom_mapping("Foo (Bar)", 1, 2)
        assert not target.exists()  # DB path used, no file written
        m._custom_mappings.clear()

    def test_falls_back_to_file_when_local(self, tmp_path: Path) -> None:
        import hevy2garmin.mapper as m
        m._custom_mappings.clear()
        target = tmp_path / "custom_mappings.json"
        with patch("hevy2garmin.db.get_database_url", return_value=None), \
             patch.object(Path, "expanduser", return_value=target):
            save_custom_mapping("Foo (Bar)", 12, 34)
        assert json.loads(target.read_text())["Foo (Bar)"] == [12, 34]
        assert m._custom_mappings["Foo (Bar)"] == (12, 34)
        m._custom_mappings.clear()


class TestNoDuplicateKeys:
    """A repeated key in the table literal is invisible: Python keeps the last
    one, so an exact FIT mapping can be silently replaced by an approximation
    added later under a different category heading."""

    def test_table_has_no_repeated_keys(self) -> None:
        import collections
        import re

        source = Path(__file__).parent.parent / "src" / "hevy2garmin" / "mapper.py"
        table = source.read_text().split("HEVY_TO_GARMIN", 1)[1]
        keys = re.findall(r'^\s{4}"([^"]+)":\s*\(', table, re.M)
        repeated = [k for k, n in collections.Counter(keys).items() if n > 1]
        assert not repeated, f"exercise defined more than once: {repeated}"

    def test_overhead_dumbbell_lunge_is_a_lunge(self) -> None:
        """It has a LUNGE mapping, so the later CARRY entry must not win."""
        from hevy2garmin.merge import _category_to_string

        cat, sub, _ = lookup_exercise("Overhead Dumbbell Lunge")
        assert _category_to_string(cat) == "LUNGE", (cat, sub)


class TestGenericSubcategory:
    """Subcategory 0 is a real exercise, not a "no specific exercise" marker.

    FIT's unset value is 65535. An entry meant to say "this category, nothing
    more specific" that uses 0 instead resolves to whatever exercise happens to
    be first in that category — cardio/0 is BOB_AND_WEAVE_CIRCLE, so Swimming
    uploaded to Garmin under that name.
    """

    def test_entries_documented_as_generic_use_the_sentinel(self) -> None:
        import re

        source = Path(__file__).parent.parent / "src" / "hevy2garmin" / "mapper.py"
        table = source.read_text().split("HEVY_TO_GARMIN", 1)[1]
        wrong = re.findall(
            r'^\s{4}"([^"]+)":\s+\(\d+, 0\),\s+#.*generic.*$', table, re.M
        )
        assert not wrong, f"'generic' entries using subcategory 0 instead of 65535: {wrong}"

    def test_swimming_is_not_a_boxing_drill(self) -> None:
        from hevy2garmin.merge import _category_to_string, _exercise_to_string

        cat, sub, _ = lookup_exercise("Swimming")
        assert _category_to_string(cat) == "CARDIO"
        assert _exercise_to_string(cat, sub) != "BOB_AND_WEAVE_CIRCLE"


class TestPallofPress:
    def test_hevy_spelling_resolves(self) -> None:
        """Hevy's catalog spells it "Pallof" (one l), which had no entry."""
        from hevy2garmin.merge import _exercise_to_string

        cat, sub, _ = lookup_exercise("Cable Core Pallof Press")
        assert _exercise_to_string(cat, sub) == "CABLE_CORE_PRESS"

    def test_old_spelling_still_resolves(self) -> None:
        """The previous misspelling stays mapped so older data keeps working."""
        from hevy2garmin.merge import _exercise_to_string

        cat, sub, _ = lookup_exercise("Cable Core Palloff Press")
        assert _exercise_to_string(cat, sub) == "CABLE_CORE_PRESS"


class TestValidCategories:
    """Bug B: some mappings used FIT categories (33-52) the installed fit_tool
    doesn't implement, so they silently fell back to TOTAL_BODY instead of their
    real category."""

    def test_every_mapped_category_is_valid(self) -> None:
        """Every built-in mapping must use a real FIT ExerciseCategory (0-32) or
        the UNKNOWN sentinel — an out-of-range category resolves to 'UNKNOWN' and
        would silently become TOTAL_BODY."""
        from hevy2garmin.merge import _category_to_string
        bad = {
            name: (c, s)
            for name, (c, s) in HEVY_TO_GARMIN.items()
            if c != _UNKNOWN_CATEGORY and _category_to_string(c) == "UNKNOWN"
        }
        assert not bad, f"mappings with invalid (out-of-range) categories: {bad}"

    def test_cardio_machines_map_to_cardio(self) -> None:
        """Cardio machines resolve to the CARDIO category, not the TOTAL_BODY
        fallback they hit before."""
        from hevy2garmin.merge import _category_to_string
        for name in ("Cycling", "Treadmill", "Elliptical Trainer", "Rowing Machine"):
            cat, sub, _ = lookup_exercise(name)
            assert _category_to_string(cat) == "CARDIO", name

    def test_dumbbell_row_resolves_to_real_subcategory(self) -> None:
        """Chest Supported Incline Row (Dumbbell) now resolves to a real Row
        subcategory name instead of a broken out-of-range sub."""
        from hevy2garmin.merge import _exercise_to_string
        cat, sub, _ = lookup_exercise("Chest Supported Incline Row (Dumbbell)")
        assert _exercise_to_string(cat, sub) == "DUMBBELL_ROW"


class TestTemplateIdDoesNotOverrideTheTable:
    """TEMPLATE_TO_GARMIN is generated from HEVY_TO_GARMIN and goes stale.

    While it was consulted first, every fix to the table was reverted for any
    workout carrying a template id — which is every workout the Hevy API
    returns. The generated copy still holds categories the table's own
    validity test forbids.
    """

    def test_template_map_categories_are_valid(self) -> None:
        from hevy2garmin.merge import _category_to_string
        from hevy2garmin.template_map import TEMPLATE_TO_GARMIN

        bad = {
            tid: (c, s)
            for tid, (c, s) in TEMPLATE_TO_GARMIN.items()
            if c != _UNKNOWN_CATEGORY and _category_to_string(c) == "UNKNOWN"
        }
        assert not bad, f"template ids with invalid categories: {bad}"

    def test_cardio_machines_map_to_cardio_with_a_template_id(self) -> None:
        """The same guarantee as TestValidCategories, on the path really used."""
        import re

        from hevy2garmin.merge import _category_to_string
        from hevy2garmin.template_map import TEMPLATE_TO_GARMIN

        source = (
            Path(__file__).parent.parent / "src" / "hevy2garmin" / "template_map.py"
        ).read_text()
        for name in ("Cycling", "Treadmill", "Elliptical Trainer", "Rowing Machine"):
            m = re.search(rf'"([0-9A-F]+)": \([\d, ]+\),\s+# {re.escape(name)}$', source, re.M)
            assert m, f"no template id found for {name}"
            tid = m.group(1)
            assert tid in TEMPLATE_TO_GARMIN
            cat, sub, _ = lookup_exercise(name, template_id=tid)
            assert _category_to_string(cat) == "CARDIO", (name, cat, sub)

    def test_table_wins_over_a_stale_template_entry(self) -> None:
        from hevy2garmin.template_map import TEMPLATE_TO_GARMIN

        tid = next(iter(TEMPLATE_TO_GARMIN))
        with patch.dict(TEMPLATE_TO_GARMIN, {tid: (99, 99)}):
            cat, sub, _ = lookup_exercise("Bench Press (Barbell)", template_id=tid)
            assert (cat, sub) == HEVY_TO_GARMIN["Bench Press (Barbell)"]

    def test_template_id_still_resolves_names_not_in_the_table(self) -> None:
        """The #173 non-English case must keep working."""
        from hevy2garmin.template_map import TEMPLATE_TO_GARMIN

        tid = next(iter(TEMPLATE_TO_GARMIN))
        cat, sub, name = lookup_exercise("Agachamento Búlgaro", template_id=tid)
        assert (cat, sub) == TEMPLATE_TO_GARMIN[tid]
        assert name == "Agachamento Búlgaro"


class TestGeneratedTemplateMapIsCurrent:
    """`template_map.py` is generated from HEVY_TO_GARMIN and can go stale.

    `lookup_exercise` resolves the English name before the template id, so a
    stale generated entry is invisible to an English-speaking user. Non-English
    workouts have no English name to match and resolve through the id, so drift
    hands exactly those users the pre-fix pair — which is how the #273 fix
    reached English names only.

    Regenerating needs the Hevy API; this check does not, because every
    generated line carries its source title in a comment.
    """

    def test_generated_map_matches_the_table(self) -> None:
        import importlib.util

        script = Path(__file__).parent.parent / "scripts" / "gen_template_map.py"
        spec = importlib.util.spec_from_file_location("gen_template_map", script)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert module.check() == 0, (
            "template_map.py is out of step with HEVY_TO_GARMIN — see the report "
            "above. Re-run scripts/gen_template_map.py, or update both files in "
            "the same commit."
        )
