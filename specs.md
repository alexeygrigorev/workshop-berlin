# Where Should We Eat? — Product and Engineering Specification

**Status:** MVP implementation specification  
**Version:** 1.0  
**Audience:** Coding agent / engineering team  
**Product:** Responsive collaborative daily lunch voting web application

## 1. Product summary

Build a lightweight web app for coworkers to decide where to eat lunch. Each team has a shared, persistent list of restaurants. On every workday, a new vote opens automatically at **08:00** in the team's configured timezone and closes automatically at **11:30**. Members select and rank **up to three** restaurants by tapping them in sequence, not by dragging through the entire restaurant list. All submitted rankings, voter identities and aggregate results are visible live to team members. At closing, the winner is finalized and saved to the team's history.

### Core product principles

1. **Fast:** A returning member should cast or revise a vote in about 15 seconds.
2. **Low friction:** Restaurant discovery via search; tap-to-rank; no long-list reordering.
3. **Transparent:** Live standings and named individual rankings are visible within the team.
4. **Repeatable:** Same shared restaurant pool; automatic weekday polls; no daily setup required.
5. **Predictable:** Team-local time determines poll lifecycle; scoring and tie-breakers are stable.

## 2. Target users, roles, and scope

- Target users: teams of approximately 5–20 coworkers, though implementation should support at least 100 members and 100 saved restaurants per team.
- **Member:** Join a team, view shared restaurants, add restaurants, cast/edit vote, view standings and named votes, view history, leave team.
- **Team admin:** All member permissions, plus update team name/timezone/schedule, remove members, edit/archive any restaurant, revoke/regenerate invite links, manage admin roles.
- Team creator is initial admin. Each user may join multiple teams, each with a separate daily vote and restaurant list.
- Authenticated membership is required to view team data or vote. Shared invite links facilitate joining, not anonymous voting.

### MVP included

- Email magic-link and Google OAuth authentication (subject to provider configuration).
- Create/join teams with persistent membership and shareable invite links.
- Team settings, team-local scheduling, and role-based authorization.
- Persistent restaurant directory with add/edit/archive and basic metadata.
- Automatic polls Monday–Friday, 08:00–11:30, excluding weekends; team-local timezone.
- Rank up to 3 restaurants by tapping, with search and a visible selection tray.
- Live ranked standings, named individual ballots, countdown, and final result.
- Historical results and basic restaurant win counts.
- Mobile-first, accessible responsive UX.

### Not in MVP

- Native iOS/Android apps; reservation booking; food delivery; paid plans; Slack/Teams integration; AI recommendations; restaurant scraping; dietary preference engine; complex holiday calendars; push/browser notifications (may be added after MVP); public anonymous polls.

## 3. Key design decisions and explicit assumptions

The following choices complete unspecified details and should be treated as MVP defaults, not as previously confirmed user preferences:

| Subject | MVP decision |
|---|---|
| Schedule | Weekdays Monday–Friday, opens 08:00, closes 11:30 in team timezone |
| Schedule configurability | Admin may change opening/closing times for future polls; default remains 08:00/11:30 |
| Eligible restaurants | All active saved restaurants are automatically snapshotted into each new poll |
| New restaurant during poll | Member may add it and it becomes eligible immediately in the open poll |
| Voting | 1–3 *distinct* restaurant choices in ranked order; partial ballot allowed |
| Ballot change | Re-submit until 11:30; latest submission replaces prior ballot atomically |
| Score | First = 3, second = 2, third = 1; highest total wins |
| Tie-breaking | Most first-place votes; then most second-place votes; then seeded deterministic random draw |
| Visibility | Members see live totals and other members' ranked choices, including names |
| Winner repetition | No cooldown/exclusion; prior winner is eligible again tomorrow |
| Zero ballots | Poll finalizes with `no_winner` and no winner ID |
| If fewer than 3 restaurants | Rank as many available as desired, minimum one to submit |
| Authentication | No anonymous voters; invited user signs in first |
| Restaurant recommendations | No external places API dependency in MVP; users enter restaurants manually |
| Weekends/holidays | No weekends, but public holidays are not automatically excluded |
| History | Polls and submitted ballots retained unless manually deleted under data retention policy |

**Important:** The scoring method is **positional ranked-points (Borda-style)**, not instant-runoff ranked-choice voting. The product can say “rank your top three”; avoid claiming instant-runoff or transferable-vote mechanics.

## 4. Main user journeys

### 4.1 First-time team setup

1. User signs in via Google or email magic link.
2. User creates team: name, IANA timezone (default guessed from browser, editable), optional office location text.
3. App creates team with creator as admin and generates a secure invitation URL.
4. Admin seeds restaurant list manually (name required, optional cuisine, address, URL, notes).
5. Admin shares invite URL with coworkers.
6. Invitee opens URL, signs in if necessary, and joins team; duplicate join is idempotent.
7. Dashboard shows today's poll state or the next scheduled opening.

### 4.2 Daily vote

1. At 08:00 team-local, poll transitions to `open` automatically.
2. Member visits team dashboard; sees countdown to 11:30, status, their current ranking, searchable restaurant list, live standings, and participation count.
3. Member searches/browses restaurants and taps one to assign rank 1; next tap assigns rank 2; next tap assigns rank 3.
4. Tapping a selected restaurant removes it, shifting later selections up without gaps. Member may use an explicit control within the small three-item selected tray to change ranking order (e.g., up/down arrows); **never require drag-and-drop**.
5. Member presses **Submit vote** to persist. Display confirmation, submission timestamp, and **Edit vote** affordance.
6. A re-submission replaces that member's ballot and updates live scores and named vote lists.
7. At 11:30 team-local, server finalizes winner; further submissions are rejected. Everyone sees the winner banner and final snapshot.
8. The day's result remains available in History.

### 4.3 Add a restaurant

1. Member chooses **Add restaurant** from directory or daily voting screen.
2. Member supplies name (required); optional address, cuisine/category, map/website URL, notes.
3. App validates, prevents obvious accidental duplicates (case-insensitive normalized name and, if supplied, address), and saves to team list.
4. When today's poll is open, newly added restaurant appears immediately as a candidate and in other members' live directories.
5. Existing ballots remain unchanged. Users can edit ballots to include new candidate.
6. Archiving removes the restaurant from future polls; for active poll, see snapshot rule below.

### 4.4 After closing

1. Dashboard says **Voting closed**, shows winning restaurant, vote totals, and individual votes.
2. History lists dates, winners/no-winner, ballot counts, and detailed scores.
3. Member can navigate to selected restaurant website/map link if provided.

## 5. Poll lifecycle and scheduling

### 5.1 Status values

- `scheduled`: Poll row exists for upcoming day but not open.
- `open`: Server accepts new/updated ballots when `opens_at <= now < closes_at`.
- `closed`: Poll is finalized, immutable; includes winner or `no_winner`.

### 5.2 Calendar and time

- Schedule per team based on valid **IANA timezone**, e.g. `Europe/Berlin` (do not store fixed UTC offsets).
- Team-local Monday–Friday only; do not create automatic polls for Saturday/Sunday.
- Compute `opens_at` and `closes_at` as UTC instants from local date/time, using timezone-aware library supporting DST.
- Closure boundary: **11:30:00 local exactly**; any ballot received at or after the boundary is rejected even if scheduler runs late.
- Poll opening and closing jobs should run at least once per minute and be **idempotent**. Treat server timestamp checks as the source of truth, not job execution timing or client clock.
- Run a daily replenishment job to ensure today's and tomorrow's eligible poll records exist. At minimum, create today's poll on first access if missed, with fixed opening and closing instants.
- If the service is down at poll time, recovery reconciliation must open/finalize correctly on next worker run.
- A user opening the app just before/after a boundary should receive canonical state from server, not stale UI.
- Timezone or schedule edits affect only **future not-yet-open polls**; keep active poll windows stable to avoid surprise mid-vote deadline changes.
- Multi-team polls operate independently.

### 5.3 Candidate snapshot rules

- At creation, copy IDs of active team restaurants to the poll candidate set. All active restaurants are initially eligible.
- New restaurants added while poll is open are inserted into its candidate set transactionally.
- Archiving a restaurant during an open poll **does not remove it from that day's candidates** or invalidate already submitted rankings; archive affects future polls. This preserves consistency and avoids silent vote changes.
- Archived restaurants must remain readable in historical data.
- If a restaurant is created after today's close, it appears beginning next eligible poll.
- Restaurant deletion should be soft delete/archive only in MVP.

## 6. Voting and ranking UX

### 6.1 Selection interactions

- Search field above a scrollable list. Search restaurant name/cuisine/address case-insensitively; debounce input (~150–250ms) if using server search.
- List shows name and optional cuisine/distance-neutral address snippet; do not fabricate walking time or distance without geolocation/routing data.
- A tap on an unselected restaurant adds it as the next available rank, up to 3.
- A tap on a selected restaurant removes it and compacts the remaining ranks.
- If 3 already selected, show non-disruptive instruction “Remove a choice to add another.” Do **not** silently replace a ranking.
- Top-three tray remains visible while browsing (sticky on small screens if feasible), with clear rank labels 1st / 2nd / 3rd and remove controls.
- Provide simple **move up / move down** controls in the tray to swap adjacent positions. Buttons must have accessible labels.
- After submission, show saved selection. User can reopen editing; unsaved changes must not be mistaken for a saved vote.
- Submit remains enabled for 1–3 selected choices while poll open; show in-progress state and deduplicate repeat clicks.
- Make it clear ballots are **public to team members** before first submission.

### 6.2 Browsing shortcuts

- **Recently chosen:** Restaurants that won most recently, ordered by win date.
- **Popular with team:** Restaurants with highest wins in last 30 eligible poll days, then all-time; computed from finalized history.
- **All restaurants:** Searchable alphabetic list. Avoid complicated recommendation algorithms in MVP.
- These are presentation/grouping aids, not eligibility filters; all active candidates remain available.

### 6.3 Live results

- Show numeric points, first-place vote counts for tie context, and bar graph proportionate to current max score.
- Sort descending by score, then first-place votes, then second-place votes, then stable alphabetic order **for display only**. Do not announce a final winner until close.
- Live view refreshes automatically via realtime subscription; reconnect and re-fetch on missed events.
- Show participating voter count / number of team members, plus timestamp if useful.
- Named ballots view displays coworker display name and ranked choices; this is only visible to members of the same team.
- After finalization, display final scores and tie-break explanation if relevant.

## 7. Scoring and tie-break algorithm

For each current valid ballot:

- Rank 1: 3 points.
- Rank 2: 2 points.
- Rank 3: 1 point.
- A missing rank earns no points; no redistribution or scaling is applied.
- A voter may select each restaurant at most once; all selected IDs must be candidates in the same poll.

For each candidate compute:

- `score = 3 * first_count + 2 * second_count + third_count`.
- Higher total score ranks ahead.
- For exact score ties at **finalization**, compare `first_count`; then `second_count`.
- If still tied, select one reproducibly using a server-generated random seed saved on poll creation and a deterministic tie-break function over sorted tied candidate IDs. This is a random selection but yields the same winner after retries; do not recompute randomness on a retry.
- Keep the original seed private to server write operations, but it need not be cryptographically secret.
- If zero submitted ballots, mark `no_winner` and do not apply random selection.
- If only one restaurant has votes, it wins; restaurants with zero votes remain in the candidate list and standings.

**Finalization transaction:** Lock poll row, verify effective close time, fetch authoritative ballots/candidates, recompute final scores from persisted ballots (not cached live totals), determine winner, persist final result/scores/status atomically, and emit a single logical finalization event. Repeated calls must be safe and not change the selected winner.

## 8. Data model (relational, PostgreSQL / Supabase)

Implement schema with UUID primary keys unless a different convention is already established. Include `created_at`, `updated_at` where relevant and indexes for frequent queries.

### 8.1 `profiles`

- `id` UUID PK, references auth.users.
- `display_name` text not null.
- `avatar_url` text nullable.
- `created_at`, `updated_at` timestamptz.

### 8.2 `teams`

- `id` UUID PK.
- `name` text not null.
- `timezone` text not null (IANA).
- `open_local_time` time not null default `08:00:00`.
- `close_local_time` time not null default `11:30:00`.
- `created_by` UUID references profiles.
- `created_at`, `updated_at`.
- Constraint open time < close time for same-day windows.

### 8.3 `team_members`

- `team_id` UUID FK teams.
- `user_id` UUID FK profiles.
- `role` enum (`admin`, `member`).
- `joined_at` timestamptz.
- Composite PK / unique (`team_id`, `user_id`).

### 8.4 `team_invites`

- `id` UUID PK.
- `team_id` UUID FK teams.
- `token_hash` text unique; store only hashed high-entropy token.
- `created_by` UUID FK profiles.
- `expires_at` timestamptz nullable (default 30 days).
- `revoked_at` timestamptz nullable.
- `created_at` timestamptz.
- Invites can be rotated or revoked by admin. An expired/revoked link cannot join.

### 8.5 `restaurants`

- `id` UUID PK.
- `team_id` UUID FK teams.
- `name` text not null.
- `normalized_name` text not null.
- `cuisine` text nullable.
- `address` text nullable.
- `website_url` text nullable.
- `map_url` text nullable.
- `notes` text nullable.
- `created_by` UUID FK profiles.
- `archived_at` timestamptz nullable.
- `created_at`, `updated_at`.
- Index (`team_id`, `archived_at`, `normalized_name`); enforce reasonable data lengths and URL schemes.
- Duplicate policy: warn or block obvious same normalized name + normalized address, but allow legitimate chains at different addresses.

### 8.6 `polls`

- `id` UUID PK.
- `team_id` UUID FK teams.
- `local_date` date not null.
- `opens_at` timestamptz not null.
- `closes_at` timestamptz not null.
- `status` enum (`scheduled`, `open`, `closed`) not null.
- `tie_seed` UUID or secure random bytes not null.
- `winner_restaurant_id` UUID nullable FK restaurants.
- `outcome` enum (`winner`, `no_winner`) nullable until closed.
- `finalized_at` timestamptz nullable.
- `created_at`, `updated_at`.
- Unique (`team_id`, `local_date`); check `opens_at < closes_at`.

### 8.7 `poll_candidates`

- `poll_id` UUID FK polls.
- `restaurant_id` UUID FK restaurants.
- `added_at` timestamptz.
- Primary key (`poll_id`, `restaurant_id`).
- Enforce candidate restaurant belongs to poll's team in trusted server operation / database function.

### 8.8 `ballots`

- `id` UUID PK.
- `poll_id` UUID FK polls.
- `user_id` UUID FK profiles.
- `submitted_at` timestamptz not null.
- `updated_at` timestamptz not null.
- Unique (`poll_id`, `user_id`).
- Server checks membership at submission.

### 8.9 `ballot_choices`

- `ballot_id` UUID FK ballots on delete cascade.
- `restaurant_id` UUID FK restaurants.
- `rank` smallint not null check `rank between 1 and 3`.
- Primary key (`ballot_id`, `rank`).
- Unique (`ballot_id`, `restaurant_id`).
- Server validates choices against poll_candidates and contiguous ranks.

### 8.10 `poll_final_scores` (optional but recommended)

- `poll_id` UUID FK polls.
- `restaurant_id` UUID FK restaurants.
- `score` integer not null.
- `first_count`, `second_count`, `third_count` integer not null.
- Primary key (`poll_id`, `restaurant_id`).
- Written only during finalization for auditability and immutable historical display.

## 9. Server operations and API contract

Use typed server actions / route handlers / RPC. Names below are illustrative; preserve semantics and authorization.

| Operation | Input | Output | Access / rules |
|---|---|---|---|
| `createTeam` | name, timezone | team | signed-in user; creator admin |
| `getMyTeams` | — | teams | signed-in user |
| `getTeam` | teamId | team, role, members | member only |
| `updateTeamSettings` | teamId, settings | team | admin only; future polls only |
| `createInvite` | teamId | invite URL | admin only |
| `revokeInvite` | inviteId | success | admin only |
| `joinTeam` | raw token | team membership | signed in, valid invite; idempotent |
| `listRestaurants` | teamId, search | restaurants | member only |
| `addRestaurant` | teamId, fields | restaurant | member only; inserts into open poll |
| `editRestaurant` | restaurantId, fields | restaurant | creator or admin; define consistent edit policy |
| `archiveRestaurant` | restaurantId | success | admin or creator; not removed from open poll |
| `getCurrentPoll` | teamId | poll, candidates, my ballot, results | member only |
| `submitBallot` | pollId, rankedRestaurantIds[1..3] | saved ballot | member; valid poll; before close; atomic replace |
| `getLiveResults` | pollId | scores, counts, named ballots | member only |
| `listPollHistory` | teamId, pagination | summaries | member only |
| `getPollHistory` | pollId | detail and finalized scores | member only |
| `leaveTeam` | teamId | success | member; prevent last admin departure until transfer |

### 9.1 Critical `submitBallot` transaction

Perform in backend transaction / security-definer database function with tightly limited permissions:

1. Resolve authenticated user from server-side auth context; never trust a `userId` supplied by client.
2. Verify user belongs to poll's team.
3. Lock/read poll and verify `now() >= opens_at AND now() < closes_at` and not finalized.
4. Validate 1–3 distinct restaurant UUIDs and membership in poll_candidates.
5. Upsert one ballot keyed by `(poll_id, user_id)`.
6. Replace choice rows with contiguous ranks in one transaction.
7. Commit and notify listeners; client refetches canonical result.

Protect against race at 11:30 by enforcing deadline in database/server, not UI alone. Use database time for deadline comparisons.

### 9.2 Realtime

- Subscribe to changes associated with the selected team/current poll, using Supabase Realtime or equivalent.
- Events of interest: candidate added, ballot submitted/updated, poll finalized.
- Client should refetch aggregated results on events instead of trusting client-supplied aggregate deltas.
- Debounce refresh if many votes arrive together.
- Unsubscribe on team/poll navigation; resume and fetch on reconnection or tab focus.
- All realtime channels and underlying tables must enforce team membership authorization.

## 10. Screens and components

### 10.1 Login / signup

- App name, brief explanation, Google login button, email magic-link form.
- Handle redirect back to invitation or selected team after authentication.
- Handle expired link, authentication error, loading, retry.

### 10.2 Team onboarding

- Create team (name, timezone).
- Join from invitation URL.
- Seed restaurants; skip option with explanatory empty state.
- Copy invite link; explicit confirmation of copy.

### 10.3 Today dashboard (primary)

- Team picker for users with multiple teams.
- Poll state banner: scheduled/open/closed.
- Countdown when open, computed from server-provided `closes_at`, displayed with client timer; server is authoritative.
- Selected top-three tray with rank numbers and move up/down/remove controls.
- Restaurant search, shortcuts (recently chosen/popular), all candidates.
- Add restaurant button.
- Submit / edit vote control and feedback.
- Live standings with score bars, named ballots, participants.
- Closed state winner banner (or no-winner message), final standings, map/website links.

### 10.4 Restaurant directory

- Searchable list of team restaurants.
- Add restaurant form; optional cuisine, address, website, map URL, notes.
- Edit and archive controls for authorized users.
- Archive action requires confirmation; archived entries visible in admin/history contexts.

### 10.5 History

- Reverse chronological polls; date, winner or no-winner, ballot count.
- Drill-down to immutable final score breakdown and named ballots as submitted at close.
- Restaurant win-count indicators and simple frequency information.

### 10.6 Team settings and members

- Team name, timezone, time schedule (defaults set), membership list, admin badge.
- Invite link creation, copy, revoke/regenerate.
- Admin membership management; member leave-team action.

## 11. UI/UX and accessibility

- Build **mobile-first** at 360px width; desktop supports 2-column layout (voting and live results).
- Avoid dragging, horizontal scrolling in critical content, and tiny tap targets.
- Minimum practical control target 44x44px for interactive voting controls.
- Keyboard-accessible buttons, visible focus states, semantic labels, ARIA live region for vote saved / poll finalized; do not constantly announce score fluctuations.
- Ensure WCAG AA contrast target; don't convey rank or status by color alone.
- Loading/skeleton states; no restaurants; no vote yet; no team; countdown ended; offline/reconnecting; error and retry states.
- Never show a false “vote saved” confirmation until server acknowledges persistence.
- Keep dates/times displayed in team timezone and show timezone name in settings.
- Distinguish **current leader** from **final winner**.
- Public-to-team vote visibility must be stated clearly in the voting UI.

## 12. Permissions, security, privacy

- Implement PostgreSQL RLS on all team-scoped tables. Nonmembers must not read teams, restaurants, polls, ballots, invitations or history.
- Members may read their team's named ballots and standings; only ballot owner may create/update their own ballot before deadline.
- Only admins update team settings, roles, invitations, and member list.
- Validate invite tokens by hash; expire and revoke tokens; use rate limits on joining and form endpoints.
- Validate and sanitize text, URL schemes (`https://` preferred), UUID types, length limits; avoid script injection.
- Never expose service-role/admin database credentials to browser.
- Protect scheduler endpoints with secret/service identity.
- Ensure team ID in route is checked against membership on every operation.
- Define deletion/retention policy before production launch. MVP: users can leave a team; historical ballot attribution remains for team transparency unless a deletion/anonymization workflow is implemented.
- Do not send named ballots to third-party analytics.

## 13. Recommended technology and repository structure

Preferred stack (not mandatory if an existing repository establishes another):

- Next.js App Router + TypeScript.
- Tailwind CSS + shadcn/ui components.
- Supabase Auth (Google OAuth, email magic links), PostgreSQL, RLS, Realtime.
- Vercel for frontend deployment.
- A secure scheduled worker / cron + server-side reconciliation for poll lifecycle.
- Zod for server input validation.
- Vitest for units, Playwright for end-to-end critical journeys.

Suggested layout:

```text
src/
  app/
    (auth)/login/
    teams/[teamId]/today/
    teams/[teamId]/restaurants/
    teams/[teamId]/history/
    teams/[teamId]/settings/
    invite/[token]/
    api/cron/reconcile-polls/
  components/
    voting/TopThreeTray.tsx
    voting/RestaurantPicker.tsx
    voting/LiveStandings.tsx
    voting/NamedBallots.tsx
    polls/PollStatus.tsx
    teams/TeamSwitcher.tsx
  lib/
    auth/
    database/
    polls/scoring.ts
    polls/scheduling.ts
    polls/finalize.ts
    validation/
  types/
supabase/
  migrations/
tests/
```

The agent should adapt names to established project conventions rather than create duplicate architectures.

## 14. Suggested implementation order

1. Set up app, migrations, environment templates, authentication, profiles.
2. Teams, membership, roles, invite links, RLS policy tests.
3. Restaurant directory, add/edit/archive, duplicate handling.
4. Poll scheduling, UTC windows, weekday logic, DST tests, recovery jobs.
5. Poll candidates and secure atomic ballot submission.
6. Top-three tap-to-rank UI, search, order adjustment, save/edit behavior.
7. Scoring and live result subscriptions; named ballots.
8. Server-side finalization, deterministic tie handling, history pages.
9. Accessibility, error states, responsive polish, integration/E2E tests, deployment.

## 15. Acceptance criteria / definition of done

### Membership and restaurants

- [ ] Signed-in coworker can create a team, invite others via link, and join a team.
- [ ] Team members can view a shared restaurant list and add entries.
- [ ] All active restaurants are available in each newly opened weekday poll.
- [ ] A restaurant added during an open poll becomes available without invalidating existing ballots.
- [ ] Archived restaurants remain visible in past poll results and are excluded from future polls.
- [ ] Nonmember cannot access team data or realtime streams.

### Voting UX

- [ ] Member can search among at least 100 candidates without dragging a long list.
- [ ] Tapping a restaurant fills 1st, then 2nd, then 3rd rank.
- [ ] Tapping a selected restaurant removes it and closes ranking gaps.
- [ ] Member can change order via accessible controls in the three-item tray.
- [ ] Member can submit a partial 1- or 2-choice vote.
- [ ] Four distinct choices cannot be submitted and duplicates cannot appear.
- [ ] Refresh restores last saved ballot; unsaved changes are not displayed as persisted.
- [ ] Resubmission before deadline updates scores without double-counting.

### Scheduling, scoring, finalization

- [ ] Every Monday–Friday local team day has one and only one poll, 08:00–11:30 by default.
- [ ] Saturday/Sunday have no automatic poll.
- [ ] At/after 11:30:00 local, ballot submission is rejected server-side.
- [ ] Score is exactly 3/2/1 for first/second/third choice.
- [ ] Tie handling follows first-place, then second-place, then deterministic seeded draw.
- [ ] Finalization retries preserve same winner and final scores.
- [ ] Zero-vote poll closes with no winner.
- [ ] DST transition and multiple timezones do not move local 08:00/11:30 boundaries.
- [ ] Missed cron run recovers without duplicate polls or changed results.

### Live results / history

- [ ] Team members see live standings and named ballots; other teams do not.
- [ ] Adding a candidate or updating a ballot refreshes other connected clients.
- [ ] A current leader is not mislabeled winner before poll close.
- [ ] History shows finalized winner/no-winner and score breakdown per date.

### Reliability and quality

- [ ] Automated tests cover scoring/ties, ballot replacement, deadline race, membership RLS and scheduling.
- [ ] End-to-end tests cover team creation, invitation, voting, editing, live refresh and closing.
- [ ] Usable on small mobile viewports and keyboard navigation.
- [ ] No keys or privileged Supabase role tokens exposed to client bundle.
- [ ] README explains local setup, env vars, migrations, auth redirect configuration, cron and deploy steps.

## 16. High-priority test cases

| Test | Expected behavior |
|---|---|
| A votes `[A,B,C]` | A +3, B +2, C +1 |
| A re-votes `[C,A]` | Old points removed; C +3, A +2 only |
| Two rapid concurrent submits by same user | One valid latest ballot; never duplicate |
| Submit at 11:29:59.999 local | Accepted if authoritative transaction check precedes close |
| Submit at 11:30:00 local | Rejected |
| Finalize twice | Winner and final scores identical |
| All candidates tied by points/firsts/seconds | Seeded deterministic selection |
| No votes | Closed, `no_winner` |
| New restaurant during open poll | Available immediately; existing ballots unchanged |
| Archive restaurant in open poll | Still eligible that day; excluded future polls |
| User in Team A tries Team B poll | Forbidden |
| DST switches in Europe/Berlin | Local opening/closing remain 08:00/11:30 |
| App returns after worker outage | Reconciliation sets correct canonical poll state |
| One candidate only | A valid one-choice ballot can select that candidate |
| Reconnect after offline period | Current results and saved ballot are fetched again |

## 17. Potential follow-on features (not part of initial build)

- Slack/Teams reminders and result posts.
- Browser push notifications.
- Restaurant discovery/maps integration and travel time.
- Office location and per-office restaurant pools.
- Dietary constraints and explicit vetoes.
- Holiday calendar and vacation-aware participation.
- Advanced fairness features (anti-repeat rotation, participation weighting).
- Reservations and group ordering integrations.
- More sophisticated alternative voting rules, clearly labeled and opt-in.

## 18. Coding agent delivery instructions

**Implement the MVP described above, not a static prototype.** Use real authentication, database persistence, transactional ballot writes, authorized real-time updates, and server-enforced lifecycle. Prioritize correct daily scheduling and voting integrity over optional visual effects. Write database migrations, authorization policies, unit/integration/E2E tests and a deployable README. Where a minor detail is unaddressed, choose the simplest secure default, document it in README, and avoid adding out-of-scope functionality.
