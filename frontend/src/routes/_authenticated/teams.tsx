import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { supabase } from "@/integrations/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Logo } from "@/components/app/Logo";
import { TimezoneSelect } from "@/components/app/TimezoneSelect";
import { guessTimezone } from "@/lib/time";

export const Route = createFileRoute("/_authenticated/teams")({
  head: () => ({ meta: [{ title: "Your teams — Where Should We Eat?" }, { name: "description", content: "Pick a team or create a new one." }] }),
  component: TeamsPage,
});

function TeamsPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const teams = useQuery({
    queryKey: ["my-teams"],
    queryFn: async () => {
      const { data: u } = await supabase.auth.getUser();
      const { data, error } = await supabase.from("team_members").select("role, teams(id, name, timezone)").eq("user_id", u.user!.id);
      if (error) throw error;
      return data;
    },
  });
  const [name, setName] = useState("");
  const [tz, setTz] = useState(guessTimezone());
  const [office, setOffice] = useState("");
  const [busy, setBusy] = useState(false);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    const { data, error } = await supabase.rpc("create_team", { _name: name, _timezone: tz, _office: office || undefined });
    setBusy(false);
    if (error) return toast.error(error.message);
    qc.invalidateQueries({ queryKey: ["my-teams"] });
    navigate({ to: "/t/$teamId/restaurants", params: { teamId: data as string }, search: { onboarding: true } });
  }

  async function signOut() {
    await qc.cancelQueries(); qc.clear();
    await supabase.auth.signOut();
    navigate({ to: "/auth", replace: true });
  }

  return (
    <main className="mx-auto max-w-2xl px-5 py-6">
      <header className="flex items-center justify-between"><Logo /><Button variant="ghost" onClick={signOut}>Sign out</Button></header>
      <h1 className="mt-10 text-4xl font-extrabold">Your teams</h1>
      <div className="mt-6 space-y-3">
        {teams.isLoading && <div className="h-16 animate-pulse rounded-xl bg-muted" />}
        {teams.data?.length === 0 && <p className="text-muted-foreground">You're not in a team yet. Create one below, or open an invite link from a coworker.</p>}
        {teams.data?.map((m) => m.teams && (
          <Link key={m.teams.id} to="/t/$teamId" params={{ teamId: m.teams.id }}
            className="flex items-center justify-between rounded-xl border bg-card p-4 shadow-card transition-transform hover:-translate-y-0.5">
            <span className="font-display text-lg font-bold">{m.teams.name}</span>
            <span className="text-sm text-muted-foreground">{m.role === "admin" ? "Admin · " : ""}{m.teams.timezone}</span>
          </Link>
        ))}
      </div>
      <form onSubmit={create} className="mt-10 space-y-4 rounded-2xl border bg-card p-6 shadow-card">
        <h2 className="text-2xl font-bold">Create a team</h2>
        <div className="space-y-2"><Label htmlFor="tn">Team name</Label><Input id="tn" required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} placeholder="Design crew" className="h-11" /></div>
        <div className="space-y-2"><Label>Timezone</Label><TimezoneSelect value={tz} onChange={setTz} /></div>
        <div className="space-y-2"><Label htmlFor="of">Office location (optional)</Label><Input id="of" value={office} onChange={(e) => setOffice(e.target.value)} placeholder="Berlin Mitte" className="h-11" /></div>
        <Button type="submit" variant="pop" size="xl" disabled={busy}>{busy ? "Creating…" : "Create team"}</Button>
      </form>
    </main>
  );
}
