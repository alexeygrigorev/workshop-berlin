import { allTimezones } from "@/lib/time";
export function TimezoneSelect({ value, onChange, id }: { value: string; onChange: (v: string) => void; id?: string }) {
  const zones = allTimezones();
  return (
    <select id={id} value={value} onChange={(e) => onChange(e.target.value)}
      className="h-11 w-full rounded-md border border-input bg-background px-3 text-sm">
      {!zones.includes(value) && <option value={value}>{value}</option>}
      {zones.map((z) => <option key={z} value={z}>{z.replace(/_/g, " ")}</option>)}
    </select>
  );
}
