import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Restaurant } from "@/lib/team-data";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { restaurants as api } from "@/lib/mock-backend";
import { useRestaurants, useTeam } from "@/lib/team-data";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export const Route = createFileRoute("/_authenticated/t/$teamId/restaurants")({
  validateSearch: (s: Record<string, unknown>): { onboarding?: boolean } =>
    s["onboarding"] === true || s["onboarding"] === "true" ? { onboarding: true } : {},
  head: () => ({ meta: [{ title: "Restaurants — Where Should We Eat?" }] }),
  component: RestaurantsPage,
});

function RestaurantsPage() {
  const { teamId } = Route.useParams();
  const { onboarding } = Route.useSearch();
  const qc = useQueryClient();
  const team = useTeam(teamId);
  const list = useRestaurants(teamId);
  const [q, setQ] = useState("");
  const [form, setForm] = useState({ name: "", cuisine: "", address: "", website_url: "", map_url: "", notes: "" });
  const [busy, setBusy] = useState(false);
  const [justAdded, setJustAdded] = useState<string | null>(null);

  // Stable order for this visit: rows keep the position they first appeared in (alphabetical on load),
  // and restaurants added now go to the end instead of being spliced into the middle of the list.
  const seen = useRef(new Map<string, number>());
  const ordered = useMemo(() => {
    const rows = list.data ?? [];
    for (const r of rows) if (!seen.current.has(r.id)) seen.current.set(r.id, seen.current.size);
    return [...rows].sort((a, b) => seen.current.get(a.id)! - seen.current.get(b.id)!);
  }, [list.data]);

  useEffect(() => {
    if (!justAdded) return;
    const t = window.setTimeout(() => setJustAdded(null), 1600);
    return () => window.clearTimeout(t);
  }, [justAdded]);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const row = await api.add(teamId, {
        name: form.name.trim(),
        cuisine: form.cuisine.trim() || null, address: form.address.trim() || null,
        website_url: form.website_url.trim() || null, map_url: form.map_url.trim() || null, notes: form.notes.trim() || null,
      });
      setForm({ name: "", cuisine: "", address: "", website_url: "", map_url: "", notes: "" });
      // Show it right away (no wait for the refetch) and highlight it where it lands.
      qc.setQueryData<Restaurant[]>(["restaurants", teamId], (old) => (old ? [...old.filter((x) => x.id !== row.id), row] : old));
      setJustAdded(row.id);
      qc.invalidateQueries({ queryKey: ["restaurants", teamId] });
      toast.success("Restaurant added");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not add restaurant");
    }
    setBusy(false);
  }

  async function archive(id: string, name: string) {
    if (!window.confirm(`Archive ${name}? It won't appear in future polls.`)) return;
    // Optimistic: drop the row immediately rather than after the round-trip.
    const key = ["restaurants", teamId];
    const prev = qc.getQueryData<Restaurant[]>(key);
    qc.setQueryData<Restaurant[]>(key, (old) => old?.map((r) => (r.id === id ? { ...r, archived_at: new Date().toISOString() } : r)));
    try {
      await api.setArchived(id, true);
    } catch (err) {
      qc.setQueryData(key, prev);
      toast.error(err instanceof Error ? err.message : "Could not archive restaurant");
    }
    qc.invalidateQueries({ queryKey: key });
  }

  async function copyInvite() {
    if (!team.data) return;
    const url = `${window.location.origin}/join/${team.data.invite_token}`;
    try { await navigator.clipboard.writeText(url); toast.success("Invite link copied"); }
    catch { toast.error("Could not copy — " + url); }
  }

  const needle = q.trim().toLowerCase();
  const active = ordered.filter((r) => !r.archived_at)
    .filter((r) => !needle || [r.name, r.cuisine, r.address].some((v) => v?.toLowerCase().includes(needle)));

  return (
    <div className="space-y-6">
      {onboarding && (
        <section className="rounded-2xl border bg-card p-5 shadow-card">
          <h2 className="text-xl font-bold">Your team is ready 🎉</h2>
          <p className="mt-1 text-muted-foreground">Add a few restaurants your team likes, then invite coworkers. You can skip this and add them later.</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button variant="pop" onClick={copyInvite}>Copy invite link</Button>
            <Button variant="ghost" asChild><Link to="/t/$teamId" params={{ teamId }}>Skip for now</Link></Button>
          </div>
        </section>
      )}

      <form onSubmit={add} className="space-y-3 rounded-2xl border bg-card p-5 shadow-card">
        <h2 className="text-xl font-bold">Add a restaurant</h2>
        <div className="space-y-2"><Label htmlFor="rn">Name</Label><Input id="rn" required maxLength={120} value={form.name} onChange={set("name")} className="h-11" /></div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-2"><Label htmlFor="rc">Cuisine</Label><Input id="rc" value={form.cuisine} onChange={set("cuisine")} className="h-11" /></div>
          <div className="space-y-2"><Label htmlFor="ra">Address</Label><Input id="ra" value={form.address} onChange={set("address")} className="h-11" /></div>
          <div className="space-y-2"><Label htmlFor="rw">Website</Label><Input id="rw" type="url" value={form.website_url} onChange={set("website_url")} placeholder="https://" className="h-11" /></div>
          <div className="space-y-2"><Label htmlFor="rm">Map link</Label><Input id="rm" type="url" value={form.map_url} onChange={set("map_url")} placeholder="https://" className="h-11" /></div>
        </div>
        <div className="space-y-2"><Label htmlFor="rt">Notes</Label><Input id="rt" value={form.notes} onChange={set("notes")} className="h-11" /></div>
        <Button type="submit" variant="pop" disabled={busy} className="min-w-36">{busy ? "Adding…" : "Add restaurant"}</Button>
      </form>

      <section>
        <Input aria-label="Search restaurants" placeholder="Search name, cuisine, address" value={q} onChange={(e) => setQ(e.target.value)} className="h-11" />
        <ul className="mt-3 space-y-2">
          {list.isLoading && <li className="h-14 animate-pulse rounded-xl bg-muted" />}
          {!list.isLoading && active.length === 0 && (
            <li className="text-muted-foreground">{needle ? "No matches." : "No restaurants yet. Add your first one above — voting needs at least one."}</li>
          )}
          {active.map((r) => (
            <li key={r.id} className={`flex items-center justify-between gap-3 rounded-xl border p-4 transition-colors duration-700 ${r.id === justAdded ? "border-primary bg-primary/10 animate-in fade-in slide-in-from-bottom-1": "bg-card"}`}>
              <div className="min-w-0">
                <p className="font-semibold">{r.name}</p>
                <p className="truncate text-sm text-muted-foreground">{[r.cuisine, r.address].filter(Boolean).join(" · ")}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2 text-sm">
                {r.website_url && <a href={r.website_url} target="_blank" rel="noreferrer" className="underline">Website</a>}
                {r.map_url && <a href={r.map_url} target="_blank" rel="noreferrer" className="underline">Map</a>}
                <Button variant="ghost" size="sm" onClick={() => archive(r.id, r.name)}>Archive</Button>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
