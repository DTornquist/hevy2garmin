import { NextResponse } from "next/server";
import { CATEGORY_NAMES } from "@/lib/garmin-categories";

/**
 * GET /api/garmin-categories
 *
 * Returns the Garmin FIT exercise category id → name map used by the mapping
 * UI. The hevy2garmin npm package's exercise-map exports the numeric (category,
 * subcategory) pairs but NOT the category *names*, so the map lives in
 * lib/garmin-categories.ts, mirroring the Python dashboard's
 * `server.py::_get_cat_names()` — the source of the original route.
 */
export function GET() {
  return NextResponse.json(CATEGORY_NAMES);
}
