import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { polls } from "@/lib/api";
import { useMe, useMembers, useRestaurants, useTodayPoll } from "@/lib/team-data";
import { moveChoice, placeChoice, toggleChoice } from "@/lib/scoring";

export const MAX_PICKS = 3;

/** All voting state and actions for today's poll; layouts only decide how to show it. */
export function useVote(teamId: string) {
  const qc = useQueryClient();
  const me = useMe();
  const today = useTodayPoll(teamId);
  const all = useRestaurants(teamId);
  const members = useMembers(teamId);
  const [selected, setSelected] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);

  const myBallot = today.data?.my_ballot ?? null;
  useEffect(() => { if (myBallot) setSelected(myBallot.choices); }, [myBallot?.submitted_at]); // eslint-disable-line react-hooks/exhaustive-deps

  // The poll's candidates are {id, name} snapshots; borrow cuisine/address from the restaurant list for display and search.
  const candidates = useMemo(() => {
    const details = new Map((all.data ?? []).map((r) => [r.id, r]));
    return (today.data?.candidates ?? []).map((c) => ({ id: c.id, name: c.name, cuisine: details.get(c.id)?.cuisine ?? null, address: details.get(c.id)?.address ?? null }));
  }, [all.data, today.data]);
  const byId = useMemo(() => new Map(candidates.map((r) => [r.id, r])), [candidates]);
  const ballots = useMemo(() => today.data?.ballots ?? [], [today.data]);
  // Server-computed (scoring, tie-breaks, final scores once closed).
  const standings = useMemo(() => today.data?.standings ?? [], [today.data]);
  // Alphabetical, so re-submitting a vote doesn't move that voter's line.
  const voters = useMemo(() => [...ballots].sort((a, b) => a.display_name.localeCompare(b.display_name)), [ballots]);
  const notVoted = (members.data ?? []).filter((m) => !ballots.some((b) => b.user_id === m.user_id));

  const needle = query.trim().toLowerCase();
  const shown = candidates.filter((r) => !needle || [r.name, r.cuisine, r.address].some((v) => v?.toLowerCase().includes(needle)));

  const poll = today.data;
  const open = poll?.status === "open";
  const scheduled = poll?.status === "scheduled";
  const dirty = selected.join() !== (myBallot?.choices ?? []).join();
  const status: "loading" | "error" | "empty" | "ready" =
    today.isLoading ? "loading" : !today.data ? "error" : candidates.length === 0 ? "empty" : "ready";

  function toggle(id: string) {
    const { next, full } = toggleChoice(selected, id, MAX_PICKS);
    if (full) toast.info("You can rank up to 3 — remove one first");
    setSelected(next);
  }

  /** Assign an explicit rank (0-based). */
  function place(id: string, index: number) {
    const { next, dropped } = placeChoice(selected, id, index, MAX_PICKS);
    if (dropped) toast.info(`${byId.get(dropped)?.name ?? "A pick"} dropped out of your top 3`);
    setSelected(next);
  }

  async function submit() {
    if (!poll) return;
    setBusy(true);
    try {
      await polls.submitBallot(teamId, poll.id, selected);
      qc.invalidateQueries({ queryKey: ["poll", teamId] });
      toast.success("Vote saved");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save vote");
    }
    setBusy(false);
  }

  return {
    status, poll, open, scheduled, busy, dirty, hasBallot: !!myBallot, myId: me.data?.id,
    candidates, shown, byId, standings, ballots, voters, notVoted,
    topScore: standings[0]?.score ?? 0,
    selected, query, setQuery,
    toggle, place,
    move: (i: number, dir: -1 | 1) => setSelected(moveChoice(selected, i, dir)),
    remove: (id: string) => setSelected(selected.filter((x) => x !== id)),
    clear: () => setSelected([]),
    reset: () => setSelected(myBallot?.choices ?? []),
    submit,
  };
}

export type Vote = ReturnType<typeof useVote>;
