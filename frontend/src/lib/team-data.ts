import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { auth, polls, restaurants, subscribeTeamEvents, teams } from "@/lib/api";

export type { Restaurant } from "@/lib/api";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => auth.getUser() });
}

export function useTeam(teamId: string) {
  return useQuery({ queryKey: ["team", teamId], queryFn: () => teams.get(teamId) });
}

export function useMembers(teamId: string) {
  return useQuery({ queryKey: ["members", teamId], queryFn: () => teams.members(teamId) });
}

export function useRestaurants(teamId: string) {
  return useQuery({ queryKey: ["restaurants", teamId], queryFn: () => restaurants.list(teamId) });
}

/** The team's current poll with live standings, ballots and my ballot (server-computed). */
export function useTodayPoll(teamId: string) {
  return useQuery({ queryKey: ["poll", teamId], queryFn: () => polls.current(teamId) });
}

export function useClosedPolls(teamId: string) {
  return useQuery({ queryKey: ["history", teamId], queryFn: () => polls.closed(teamId) });
}

/** Live updates for one team via SSE: events invalidate the affected queries. */
export function useTeamRealtime(teamId: string) {
  const qc = useQueryClient();
  useEffect(() => {
    const invalidate = (...keys: string[]) => keys.forEach((k) => qc.invalidateQueries({ queryKey: [k, teamId] }));
    const all = () => invalidate("poll", "restaurants", "history", "members", "team");
    return subscribeTeamEvents(
      teamId,
      (e) => {
        const kind = e.type.split(".")[0];
        if (kind === "ballot") invalidate("poll");
        else if (kind === "poll") invalidate("poll", "history");
        else if (kind === "restaurant") invalidate("restaurants", "poll");
        else if (kind === "member") invalidate("members", "poll", "team");
        else if (e.type === "team.updated") invalidate("team", "poll");
        else if (e.type !== "invite.changed") all(); // resync and anything unknown
      },
      all, // after a reconnect we may have missed events
    );
  }, [teamId, qc]);
}
