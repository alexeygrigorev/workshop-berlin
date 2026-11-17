import { Link } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { useFlip } from "@/hooks/use-flip";
import { cn } from "@/lib/utils";
import type { Vote } from "./use-vote";

export const RANK_LABEL = ["1st", "2nd", "3rd"] as const;

/** Loading / error / empty states shared by every layout. Returns null when the poll is ready. */
export function VoteStatus({ v, teamId }: { v: Vote; teamId: string }) {
  if (v.status === "loading") return <div className="h-40 animate-pulse rounded-xl bg-muted" />;
  if (v.status === "error") return <p role="alert">Could not load today's poll.</p>;
  if (v.status === "empty") {
    return (
      <div className="rounded-2xl border bg-card p-6">
        <p className="text-muted-foreground">No restaurants yet, so there's nothing to vote on.</p>
        <Button variant="pop" className="mt-4" asChild><Link to="/t/$teamId/restaurants" params={{ teamId }}>Add restaurants</Link></Button>
      </div>
    );
  }
  return null;
}

/** One fixed-height line describing whether the shown ballot is saved. */
export function SaveState({ v, className }: { v: Vote; className?: string }) {
  const text = !v.open ? (v.hasBallot ? "Voting closed — your vote counted" : "Voting closed")
    : v.dirty ? (v.selected.length ? "Unsaved changes" : v.hasBallot ? "Unsaved: ballot cleared" : "Not voted yet · votes are visible to your team")
    : v.hasBallot ? "Saved ✓" : "Not voted yet · votes are visible to your team";
  return <p className={cn("h-5 truncate text-xs", v.dirty && v.open ? "font-semibold text-primary" : "text-muted-foreground", className)}>{text}</p>;
}

export function SaveButton({ v, className, size = "xl" }: { v: Vote; className?: string; size?: "xl" | "default" | "lg" }) {
  if (!v.open) return null;
  return (
    <Button variant="pop" size={size} className={className} disabled={v.busy || v.selected.length === 0 || !v.dirty} onClick={v.submit}>
      {v.hasBallot ? "Update vote" : "Submit vote"}
    </Button>
  );
}

/** Live standings with score bars; rows glide when the order changes. */
export function StandingsList({ v, limit, dense }: { v: Vote; limit?: number; dense?: boolean }) {
  const rows = limit ? v.standings.slice(0, limit) : v.standings;
  const ref = useFlip<HTMLOListElement>(rows.map((s) => s.restaurant_id).join());
  return (
    <ol ref={ref} className={dense ? "space-y-1" : "space-y-2"}>
      {rows.map((s, i) => (
        <li key={s.restaurant_id} data-flip-id={s.restaurant_id} className={cn("rounded-xl border bg-card", dense ? "px-3 py-2" : "p-3")}>
          <div className="flex items-baseline gap-2">
            <span className="w-5 shrink-0 text-sm font-bold text-muted-foreground tabular-nums">{i + 1}</span>
            <span className="flex-1 truncate font-semibold">{s.name}</span>
            {!dense && <span className="hidden text-xs text-muted-foreground tabular-nums sm:inline">{s.first}×1st · {s.second}×2nd · {s.third}×3rd</span>}
            <span className="w-14 shrink-0 text-right text-sm tabular-nums">{s.score} pts</span>
          </div>
          <div className={cn("rounded bg-muted", dense ? "mt-1 h-1.5" : "mt-2 h-2")}>
            <div className="h-full rounded bg-primary transition-[width] duration-300 ease-out" style={{ width: `${v.topScore ? (s.score / v.topScore) * 100 : 0}%` }} />
          </div>
        </li>
      ))}
    </ol>
  );
}

/** Named ballots, plus members who haven't voted yet. */
export function VotersList({ v, showPending = true }: { v: Vote; showPending?: boolean }) {
  return (
    <div className="space-y-3 text-sm">
      {v.voters.length === 0 && <p className="text-muted-foreground">No votes yet.</p>}
      <ul className="space-y-1">
        {v.voters.map((b) => (
          <li key={b.user_id} className="truncate">
            <strong>{b.display_name}</strong>{b.user_id === v.myId && " (you)"}
            <span className="text-muted-foreground">: {b.choices.map((id) => v.byId.get(id)?.name ?? "?").join(" › ")}</span>
          </li>
        ))}
      </ul>
      {showPending && v.notVoted.length > 0 && (
        <p className="text-muted-foreground">Not voted yet: {v.notVoted.map((m) => m.display_name).join(", ")}</p>
      )}
    </div>
  );
}
