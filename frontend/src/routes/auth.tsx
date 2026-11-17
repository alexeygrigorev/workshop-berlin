import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { auth } from "@/lib/mock-backend";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Logo } from "@/components/app/Logo";
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
  const [password, setPassword] = useState("");
  const [signUp, setSignUp] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const go = () => navigate({ to: takeAfterAuth() as "/teams", replace: true });
    auth.getSession().then((session) => session && go());
    return auth.onChange((_e, session) => { if (session) go(); });
  }, [navigate]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSending(true);
    setError(null);
    try {
      await (signUp ? auth.signUp(email, password) : auth.signIn(email, password));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong";
      setError(message);
      toast.error(message);
    }
    setSending(false);
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
        <form onSubmit={submit} className="space-y-3">
          <Label htmlFor="email">Work email</Label>
          <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" className="h-11" />
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" required minLength={6} autoComplete={signUp ? "new-password" : "current-password"} value={password} onChange={(e) => setPassword(e.target.value)} className="h-11" />
          <Button type="submit" variant="pop" size="xl" className="w-full" disabled={sending}>
            {sending ? "Please wait…" : signUp ? "Create account" : "Sign in"}
          </Button>
          <Button type="button" variant="link" className="px-0" onClick={() => setSignUp(!signUp)}>
            {signUp ? "Already have an account? Sign in" : "No account? Create one"}
          </Button>
        </form>
      </div>
    </main>
  );
}
