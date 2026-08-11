// Mirrors profiles/*.yaml's real discipline keys/display names — there's
// no API endpoint to list disciplines (P10's spec doesn't include one),
// so this is hand-kept in sync with the backend's seeded profiles.
export const DISCIPLINES: { key: string; label: string }[] = [
  { key: "mechanical", label: "Mechanical Engineering" },
  { key: "civil", label: "Civil Engineering" },
  { key: "electrical", label: "Electrical Engineering" },
  { key: "electronics", label: "Electronics & Communication Engineering" },
  { key: "chemical", label: "Chemical Engineering" },
  { key: "computer_science", label: "Computer Science & Engineering" },
];
