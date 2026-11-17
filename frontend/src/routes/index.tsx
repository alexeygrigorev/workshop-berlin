import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { auth } from "@/lib/mock-backend";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/app/Logo";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Where Should We Eat? — Team lunch voting" },
      { name: "description", content: "A daily lunch vote for your team. Rank your top three by 11:30 and see the winner." },
      { property: "og:title", content: "Where Should We Eat? — Team lunch voting" },
      { property: "og:description", content: "A daily lunch vote for your team. Rank your top three by 11:30." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

function Index() {
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => { auth.getSession().then((session) => setSignedIn(!!session)); }, []);
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col px-5 py-6">
      <header className="flex items-center justify-between">
        <Logo />
        <Button asChild variant="outline">
          <Link to={signedIn ? "/teams" : "/auth"}>{signedIn ? "My teams" : "Sign in"}</Link>
        </Button>
      </header>
      <section className="grid flex-1 items-center gap-10 py-16 md:grid-cols-2">
        <div>
          <p className="mb-4 inline-block rounded-full bg-accent px-3 py-1 text-sm font-semibold">Weekdays · 08:00 – 11:30</p>
          <h1 className="text-5xl font-extrabold leading-[1.02] md:text-6xl">Stop debating. <span className="text-primary">Start eating.</span></h1>
          <p className="mt-5 max-w-md text-lg text-muted-foreground">
            Every workday a fresh vote opens for your team. Tap your top three, watch the standings live, and lunch is decided at 11:30.
          </p>
          <Button asChild variant="pop" size="xl" className="mt-8">
            <Link to={signedIn ? "/teams" : "/auth"}>{signedIn ? "Go to today's vote" : "Get started — it's free"}</Link>
          </Button>
        </div>
        <ol aria-label="Example ballot" className="space-y-3 rounded-3xl border bg-card p-6 shadow-card">
          {[["1st", "Pho Saigon", "3 pts"], ["2nd", "Burrito Bar", "2 pts"], ["3rd", "Green Bowl", "1 pt"]].map(([r, n, p], i) => (
            <li key={r} className="flex items-center gap-4 rounded-xl bg-muted p-4" style={{ animationDelay: `${i * 80}ms` }}>
              <span className="grid size-11 place-items-center rounded-full bg-primary font-display font-bold text-primary-foreground">{r}</span>
              <span className="flex-1 font-semibold">{n}</span>
              <span className="text-sm text-muted-foreground">{p}</span>
            </li>
          ))}
          <p className="pt-2 text-sm text-muted-foreground">Ranked points: 3 for 1st, 2 for 2nd, 1 for 3rd.</p>
        </ol>
      </section>
    </main>
  );
}
