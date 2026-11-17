/**
 * Mock backend: the only place that knows about data storage or auth.
 * Everything lives in localStorage, so it is per-browser and not secure
 * (passwords are stored in plain text). Replace this file to use a real API.
 */

import { FRIEDRICHSTRASSE_SEED, mapUrl } from "@/lib/seed-restaurants";

export type User = { id: string; email: string };
export type Session = { user: User };
export type AuthEvent = "SIGNED_IN" | "SIGNED_OUT";
export type Role = "admin" | "member";

export type Team = { id: string; name: string; timezone: string; office: string | null; invite_token: string };
export type Restaurant = {
  id: string; team_id: string; name: string; cuisine: string | null; address: string | null;
  website_url: string | null; map_url: string | null; notes: string | null; archived_at: string | null; created_by: string | null;
};
export type Poll = {
  id: string; team_id: string; poll_date: string; status: "open" | "closed";
  winner_id: string | null; no_winner: boolean; ballot_count: number;
  final_scores: Record<string, number> | null; tie_break: string | null; timezone: string;
};
export type Ballot = { poll_id: string; team_id: string; user_id: string; choices: string[]; submitted_at: string };
type Member = { team_id: string; user_id: string; role: Role; joined_at: string };

type Db = {
  users: (User & { password: string })[];
  teams: Team[];
  members: Member[];
  restaurants: Restaurant[];
  polls: Poll[];
  ballots: Ballot[];
};

const DB_KEY = "wswe_mock_db";
const SESSION_KEY = "wswe_mock_session";
const EMPTY: Db = { users: [], teams: [], members: [], restaurants: [], polls: [], ballots: [] };

const hasStorage = () => typeof window !== "undefined" && !!window.localStorage;
const uid = () => crypto.randomUUID();
const now = () => new Date().toISOString();
const delay = () => new Promise<void>((r) => setTimeout(r, 120));

function load(): Db {
  if (!hasStorage()) return structuredClone(EMPTY);
  try {
    return { ...structuredClone(EMPTY), ...JSON.parse(localStorage.getItem(DB_KEY) ?? "{}") };
  } catch {
    return structuredClone(EMPTY);
  }
}

const dataListeners = new Set<() => void>();
function save(db: Db) {
  localStorage.setItem(DB_KEY, JSON.stringify(db));
  dataListeners.forEach((fn) => fn());
}

/** Throw the same `{ message }` shape the UI already displays. */
const fail = (message: string): never => { throw new Error(message); };

// ---------- auth ----------

const authListeners = new Set<(event: AuthEvent, session: Session | null) => void>();

function currentSession(): Session | null {
  if (!hasStorage()) return null;
  try {
    const s = JSON.parse(localStorage.getItem(SESSION_KEY) ?? "null") as Session | null;
    // Drop sessions whose user no longer exists (e.g. DB was cleared).
    return s && load().users.some((u) => u.id === s.user.id) ? s : null;
  } catch {
    return null;
  }
}

function setSession(session: Session | null) {
  if (session) localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  else localStorage.removeItem(SESSION_KEY);
  authListeners.forEach((fn) => fn(session ? "SIGNED_IN" : "SIGNED_OUT", session));
}

function requireUser(): User {
  return currentSession()?.user ?? fail("Not signed in");
}

export const auth = {
  async getSession(): Promise<Session | null> { return currentSession(); },
  async getUser(): Promise<User | null> { return currentSession()?.user ?? null; },

  async signUp(email: string, password: string): Promise<User> {
    await delay();
    const db = load();
    email = email.trim().toLowerCase();
    if (password.length < 6) fail("Password should be at least 6 characters.");
    if (db.users.some((u) => u.email === email)) fail("User already registered");
    const user = { id: uid(), email, password };
    db.users.push(user);
    save(db);
    setSession({ user: { id: user.id, email } });
    return { id: user.id, email };
  },

  async signIn(email: string, password: string): Promise<User> {
    await delay();
    const u = load().users.find((x) => x.email === email.trim().toLowerCase() && x.password === password);
    if (!u) fail("Invalid login credentials");
    const user = { id: u!.id, email: u!.email };
    setSession({ user });
    return user;
  },

  async signOut(): Promise<void> { setSession(null); },

  /** Returns an unsubscribe function. Also fires for sign-in/out in other tabs. */
  onChange(fn: (event: AuthEvent, session: Session | null) => void): () => void {
    authListeners.add(fn);
    const onStorage = (e: StorageEvent) => {
      if (e.key !== SESSION_KEY) return;
      const s = currentSession();
      fn(s ? "SIGNED_IN" : "SIGNED_OUT", s);
    };
    window.addEventListener("storage", onStorage);
    return () => { authListeners.delete(fn); window.removeEventListener("storage", onStorage); };
  },
};

// ---------- teams ----------

/** Give a team that has never had restaurants the Friedrichstraße starter list. Returns true if it changed `db`. */
function seedIfEmpty(db: Db, teamId: string, userId: string | null): boolean {
  if (db.restaurants.some((r) => r.team_id === teamId)) return false;
  for (const x of FRIEDRICHSTRASSE_SEED) {
    db.restaurants.push({
      id: uid(), team_id: teamId, name: x.name, cuisine: x.cuisine, address: x.address, website_url: null,
      map_url: mapUrl(x.name, x.address), notes: null, archived_at: null, created_by: userId,
    });
  }
  return true;
}

export const teams = {
  async mine(): Promise<{ role: Role; team: Pick<Team, "id" | "name" | "timezone"> }[]> {
    await delay();
    const me = requireUser();
    const db = load();
    return db.members
      .filter((m) => m.user_id === me.id)
      .flatMap((m) => {
        const t = db.teams.find((x) => x.id === m.team_id);
        return t ? [{ role: m.role, team: { id: t.id, name: t.name, timezone: t.timezone } }] : [];
      });
  },

  async get(teamId: string): Promise<Team | null> {
    await delay();
    return load().teams.find((t) => t.id === teamId) ?? null;
  },

  async create(name: string, timezone: string, office?: string): Promise<string> {
    await delay();
    const me = requireUser();
    const db = load();
    const team: Team = { id: uid(), name: name.trim(), timezone, office: office || null, invite_token: uid() };
    db.teams.push(team);
    db.members.push({ team_id: team.id, user_id: me.id, role: "admin", joined_at: now() });
    seedIfEmpty(db, team.id, me.id);
    save(db);
    return team.id;
  },

  async members(teamId: string): Promise<{ user_id: string; role: Role; joined_at: string; display_name: string }[]> {
    await delay();
    const db = load();
    return db.members
      .filter((m) => m.team_id === teamId)
      .sort((a, b) => a.joined_at.localeCompare(b.joined_at))
      .map((m) => ({
        user_id: m.user_id, role: m.role, joined_at: m.joined_at,
        display_name: db.users.find((u) => u.id === m.user_id)?.email.split("@")[0] ?? "Unknown",
      }));
  },

  async inviteInfo(token: string): Promise<{ team_id: string; team_name: string; already_member: boolean } | null> {
    await delay();
    const me = requireUser();
    const db = load();
    const t = db.teams.find((x) => x.invite_token === token);
    if (!t) return null;
    return { team_id: t.id, team_name: t.name, already_member: db.members.some((m) => m.team_id === t.id && m.user_id === me.id) };
  },

  async join(token: string): Promise<string> {
    await delay();
    const me = requireUser();
    const db = load();
    const t = db.teams.find((x) => x.invite_token === token) ?? fail("Invalid invite link");
    if (!db.members.some((m) => m.team_id === t.id && m.user_id === me.id)) {
      db.members.push({ team_id: t.id, user_id: me.id, role: "member", joined_at: now() });
      save(db);
    }
    return t.id;
  },

  async regenerateInvite(teamId: string): Promise<string> {
    await delay();
    const me = requireUser();
    const db = load();
    const t = db.teams.find((x) => x.id === teamId) ?? fail("Team not found");
    if (!db.members.some((m) => m.team_id === teamId && m.user_id === me.id && m.role === "admin")) fail("Admins only");
    t.invite_token = uid();
    save(db);
    return t.invite_token;
  },
};

// ---------- restaurants ----------

export const restaurants = {
  async list(teamId: string): Promise<Restaurant[]> {
    await delay();
    const db = load();
    if (db.teams.some((t) => t.id === teamId) && seedIfEmpty(db, teamId, null)) save(db);
    return db.restaurants.filter((r) => r.team_id === teamId).sort((a, b) => a.name.localeCompare(b.name));
  },

  async add(teamId: string, r: Partial<Omit<Restaurant, "id" | "team_id" | "created_by" | "archived_at">> & { name: string }): Promise<Restaurant> {
    await delay();
    const me = requireUser();
    const db = load();
    const row: Restaurant = {
      id: uid(), team_id: teamId, cuisine: null, address: null, website_url: null, map_url: null, notes: null,
      ...r, archived_at: null, created_by: me.id,
    };
    db.restaurants.push(row);
    save(db);
    return row;
  },

  async setArchived(id: string, archived: boolean): Promise<void> {
    await delay();
    const db = load();
    const r = db.restaurants.find((x) => x.id === id) ?? fail("Restaurant not found");
    r.archived_at = archived ? now() : null;
    save(db);
  },
};

// ---------- polls ----------

const today = () => new Date().toISOString().slice(0, 10);

export const polls = {
  /** Today's poll for a team (created on first call), its candidates and ballots. */
  async today(teamId: string): Promise<{ poll: Poll; candidateIds: string[]; ballots: (Ballot & { display_name: string })[] } | null> {
    await delay();
    const db = load();
    const team = db.teams.find((t) => t.id === teamId);
    if (!team) return null;
    let poll = db.polls.find((p) => p.team_id === teamId && p.poll_date === today());
    if (!poll) {
      poll = {
        id: uid(), team_id: teamId, poll_date: today(), status: "open", winner_id: null, no_winner: false,
        ballot_count: 0, final_scores: null, tie_break: null, timezone: team.timezone,
      };
      db.polls.push(poll);
      save(db);
    }
    const pid = poll.id;
    return {
      poll,
      candidateIds: db.restaurants.filter((r) => r.team_id === teamId && !r.archived_at).map((r) => r.id),
      ballots: db.ballots.filter((b) => b.poll_id === pid).sort((a, b) => a.submitted_at.localeCompare(b.submitted_at))
        .map((b) => ({ ...b, display_name: db.users.find((u) => u.id === b.user_id)?.email.split("@")[0] ?? "Unknown" })),
    };
  },

  /** Ranked choices, best first (max 3). Replaces any earlier ballot from the same user. */
  async submitBallot(pollId: string, choices: string[]): Promise<void> {
    await delay();
    const me = requireUser();
    const db = load();
    const poll = db.polls.find((p) => p.id === pollId) ?? fail("Poll not found");
    if (poll.status !== "open") fail("This poll is closed");
    if (choices.length < 1 || choices.length > 3 || new Set(choices).size !== choices.length) fail("Pick 1 to 3 different restaurants");
    db.ballots = db.ballots.filter((b) => !(b.poll_id === pollId && b.user_id === me.id));
    db.ballots.push({ poll_id: pollId, team_id: poll.team_id, user_id: me.id, choices, submitted_at: now() });
    poll.ballot_count = db.ballots.filter((b) => b.poll_id === pollId).length;
    save(db);
  },

  async closed(teamId: string): Promise<Poll[]> {
    await delay();
    return load().polls.filter((p) => p.team_id === teamId && p.status === "closed").sort((a, b) => b.poll_date.localeCompare(a.poll_date));
  },
};

// ---------- change notifications (replaces realtime) ----------

/** Calls `fn` whenever data changes, here or in another tab. Returns an unsubscribe function. */
export function onDataChange(fn: () => void): () => void {
  dataListeners.add(fn);
  const onStorage = (e: StorageEvent) => { if (e.key === DB_KEY) fn(); };
  window.addEventListener("storage", onStorage);
  return () => { dataListeners.delete(fn); window.removeEventListener("storage", onStorage); };
}
