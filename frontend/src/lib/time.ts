export function fmtTime(iso: string | Date, tz: string) {
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", timeZone: tz }).format(new Date(iso));
}
export function fmtDate(d: string, opts: Intl.DateTimeFormatOptions = { weekday: "short", day: "numeric", month: "short", year: "numeric" }) {
  return new Intl.DateTimeFormat(undefined, { ...opts, timeZone: "UTC" }).format(new Date(d + "T12:00:00Z"));
}
export function localWeekday(tz: string) {
  return new Intl.DateTimeFormat("en-US", { weekday: "short", timeZone: tz }).format(new Date());
}
export function nextOpeningLabel(tz: string, openTime: string) {
  const wd = localWeekday(tz);
  const day = wd === "Fri" || wd === "Sat" || wd === "Sun" ? "Monday" : "tomorrow";
  return `Next vote opens ${day} at ${openTime.slice(0, 5)}`;
}
export function guessTimezone() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Berlin"; } catch { return "Europe/Berlin"; }
}
export function allTimezones(): string[] {
  try { return (Intl as unknown as { supportedValuesOf: (k: string) => string[] }).supportedValuesOf("timeZone"); }
  catch { return ["Europe/Berlin", "Europe/London", "America/New_York", "America/Los_Angeles", "Asia/Tokyo", "UTC"]; }
}
export function countdown(ms: number) {
  if (ms <= 0) return "0:00";
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return h > 0 ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}:${String(sec).padStart(2, "0")}`;
}
