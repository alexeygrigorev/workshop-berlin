import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { supabase } from "@/integrations/supabase/client";

export type Restaurant = {
  id: string; team_id: string; name: string; cuisine: string | null; address: string | null;
  website_url: string | null; map_url: string | null; notes: string | null; archived_at: string | null; created_by: string | null;
};

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: async () => (await supabase.auth.getUser()).data.user });
}

export function useTeam(teamId: string) {
  return useQuery({
    queryKey: ["team", teamId],
    queryFn: async () => {
      const { data, error } = await supabase.from("teams").select("*").eq("id", teamId).maybeSingle();
      if (error) throw error;
      return data;
    },
  });
}

export function useMembers(teamId: string) {
  return useQuery({
    queryKey: ["members", teamId],
    queryFn: async () => {
      const { data, error } = await supabase.from("team_members").select("user_id, role, joined_at, profiles(display_name)").eq("team_id", teamId).order("joined_at");
      if (error) throw error;
      return data;
    },
  });
}

export function useRestaurants(teamId: string) {
  return useQuery({
    queryKey: ["restaurants", teamId],
    queryFn: async () => {
      const { data, error } = await supabase.from("restaurants").select("*").eq("team_id", teamId).order("name");
      if (error) throw error;
      return data as Restaurant[];
    },
  });
}

export function useTodayPoll(teamId: string) {
  return useQuery({
    queryKey: ["poll", teamId],
    queryFn: async () => {
      const { data: pid, error } = await supabase.rpc("ensure_today_poll", { _team: teamId });
      if (error) throw error;
      if (!pid) return null;
      const [p, c, b] = await Promise.all([
        supabase.from("polls").select("*").eq("id", pid).single(),
        supabase.from("poll_candidates").select("restaurant_id").eq("poll_id", pid),
        supabase.from("ballots").select("user_id, choices, submitted_at, profiles(display_name)").eq("poll_id", pid).order("submitted_at"),
      ]);
      if (p.error) throw p.error;
      return { poll: p.data, candidateIds: (c.data ?? []).map((x) => x.restaurant_id), ballots: b.data ?? [] };
    },
  });
}

export function useClosedPolls(teamId: string) {
  return useQuery({
    queryKey: ["history", teamId],
    queryFn: async () => {
      const { data, error } = await supabase.from("polls").select("id, poll_date, winner_id, no_winner, ballot_count, final_scores, tie_break, timezone")
        .eq("team_id", teamId).eq("status", "closed").order("poll_date", { ascending: false }).limit(200);
      if (error) throw error;
      return data;
    },
  });
}

/** Live updates for one team; refetch on any change and on reconnect. */
export function useTeamRealtime(teamId: string) {
  const qc = useQueryClient();
  useEffect(() => {
    const refresh = () => {
      qc.invalidateQueries({ queryKey: ["poll", teamId] });
      qc.invalidateQueries({ queryKey: ["restaurants", teamId] });
    };
    const ch = supabase
      .channel(`team-${teamId}-${Math.random().toString(36).slice(2)}`)
      .on("postgres_changes", { event: "*", schema: "public", table: "ballots", filter: `team_id=eq.${teamId}` }, refresh)
      .on("postgres_changes", { event: "*", schema: "public", table: "poll_candidates", filter: `team_id=eq.${teamId}` }, refresh)
      .on("postgres_changes", { event: "*", schema: "public", table: "restaurants", filter: `team_id=eq.${teamId}` }, refresh)
      .on("postgres_changes", { event: "*", schema: "public", table: "polls", filter: `team_id=eq.${teamId}` }, () => {
        refresh();
        qc.invalidateQueries({ queryKey: ["history", teamId] });
      })
      .subscribe((status) => { if (status === "SUBSCRIBED") refresh(); });
    const onFocus = () => refresh();
    window.addEventListener("online", onFocus);
    return () => { window.removeEventListener("online", onFocus); supabase.removeChannel(ch); };
  }, [teamId, qc]);
}
