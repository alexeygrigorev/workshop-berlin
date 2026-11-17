import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { supabase } from "@/integrations/supabase/client";
import { lovable } from "@/integrations/lovable";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Logo } from "@/components/app/Logo";
import { GoogleIcon } from "@/components/app/GoogleIcon";
import { takeAfterAuth } from "@/lib/auth-redirect";

export const Route = createFileRoute("/auth")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "Sign in — Where Should We Eat?" },
      { name: "description", content: "Sign in to vote on today's team lunch." },
      { property: "og:title", content: "Sign in — Where Should We Eat?" },
      { property: "og:description", content: "Sign in to vote on today's team lunch." },
    ],
  }),
  component: AuthPage,
});

function AuthPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const hash = new URLSearchParams(window.location.hash.slice(1));
    const err = hash.get("error_description") || new URLSearchParams(window.location.search).get("error_description");
    if (err) setError(err.replace(/\+/g, " "));
    const go = () => navigate({ to: takeAfterAuth() as "/teams", replace: true });
    supabase.auth.getSession().then(({ data }) => data.session && go());
    const { data } = supabase.auth.onAuthStateChange((_e, session) => session && go());
    return () => data.subscription.unsubscribe();
  }, [navigate]);

  async function google() {
    setError(null);
    const r = await lovable.auth.signInWithOAuth("google", { redirect_uri: window.location.origin + "/auth" });
    if (r.error) setError(r.error.message ?? "Google sign-in failed. Please try again.");
  }

  async function magic(e: React.FormEvent) {
    e.preventDefault();
    setSending(true);
    setError(null);
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: window.location.origin + "/auth" },
    });
    setSending(false);
    if (error) { setError(error.message); toast.error(error.message); }
    else setSent(true);
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-8 px-5 py-10">
      <Logo />
      <div>
        <h1 className="text-4xl font-extrabold">Lunch, decided by 11:30.</h1>
        <p className="mt-2 text-muted-foreground">Sign in to rank today's spots with your team.</p>
      </div>
      <div className="space-y-5 rounded-2xl border bg-card p-6 shadow-card">
        {error && <p role="alert" className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
        <Button variant="google" size="xl" className="w-full rounded-full" onClick={google}>
          <GoogleIcon /> Continue with Google
        </Button>
        <div className="flex items-center gap-3 text-xs uppercase tracking-wider text-muted-foreground">
          <span className="h-px flex-1 bg-border" /> or <span className="h-px flex-1 bg-border" />
        </div>
        {sent ? (
          <div role="status" className="rounded-lg bg-success/10 p-4 text-sm">
            <p className="font-semibold">Check your inbox</p>
            <p className="text-muted-foreground">We sent a sign-in link to {email}. Open it on this device.</p>
            <Button variant="link" className="px-0" onClick={() => setSent(false)}>Use a different email</Button>
          </div>
        ) : (
          <form onSubmit={magic} className="space-y-3">
            <Label htmlFor="email">Work email</Label>
            <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" className="h-11" />
            <Button type="submit" variant="pop" size="xl" className="w-full" disabled={sending}>
              {sending ? "Sending…" : "Email me a sign-in link"}
            </Button>
          </form>
        )}
      </div>
    </main>
  );
}
