/**
 * HTTP client for the FastAPI backend (contract: /api/openapi.yaml).
 * The only module that knows about the network, the session token and the SSE stream.
 * Types are hand-written from the spec.
 */

const BASE_URL = ((import.meta.env["VITE_API_URL"] as string | undefined) || "http://localhost:8000").replace(/\/+$/, "");
const TOKEN_KEY = "wswe_token";

// ---------- types (mirror api/openapi.yaml) ----------

export type Role = "admin" | "member";
export type PollStatus = "scheduled" | "open" | "closed";
export type TieBreak = "first_place_votes" | "second_place_votes" | "random_draw" | null;

export type User = { id: string; email: string; display_name: string; created_at: string };
export type Session = { user: User };
export type AuthEvent = "SIGNED_IN" | "SIGNED_OUT";

export type TeamRef = { id: string; name: string; timezone: string };
export type MyTeam = { role: Role; joined_at: string; team: TeamRef };
export type Team = {
  id: string; name: string; timezone: string; office: string | null;
  schedule: { open_time: string; close_time: string; weekdays: number[] };
  my_role: Role; member_count: number; created_at: string; updated_at: string;
};
export type Member = { user_id: string; display_name: string; role: Role; joined_at: string };
export type Invite = { active: boolean; token: string | null; url: string | null; updated_at: string };
export type InvitePreview = { team_id: string; team_name: string; member_count: number; already_member: boolean };
export type JoinResult = { joined: boolean; role: Role; team: TeamRef };

export type Restaurant = {
  id: string; team_id: string; name: string; cuisine: string | null; address: string | null;
  website_url: string | null; map_url: string | null; notes: string | null;
  archived_at: string | null; created_by: string | null; created_at: string; updated_at: string;
};
export type RestaurantCreate = {
  name: string; cuisine?: string | null; address?: string | null;
  website_url?: string | null; map_url?: string | null; notes?: string | null;
};

export type Candidate = { id: string; name: string; archived: boolean };
export type Standing = {
  restaurant_id: string; name: string; score: number;
  first_count: number; second_count: number; third_count: number; position: number;
};
export type Ballot = {
  poll_id: string; team_id: string; user_id: string; display_name: string; choices: string[]; submitted_at: string;
};
export type Poll = {
  id: string; team_id: string; poll_date: string; timezone: string; opens_at: string; closes_at: string;
  status: PollStatus; candidates: Candidate[]; winner_id: string | null; winner: Restaurant | null;
  no_winner: boolean; ballot_count: number; final_scores: Standing[] | null; tie_break: TieBreak; finalized_at: string | null;
};
export type PollDetail = Poll & {
  standings: Standing[]; ballots: Ballot[]; my_ballot: Ballot | null; member_count: number; server_time: string;
};
export type PollPage = { items: Poll[]; next_cursor: string | null };

export type TeamEvent = {
  id: string; type: string; team_id: string; poll_id?: string | null; occurred_at: string; data: Record<string, unknown>;
};

// ---------- errors ----------

/** RFC 9457 problem+json from the server. `message` is `detail ?? title`, so UI code can keep showing `err.message`. */
export class ApiError extends Error {
  status: number;
  code: string;
  errors: { pointer: string; code: string; message: string }[] | undefined;
  constructor(status: number, code: string, message: string, errors?: ApiError["errors"]) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.errors = errors;
  }
}

// ---------- token + auth change notifications ----------

const hasStorage = () => typeof window !== "undefined" && !!window.localStorage;

function getToken(): string | null {
  if (!hasStorage()) return null;
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

const authListeners = new Set<(event: AuthEvent, session: Session | null) => void>();
let cachedUser: User | null = null;

function setSession(token: string | null, user: User | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* storage unavailable */ }
  cachedUser = user;
  authListeners.forEach((fn) => fn(user ? "SIGNED_IN" : "SIGNED_OUT", user ? { user } : null));
}

// ---------- fetch wrapper ----------

type Opts = { method?: string; body?: unknown; query?: Record<string, string | number | undefined>; auth?: boolean; signal?: AbortSignal };

async function toError(res: Response): Promise<ApiError> {
  try {
    const p = await res.json();
    return new ApiError(res.status, p.code ?? "internal_error", p.detail ?? p.title ?? `Request failed (${res.status})`, p.errors);
  } catch {
    return new ApiError(res.status, "internal_error", `Request failed (${res.status})`);
  }
}

async function request<T>(path: string, opts: Opts = {}): Promise<T> {
  const url = new URL(BASE_URL + path);
  for (const [k, v] of Object.entries(opts.query ?? {})) if (v !== undefined) url.searchParams.set(k, String(v));
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token && opts.auth !== false) headers["Authorization"] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(url, {
      method: opts.method ?? "GET", headers,
      ...(opts.body !== undefined && { body: JSON.stringify(opts.body) }),
      ...(opts.signal && { signal: opts.signal }),
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(0, "unavailable", "Could not reach the server. Check your connection and try again.");
  }
  if (!res.ok) {
    const err = await toError(res);
    // An expired/invalid session: sign out (but not for failed sign-in attempts).
    if (res.status === 401 && opts.auth !== false && token) setSession(null, null);
    throw err;
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

const enc = encodeURIComponent;

// ---------- auth ----------

type SessionResponse = { access_token: string; expires_at: string; user: User };

export const auth = {
  async getUser(): Promise<User | null> {
    if (!getToken()) return null;
    try {
      cachedUser = await request<User>("/v1/me");
      return cachedUser;
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return null; // already signed out by request()
      throw e;
    }
  },
  async getSession(): Promise<Session | null> {
    const user = await auth.getUser();
    return user ? { user } : null;
  },

  async signUp(email: string, password: string): Promise<User> {
    const s = await request<SessionResponse>("/v1/auth/sign-up", { method: "POST", body: { email: email.trim(), password }, auth: false });
    setSession(s.access_token, s.user);
    return s.user;
  },
  async signIn(email: string, password: string): Promise<User> {
    const s = await request<SessionResponse>("/v1/auth/sign-in", { method: "POST", body: { email: email.trim(), password }, auth: false });
    setSession(s.access_token, s.user);
    return s.user;
  },
  async signOut(): Promise<void> {
    try { if (getToken()) await request<void>("/v1/auth/sign-out", { method: "POST" }); } catch { /* sign out locally anyway */ }
    setSession(null, null);
  },

  /** Returns an unsubscribe function. Also fires for sign-in/out in other tabs. */
  onChange(fn: (event: AuthEvent, session: Session | null) => void): () => void {
    authListeners.add(fn);
    const onStorage = (e: StorageEvent) => {
      if (e.key !== TOKEN_KEY) return;
      const had = !!e.newValue;
      if (!had) cachedUser = null;
      fn(had ? "SIGNED_IN" : "SIGNED_OUT", had && cachedUser ? { user: cachedUser } : null);
    };
    window.addEventListener("storage", onStorage);
    return () => { authListeners.delete(fn); window.removeEventListener("storage", onStorage); };
  },
};

// ---------- teams ----------

export const teams = {
  async mine(): Promise<MyTeam[]> {
    return (await request<{ items: MyTeam[] }>("/v1/me/teams")).items;
  },
  /** Null when the team doesn't exist or the caller isn't a member (404 / 403). */
  async get(teamId: string): Promise<Team | null> {
    try { return await request<Team>(`/v1/teams/${enc(teamId)}`); }
    catch (e) { if (e instanceof ApiError && (e.status === 404 || e.status === 403)) return null; throw e; }
  },
  async create(name: string, timezone: string, office?: string): Promise<string> {
    const t = await request<Team>("/v1/teams", { method: "POST", body: { name: name.trim(), timezone, office: office || null } });
    return t.id;
  },
  async members(teamId: string): Promise<Member[]> {
    return (await request<{ items: Member[] }>(`/v1/teams/${enc(teamId)}/members`)).items;
  },
  async invite(teamId: string): Promise<Invite> {
    return request<Invite>(`/v1/teams/${enc(teamId)}/invite`);
  },
  /** Null when the invite is invalid or revoked. */
  async inviteInfo(token: string): Promise<InvitePreview | null> {
    try { return await request<InvitePreview>(`/v1/invites/${enc(token)}`); }
    catch (e) { if (e instanceof ApiError && (e.code === "invite_invalid" || e.status === 404 || e.status === 422)) return null; throw e; }
  },
  async join(token: string): Promise<string> {
    return (await request<JoinResult>(`/v1/invites/${enc(token)}/accept`, { method: "POST" })).team.id;
  },
  async regenerateInvite(teamId: string): Promise<Invite> {
    return request<Invite>(`/v1/teams/${enc(teamId)}/invite/regenerate`, { method: "POST" });
  },
};

// ---------- restaurants ----------

export const restaurants = {
  /** Active restaurants, sorted by name. */
  async list(teamId: string): Promise<Restaurant[]> {
    return (await request<{ items: Restaurant[] }>(`/v1/teams/${enc(teamId)}/restaurants`)).items;
  },
  async add(teamId: string, r: RestaurantCreate): Promise<Restaurant> {
    return request<Restaurant>(`/v1/teams/${enc(teamId)}/restaurants`, { method: "POST", body: r });
  },
  async setArchived(teamId: string, id: string, archived: boolean): Promise<Restaurant> {
    return request<Restaurant>(`/v1/teams/${enc(teamId)}/restaurants/${enc(id)}/${archived ? "archive" : "unarchive"}`, { method: "POST" });
  },
};

// ---------- polls ----------

export const polls = {
  /** The team's current poll (scheduled, open or, after closing time, closed), with live standings and ballots. */
  async current(teamId: string): Promise<PollDetail> {
    return request<PollDetail>(`/v1/teams/${enc(teamId)}/polls/current`);
  },
  /** Ranked choices, best first (max 3). Replaces any earlier ballot from the same user. */
  async submitBallot(teamId: string, pollId: string, choices: string[]): Promise<Ballot> {
    return request<Ballot>(`/v1/teams/${enc(teamId)}/polls/${enc(pollId)}/ballots/me`, { method: "PUT", body: { choices } });
  },
  /** Closed polls, newest first (first page). */
  async closed(teamId: string, limit = 30): Promise<PollPage> {
    return request<PollPage>(`/v1/teams/${enc(teamId)}/polls`, { query: { status: "closed", limit } });
  },
};

// ---------- realtime (SSE) ----------

/**
 * Subscribes to the team's SSE stream. `EventSource` can't send an Authorization header and the cookie
 * would need credentialed CORS, so this reads the stream with fetch() and the bearer token instead.
 * Reconnects with backoff, resuming via Last-Event-ID. `onEvent` gets every event; `onReconnect` is
 * called after a *re*connect so callers can refetch anything that may have been missed.
 */
export function subscribeTeamEvents(
  teamId: string,
  onEvent: (e: TeamEvent) => void,
  onReconnect?: () => void,
): () => void {
  const ctrl = new AbortController();
  let lastId: string | undefined;
  let attempt = 0;
  let connectedBefore = false;

  async function run() {
    while (!ctrl.signal.aborted) {
      try {
        const headers: Record<string, string> = { Accept: "text/event-stream" };
        const token = getToken();
        if (!token) return;
        headers["Authorization"] = `Bearer ${token}`;
        if (lastId) headers["Last-Event-ID"] = lastId;
        const res = await fetch(`${BASE_URL}/v1/teams/${enc(teamId)}/events`, { headers, signal: ctrl.signal });
        if (res.status === 401) { setSession(null, null); return; }
        if (res.status === 403 || res.status === 404) return; // not a member: stop for good
        if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
        if (connectedBefore) onReconnect?.();
        connectedBefore = true;
        attempt = 0;
        await readStream(res.body, (id, data) => {
          if (id) lastId = id;
          try { onEvent(JSON.parse(data) as TeamEvent); } catch { /* ignore malformed frame */ }
        }, ctrl.signal);
      } catch (e) {
        if (ctrl.signal.aborted) return;
        void e;
      }
      if (ctrl.signal.aborted) return;
      // Stream ended or failed: back off (1s, 2s, 4s ... max 30s) and resume.
      const wait = Math.min(30_000, 1000 * 2 ** attempt++);
      await new Promise<void>((r) => { const t = setTimeout(r, wait); ctrl.signal.addEventListener("abort", () => { clearTimeout(t); r(); }, { once: true }); });
    }
  }
  void run();
  return () => ctrl.abort();
}

async function readStream(body: ReadableStream<Uint8Array>, onFrame: (id: string | undefined, data: string) => void, signal: AbortSignal) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  const onAbort = () => void reader.cancel().catch(() => {});
  signal.addEventListener("abort", onAbort, { once: true });
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return;
      buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let i: number;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const frame = buf.slice(0, i);
        buf = buf.slice(i + 2);
        let id: string | undefined;
        const data: string[] = [];
        for (const line of frame.split("\n")) {
          if (line.startsWith(":")) continue; // keep-alive comment
          if (line.startsWith("id:")) id = line.slice(3).trim();
          else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
        }
        if (data.length) onFrame(id, data.join("\n"));
      }
    }
  } finally {
    signal.removeEventListener("abort", onAbort);
  }
}
