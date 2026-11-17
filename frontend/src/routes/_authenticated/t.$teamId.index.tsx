import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { polls } from "@/lib/mock-backend";
import { useMe, useRestaurants, useTodayPoll } from "@/lib/team-data";
import { moveChoice, tally, toggleChoice } from "@/lib/scoring";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useFlip } from "@/hooks/use-flip";

const MAX_PICKS = 3;

export const Route = createFileRoute("/_authenticated/t/$teamId/")({
  head: () => ({ meta: [{ title: "Today's vote — Where Should We Eat?" }] }),
  component: TodayPage,
});

function TodayPage() {
  const { teamId } = Route.useParams();
  const qc = useQueryClient();
  const me = useMe();
  const today = useTodayPoll(teamId);
  const all = useRestaurants(teamId);
  const [selected, setSelected] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);

  const myBallot = today.data?.ballots.find((b) => b.user_id === me.data?.id);
  useEffect(() => { if (myBallot) setSelected(myBallot.choices); }, [myBallot?.submitted_at]); // eslint-disable-line react-hooks/exhaustive-deps

  const candidates = useMemo(() => {
    const ids = new Set(today.data?.candidateIds ?? []);
    return (all.data ?? []).filter((r) => ids.has(r.id));
  }, [all.data, today.data]);
  const byId = new Map(candidates.map((r) => [r.id, r]));
  const standings = useMemo(() => tally(candidates, today.data?.ballots ?? []), [candidates, today.data]);
  // Standings re-sort as votes come in; glide rows to their new place instead of jumping.
  const standingsRef = useFlip<HTMLUListElement>(standings.map((s) => s.restaurant_id).join());
  const choicesRef = useFlip<HTMLOListElement>(selected.join());

  if (today.isLoading || all.isLoading) return <div className="h-40 animate-pulse rounded-xl bg-muted" />;
  if (!today.data) return <p role="alert">Could not load today's poll.</p>;
  const { poll, ballots } = today.data;

  if (candidates.length === 0) {
    return (
      <div className="rounded-2xl border bg-card p-6">
        <p className="text-muted-foreground">No restaurants yet, so there's nothing to vote on.</p>
        <Button variant="pop" className="mt-4" asChild><Link to="/t/$teamId/restaurants" params={{ teamId }}>Add restaurants</Link></Button>
      </div>
    );
  }

  const open = poll.status === "open";
  const top = standings[0]?.score ?? 0;
  const needle = q.trim().toLowerCase();
  const shown = candidates.filter((r) => !needle || [r.name, r.cuisine, r.address].some((v) => v?.toLowerCase().includes(needle)));

  async function submit() {
    setBusy(true);
    try {
      await polls.submitBallot(poll.id, selected);
      qc.invalidateQueries({ queryKey: ["poll", teamId] });
      toast.success("Vote saved");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save vote");
    }
    setBusy(false);
  }

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <section className="space-y-4">
        <h2 className="text-xl font-bold">{open ? "Your top 3" : "Voting closed"}</h2>
        {/* Fixed slots: picking a restaurant fills a slot instead of inserting a row and pushing the list below it down. */}
        <ol ref={choicesRef} className="space-y-2" aria-label="Your ranking">
          {!open && selected.length === 0 && <li className="text-muted-foreground">You didn't vote today.</li>}
          {selected.map((id, i) => (
            <li key={id} data-flip-id={id} className="flex h-14 items-center gap-2 rounded-xl border border-primary/40 bg-card px-3 animate-in fade-in duration-200">
              <span className="w-6 font-bold">{i + 1}.</span>
              <span className="flex-1 truncate font-semibold">{byId.get(id)?.name ?? "Archived"}</span>
              {open && <>
                <Button size="sm" variant="ghost" aria-label="Move up" disabled={i === 0} onClick={() => setSelected(moveChoice(selected, i, -1))}>↑</Button>
                <Button size="sm" variant="ghost" aria-label="Move down" disabled={i === selected.length - 1} onClick={() => setSelected(moveChoice(selected, i, 1))}>↓</Button>
                <Button size="sm" variant="ghost" aria-label="Remove" onClick={() => setSelected(selected.filter((x) => x !== id))}>✕</Button>
              </>}
            </li>
          ))}
          {open && Array.from({ length: Math.max(0, MAX_PICKS - selected.length) }, (_, k) => {
            const n = selected.length + k + 1;
            return (
              <li key={`empty-${n}`} aria-hidden="true" className="flex h-14 items-center gap-2 rounded-xl border border-dashed px-3 text-muted-foreground">
                <span className="w-6 font-bold">{n}.</span>
                <span className="flex-1 text-sm">{selected.length === 0 && k === 0 ? "Tap restaurants below to rank them." : "Empty"}</span>
              </li>
            );
          })}
        </ol>
        {open && <Button variant="pop" size="xl" className="w-full" disabled={busy || selected.length === 0} onClick={submit}>{myBallot ? "Update vote" : "Submit vote"}</Button>}

        {open && <>
          <Input aria-label="Search restaurants" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} className="h-11" />
          <ul className="space-y-2">
            {shown.map((r) => {
              const rank = selected.indexOf(r.id);
              return (
                <li key={r.id}>
                  <button type="button" aria-pressed={rank >= 0}
                    onClick={() => {
                      const { next, full } = toggleChoice(selected, r.id);
                      if (full) toast.info("You can rank up to 3 — remove one first");
                      setSelected(next);
                    }}
                    className={`flex min-h-11 w-full items-center justify-between gap-3 rounded-xl border p-3 text-left transition-colors duration-150 ${rank >= 0 ? "border-primary bg-primary/10" : "bg-card hover:bg-muted/50"}`}>
                    <span><span className="font-semibold">{r.name}</span>{r.cuisine && <span className="text-sm text-muted-foreground"> · {r.cuisine}</span>}</span>
                    {/* Fixed-width badge slot so selecting doesn't reflow the row. */}
                    <span className="w-8 shrink-0 text-right font-bold">{rank >= 0 ? `#${rank + 1}` : ""}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </>}
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-bold">Standings <span className="text-sm font-normal text-muted-foreground">({ballots.length} voted)</span></h2>
        <ul ref={standingsRef} className="space-y-2">
          {standings.map((s) => (
            <li key={s.restaurant_id} data-flip-id={s.restaurant_id} className="rounded-xl border bg-card p-3">
              <div className="flex justify-between"><span className="font-semibold">{s.name}</span><span className="tabular-nums">{s.score} pts</span></div>
              <div className="mt-2 h-2 rounded bg-muted"><div className="h-2 rounded bg-primary transition-[width] duration-300 ease-out" style={{ width: `${top ? (s.score / top) * 100 : 0}%` }} /></div>
            </li>
          ))}
        </ul>
        {ballots.length > 0 && (
          <ul className="space-y-1 text-sm text-muted-foreground">
            {/* Alphabetical, so re-submitting a vote doesn't move that voter's line to the bottom. */}
            {[...ballots].sort((a, b) => a.display_name.localeCompare(b.display_name)).map((b) => (
              <li key={b.user_id}><strong>{b.display_name}</strong>: {b.choices.map((id) => byId.get(id)?.name ?? "?").join(" › ")}</li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
