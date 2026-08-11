// Client-side mirror of the backend's largest-remainder scaling
// (selection.py::_scale_difficulty_mix) so presets stay exact sums.
function scaleMix(ratios: Record<string, number>, total: number): Record<string, number> {
  const keys = Object.keys(ratios);
  const sum = keys.reduce((s, k) => s + ratios[k], 0);
  const floors: Record<string, number> = {};
  for (const k of keys) floors[k] = Math.floor((ratios[k] / sum) * total);
  let remainder = total - keys.reduce((s, k) => s + floors[k], 0);
  const byRemainder = [...keys].sort(
    (a, b) => (ratios[b] / sum) * total - floors[b] - ((ratios[a] / sum) * total - floors[a])
  );
  for (const k of byRemainder) {
    if (remainder <= 0) break;
    floors[k] += 1;
    remainder -= 1;
  }
  return floors;
}

export type DifficultyPreset = "balanced" | "fundamentals" | "challenge";

export const DIFFICULTY_PRESETS: { value: DifficultyPreset; label: string }[] = [
  { value: "balanced", label: "Balanced" },
  { value: "fundamentals", label: "Emphasize fundamentals" },
  { value: "challenge", label: "Emphasize challenge" },
];

/** null means "use the backend's own default balanced scaling" — sent
 * as-is, not reproduced client-side, so the one canonical ratio lives in
 * one place (selection.py). */
export function difficultyMixFor(
  preset: DifficultyPreset,
  count: number
): Record<string, number> | null {
  if (preset === "balanced") return null;
  if (preset === "fundamentals") return scaleMix({ easy: 50, medium: 35, hard: 15 }, count);
  return scaleMix({ easy: 15, medium: 35, hard: 50 }, count);
}
