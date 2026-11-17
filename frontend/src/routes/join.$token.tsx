import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/app/Logo";
import { setAfterAuth } from "@/lib/auth-redirect";

export const Route = createFileRoute("/join/$token")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "Join your team — Where Should We Eat?" },
      { name: "description", content: "You've been invited to your team's daily lunch vote." },
      { property: "og:title", content: "Join your team's lunch vote" },
      { property: "og:description", content: "You've been invited to your team's daily lunch vote." },
    ],
  }),
  component: JoinPage,
});

function JoinPage() {
  const { token } = Route.useParams();
  const navigate = useNavigate();
  const [info, setInfo] = useState<{ team_id: string; team_name: string; already_member: boolean } | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const { data: s } = await supabase.auth.getSession();
      if (!s.session) { setAfterAuth(`/join/${token}`); navigate({ to: "/auth", replace: true }); return; }
      const { data } = await supabase.rpc("invite_info", { _token: token });
      setInfo(data?.[0] ?? null);
    })();
  }, [token, navigate]);

  async function join() {
    setBusy(true);
    const { data, error } = await supabase.rpc("join_team", { _token: token });
    setBusy(false);
    if (error) return setErr(error.message);
    navigate({ to: "/t/$teamId", params: { teamId: data as string } });
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 px-5">
      <Logo />
      <div className="rounded-2xl border bg-card p-6 shadow-card">
        {info === undefined && <p>Checking invite…</p>}
        {info === null && <p role="alert">This invite link is invalid or was revoked. Ask your team admin for a new one.</p>}
        {info && (
          <>
            <h1 className="text-3xl font-extrabold">Join {info.team_name}</h1>
            <p className="mt-2 text-muted-foreground">You'll see the team's restaurants and vote on lunch every weekday.</p>
            {err && <p role="alert" className="mt-3 text-sm text-destructive">{err}</p>}
            {info.already_member ? (
              <Button variant="pop" size="xl" className="mt-6 w-full" onClick={() => navigate({ to: "/t/$teamId", params: { teamId: info.team_id } })}>You're already in — open team</Button>
            ) : (
              <Button variant="pop" size="xl" className="mt-6 w-full" onClick={join} disabled={busy}>{busy ? "Joining…" : "Join team"}</Button>
            )}
          </>
        )}
      </div>
    </main>
  );
}
