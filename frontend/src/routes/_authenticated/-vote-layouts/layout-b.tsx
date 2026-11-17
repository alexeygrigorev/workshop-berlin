import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { RANK_LABEL, SaveButton, SaveState, StandingsList, VotersList } from "./shared";
import type { Vote } from "./use-vote";

/**
 * Layout B — "Tap-to-rank cards".
 * A compact grid of restaurant cards. Tapping a card stamps the next rank on the card itself
 * (no separate tray that grows); a small ▲ on a ranked card bumps it up one place.
 * Standings show as a fixed three-slot podium with everything else in a collapsible below.
 */
export function LayoutB({ v }: { v: Vote }) {
  const [more, setMore] = useState(false);
  const podium = v.standings.slice(0, 3);

  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <div className="flex h-12 items-center gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="text-xl font-bold leading-tight">{v.open ? "Tap in order of preference" : "Voting closed"}</h2>
            <SaveState v={v} />
          </div>
          {v.open && <Button variant="ghost" size="sm" disabled={v.selected.length === 0} onClick={v.clear}>Clear</Button>}
          <SaveButton v={v} size="default" />
        </div>
        {v.open && v.candidates.length > 9 && (
          <Input aria-label="Search restaurants" placeholder="Search…" value={v.query} onChange={(e) => v.setQuery(e.target.value)} className="h-10" />
        )}
        <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {(v.open ? v.shown : v.candidates).map((r) => {
            const rank = v.selected.indexOf(r.id);
            const picked = rank >= 0;
            return (
              <li key={r.id} className="relative">
                <button type="button" aria-pressed={picked} disabled={!v.open} onClick={() => v.toggle(r.id)}
                  aria-label={picked ? `${r.name}, ranked ${RANK_LABEL[rank]}. Tap to remove.` : `Rank ${r.name}`}
                  className={cn("flex h-24 w-full flex-col justify-end rounded-xl border p-3 pr-10 text-left transition-colors duration-150 disabled:cursor-default",
                    picked ? "border-primary bg-primary/10 ring-2 ring-primary/40" : "bg-card hover:bg-muted/50")}>
                  <span className="line-clamp-2 font-semibold leading-tight">{r.name}</span>
                  <span className="truncate text-xs text-muted-foreground">{r.cuisine ?? " "}</span>
                </button>
                {/* Badge is absolutely positioned, so ranking a card never reflows it. */}
                <span aria-hidden="true" className={cn("pointer-events-none absolute right-2 top-2 grid h-8 w-8 place-items-center rounded-full text-sm font-extrabold transition-all duration-150",
                  picked ? "scale-100 bg-primary text-primary-foreground" : "scale-90 border border-dashed text-muted-foreground/50")}>
                  {picked ? rank + 1 : "+"}
                </span>
                {picked && rank > 0 && v.open && (
                  <button type="button" aria-label={`Move ${r.name} up to ${RANK_LABEL[rank - 1]}`} onClick={() => v.move(rank, -1)}
                    className="absolute bottom-2 right-2 grid h-8 w-8 place-items-center rounded-full border bg-background text-xs hover:bg-muted">▲</button>
                )}
              </li>
            );
          })}
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-bold">Leading now <span className="text-sm font-normal text-muted-foreground">({v.ballots.length} voted)</span></h2>
        <ol className="grid grid-cols-3 items-end gap-2" aria-label="Top three">
          {[1, 0, 2].map((i) => {
            const s = podium[i];
            return (
              <li key={i} className={cn("flex flex-col justify-end rounded-xl border bg-card p-2 text-center",
                i === 0 ? "h-28 border-primary" : i === 1 ? "h-24" : "h-20")}>
                <span className="text-xs font-bold text-muted-foreground">{RANK_LABEL[i]}</span>
                <span className="truncate text-sm font-semibold">{s && s.score > 0 ? s.name : "—"}</span>
                <span className="text-xs tabular-nums text-muted-foreground">{s && s.score > 0 ? `${s.score} pts` : " "}</span>
              </li>
            );
          })}
        </ol>
        <Collapsible open={more} onOpenChange={setMore}>
          <CollapsibleTrigger asChild>
            <Button variant="outline" className="w-full">{more ? "Hide" : "Show"} full standings & who voted</Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-3 space-y-4">
            <StandingsList v={v} />
            <VotersList v={v} />
          </CollapsibleContent>
        </Collapsible>
      </section>
    </div>
  );
}
