import { createFileRoute, Link, Outlet } from "@tanstack/react-router";
import { Logo } from "@/components/app/Logo";
import { useTeam, useTeamRealtime } from "@/lib/team-data";

export const Route = createFileRoute("/_authenticated/t/$teamId")({
  component: TeamLayout,
});

function TeamLayout() {
  const { teamId } = Route.useParams();
  const team = useTeam(teamId);
  useTeamRealtime(teamId);

  if (team.isLoading) return <main className="mx-auto max-w-3xl px-5 py-6"><div className="h-16 animate-pulse rounded-xl bg-muted" /></main>;
  if (!team.data) {
    return (
      <main className="mx-auto max-w-3xl px-5 py-6">
        <Logo />
        <p role="alert" className="mt-10">Team not found. <Link to="/teams" className="underline">Back to your teams</Link></p>
      </main>
    );
  }

  const link = "rounded-lg px-3 py-2 text-sm font-semibold text-muted-foreground hover:text-foreground";
  const active = { className: "bg-muted text-foreground" };
  return (
    <main className="mx-auto max-w-3xl px-5 py-6">
      <header className="flex items-center justify-between gap-3">
        <Logo />
        <Link to="/teams" className="text-sm text-muted-foreground underline">All teams</Link>
      </header>
      <h1 className="mt-6 text-3xl font-extrabold">{team.data.name}</h1>
      <nav className="mt-3 flex gap-1" aria-label="Team">
        <Link to="/t/$teamId" params={{ teamId }} activeOptions={{ exact: true }} className={link} activeProps={active}>Today</Link>
        <Link to="/t/$teamId/restaurants" params={{ teamId }} className={link} activeProps={active}>Restaurants</Link>
      </nav>
      <div className="mt-6"><Outlet /></div>
    </main>
  );
}
