/**
 * Garmin FIT exercise category id → display name.
 *
 * Single source of truth shared by the /api/garmin-categories route and the
 * mappings page. Mirrors the canonical set the Python dashboard serves from
 * `src/hevy2garmin/server.py::_get_cat_names()`. Keep the two in sync.
 */
export const CATEGORY_NAMES: Record<string, string> = {
  "0": "Bench Press",
  "1": "Calf Raise",
  "2": "Cardio",
  "3": "Carry",
  "4": "Chop",
  "5": "Core",
  "6": "Crunch",
  "7": "Curl",
  "8": "Deadlift",
  "9": "Flye",
  "10": "Hip Raise",
  "11": "Hip Stability",
  "12": "Hip Swing",
  "13": "Hyperextension",
  "14": "Lateral Raise",
  "15": "Leg Curl",
  "16": "Leg Raise",
  "17": "Lunge",
  "18": "Olympic Lift",
  "19": "Plank",
  "20": "Plyo",
  "21": "Pull Up",
  "22": "Push Up",
  "23": "Row",
  "24": "Shoulder Press",
  "25": "Shoulder Stability",
  "26": "Shrug",
  "27": "Sit Up",
  "28": "Squat",
  "29": "Total Body",
  "30": "Triceps Extension",
  "31": "Warm Up",
  "32": "Run",
  "33": "Cycling",
  "36": "Yoga",
  "38": "Battle Ropes",
  "39": "Elliptical",
  "41": "Indoor Bike",
  "42": "Indoor Row",
  "47": "Stair Machine",
  "52": "Treadmill",
  "65534": "Unknown",
};

/** [{ id, name }] sorted by id — convenient for dropdowns. */
export const CATEGORY_OPTIONS: { id: number; name: string }[] = Object.entries(
  CATEGORY_NAMES,
)
  .map(([id, name]) => ({ id: Number(id), name }))
  .sort((a, b) => a.id - b.id);

/** Human-readable name for a category id (falls back to "Category N"). */
export function categoryName(id: number): string {
  return CATEGORY_NAMES[String(id)] ?? `Category ${id}`;
}
