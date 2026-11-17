import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { auth, onDataChange, polls, restaurants, teams } from "@/lib/mock-backend";

export type { Restaurant } from "@/lib/mock-backend";

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

export function useTodayPoll(teamId: string) {
  return useQuery({ queryKey: ["poll", teamId], queryFn: () => polls.today(teamId) });
}

export function useClosedPolls(teamId: string) {
  return useQuery({ queryKey: ["history", teamId], queryFn: () => polls.closed(teamId) });
}

/** Live updates for one team; refetch on any change. */
export function useTeamRealtime(teamId: string) {
  const qc = useQueryClient();
  useEffect(() => {
    const refresh = () => {
      qc.invalidateQueries({ queryKey: ["poll", teamId] });
      qc.invalidateQueries({ queryKey: ["restaurants", teamId] });
      qc.invalidateQueries({ queryKey: ["history", teamId] });
    };
    return onDataChange(refresh);
  }, [teamId, qc]);
}
