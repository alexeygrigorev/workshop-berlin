import { Link } from "@tanstack/react-router";
export function Logo() {
  return (
    <Link to="/" className="inline-flex items-center gap-2 font-display text-lg font-extrabold tracking-tight">
      <span aria-hidden className="grid size-8 place-items-center rounded-full bg-primary text-primary-foreground">🍴</span>
      Where Should We Eat?
    </Link>
  );
}
