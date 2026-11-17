# Where Should We Eat? — HTTP API

`openapi.yaml` (OpenAPI 3.1) is the contract for the backend. The web app, a future CLI and AI agents all use it, and every UI action has an operation.

Validate:

```sh
npx --yes @redocly/cli lint api/openapi.yaml           # valid, 4 warnings (see below)
npx --yes @apidevtools/swagger-cli validate api/openapi.yaml   # valid
```

The remaining Redocly warnings are deliberate. There is no `info.license` because no license has been chosen. The servers are a placeholder `https://api.example.com` and `localhost` (two warnings), because no deployment URL exists yet. `TeamEvent` is never referenced: it documents the JSON in the SSE `data:` lines, and OpenAPI 3.1 has no way to attach a schema to individual SSE frames.

## Design principles

- **API first, no UI-only behaviour.** The server owns everything the mock or the UI used to decide: poll status, candidate snapshots, scoring, tie-breaks, finalization, permissions and timezone handling. The UI no longer needs `scoring.tally`, because standings come back already computed.
- **REST under `/v1`.** Team data is nested under `/v1/teams/{teamId}`. IDs are UUIDs, field names are `snake_case`, timestamps are UTC instants, and `poll_date` is a team-local date. Polls also carry `timezone`, `opens_at` and `closes_at`.
- **Agent friendly.** Every operation has an `operationId`, a summary, a description with an **authorization line** (Public / Authenticated / Member / Admin) and examples. Errors use one shape: RFC 9457 `application/problem+json` with a stable `code`. The codes are `unauthenticated`, `invalid_credentials`, `email_taken`, `validation_failed`, `not_found`, `not_a_member`, `admins_only`, `forbidden`, `invite_invalid`, `last_admin`, `duplicate_restaurant`, `invalid_candidate`, `poll_not_open`, `poll_closed`, `poll_not_closable`, `precondition_failed`, `idempotency_key_reused`, `rate_limited`, `unavailable` and `internal_error`.
- **Safe retries.**
  - `PUT` and `DELETE` are idempotent. `PUT .../ballots/me` replaces the ballot.
  - Joining via an invite is idempotent and returns `200` with `joined: false` if you are already a member.
  - Finalizing is idempotent and always gives the same winner.
  - `POST` creates accept an optional `Idempotency-Key`.
  - Teams and restaurants return an `ETag`, and `PATCH` accepts an optional `If-Match`.
- **Pagination only where lists grow without limit.** That is poll history (`listPolls`, cursor based). Restaurants, members and ballots are limited by team size.
- **Realtime.** `GET /v1/teams/{teamId}/events` is an SSE stream of typed change events: `poll.*`, `ballot.*`, `restaurant.*`, `member.*`, `team.updated`, `invite.changed` and `resync`. A client resumes with `Last-Event-ID`. Events are hints to re-fetch; they are not the source of truth.

## Auth model

- **Session token.** Today you sign up or sign in with email and password, as the app does now. The response contains `{access_token, expires_at, user}` and also sets an `HttpOnly` cookie `wswe_session` so browsers and `EventSource` work. Cookie-authenticated writes require a same-origin `Origin` header. Sessions last **30 days, sliding**: every use renews them. There is no refresh endpoint, and `expires_at` is the expiry as of sign-in.
- **Personal API tokens** (`wswe_pat_…`) are for CLIs and agents. You create them with `createApiToken` (the secret is shown once), list them with `listApiTokens` and revoke them with `revokeApiToken`. A token acts as its creator, with the same team roles. It also has **scopes** `read` and/or `write` (default both; no per-team restriction).
  - Each operation declares its scope in `security` (`bearerAuth: [read]` for GETs and the event stream, `bearerAuth: [write]` for everything else).
  - A missing scope gets `403 insufficient_scope`.
  - Managing tokens and signing out require a session, not an API token.
  - Sessions and cookies have both scopes.
- **CORS** uses a configurable allowlist of origins (the web app by default). Third-party browser clients use bearer tokens, so they need no cookies or credentials. CORS does not affect the CLI or agents.
- Both token types are sent as `Authorization: Bearer …`. Magic-link and Google OAuth (in the spec) can be added later as further ways to get a session token; no other endpoint changes.

## Frontend call → API operation

| mock-backend call | operationId | HTTP |
|---|---|---|
| `auth.signUp` | `signUp` | `POST /v1/auth/sign-up` |
| `auth.signIn` | `signIn` | `POST /v1/auth/sign-in` |
| `auth.signOut` | `signOut` | `POST /v1/auth/sign-out` |
| `auth.getUser` / `auth.getSession` | `getCurrentUser` | `GET /v1/me` (`401` = no session) |
| `auth.onChange` | — (client-side: token storage plus handling `401`) | — |
| `teams.mine` | `listMyTeams` | `GET /v1/me/teams` |
| `teams.get` | `getTeam` (+ `getTeamInvite` for the token) | `GET /v1/teams/{teamId}` (+ `GET …/invite`) |
| `teams.create` | `createTeam` | `POST /v1/teams` |
| `teams.members` | `listMembers` | `GET /v1/teams/{teamId}/members` |
| `teams.inviteInfo` | `getInviteInfo` | `GET /v1/invites/{inviteToken}` |
| `teams.join` | `joinTeam` | `POST /v1/invites/{inviteToken}/accept` |
| `teams.regenerateInvite` | `regenerateTeamInvite` | `POST /v1/teams/{teamId}/invite/regenerate` |
| `restaurants.list` | `listRestaurants` (`?status=all` matches the mock) | `GET /v1/teams/{teamId}/restaurants` |
| `restaurants.add` | `createRestaurant` | `POST /v1/teams/{teamId}/restaurants` |
| `restaurants.setArchived(id, true/false)` | `archiveRestaurant` / `unarchiveRestaurant` | `POST …/restaurants/{id}/archive` / `/unarchive` |
| `polls.today` | `getCurrentPoll` | `GET /v1/teams/{teamId}/polls/current` |
| `polls.submitBallot` | `submitBallot` | `PUT /v1/teams/{teamId}/polls/{pollId}/ballots/me` |
| `polls.closed` (`useClosedPolls`, currently unused by any route) | `listPolls` (`status=closed` is the default) | `GET /v1/teams/{teamId}/polls` |
| `onDataChange` / `useTeamRealtime` | `streamTeamEvents` | `GET /v1/teams/{teamId}/events` (SSE) |
| `scoring.tally` (client) | `getCurrentPoll.standings` / `getPollStandings` | `GET …/polls/{pollId}/standings` |

**Added for spec parity and for non-UI clients:**

- `getHealth`
- `updateCurrentUser` (display name)
- API tokens: `listApiTokens`, `createApiToken`, `revokeApiToken`
- `updateTeam` (name, timezone, office, open and close times)
- Members: `updateMemberRole`, `removeMember`, `leaveTeam`
- Invites: `getTeamInvite`, `revokeTeamInvite`
- Restaurants: `getRestaurant`, `updateRestaurant`, `unarchiveRestaurant`
- Polls: `getPoll`, `getPollByDate`, `getPollStandings`, `finalizePoll`
- Ballots: `listBallots`, `getMyBallot`, `deleteMyBallot`
- `getRestaurantStats`

That makes **40 operations** in total.

### Behaviour changes compared with the mock (the client must adapt)

- **Poll date.** The mock uses the UTC date for "today". The API uses the team-local date and real `opens_at` / `closes_at` instants. The mock never closes a poll; the API moves polls through `scheduled → open → closed` and finalizes them on the server.
- **Candidates.** The poll returns `candidates` as `{id, name, archived}` snapshots instead of `candidateIds`, so the client no longer intersects them with the restaurant list.
- **Final scores.** `final_scores` is now an array of `Standing` with `score`, `first_count`, `second_count`, `third_count` and `position`. The mock used `Record<id, number>`, and the client fields `first/second/third` were renamed to `*_count`.
- **Invite token.** `invite_token` is no longer part of `Team`. It comes from `getTeamInvite`.
- **Membership checks.** The mock checks membership nowhere: anyone can read any team, and `teams.get` returns `null` when the team is missing. The API returns `403 not_a_member`.
- **Starter restaurants are gone from the API.** The mock seeds the Berlin Friedrichstraße list on `teams.create` and lazily on `restaurants.list`. In the API, new teams always start with an **empty** restaurant list, and no endpoint or flag seeds them. The list in `frontend/src/lib/seed-restaurants.ts` is only for seeding the local dev/test database, through a dev seed script (for example a `seed` command run against the local DB), never through API endpoints.
- **Errors.** The UI currently shows `err.message`. It should show `problem.detail ?? problem.title` and branch on `code`.

## Decisions

Items 1–11 are my calls, for review. Items 12–17 were decided by the user.

1. **Who can edit or archive a restaurant.** I chose admins plus the member who created it. The spec says admins only for edit/archive "any", and the current UI lets every member archive.
2. **Invite visibility.** Any member can read the invite link (`getTeamInvite`), as the mock does today. Revoking and regenerating it is admin-only.
3. **Non-members get `403 not_a_member`**, not `404`. This follows spec test case "User in Team A tries Team B poll → Forbidden".
4. **Ballot rule errors.** A submission outside the voting window gets `409 poll_not_open` or `409 poll_closed`. A bad ballot gets `422 validation_failed` or `422 invalid_candidate`.
5. **`finalizePoll` is callable by any member.** It is safe because it never closes a poll early and gives a deterministic result. Reads also finalize lazily.
6. **`deleteMyBallot` (withdrawing a vote)** is an addition the spec does not mention.
7. **Leaving or being removed during an open poll** keeps that member's ballot counted. Their past ballots stay in history.
8. **The last admin cannot leave or be demoted** while other members remain (`409 last_admin`).
9. **Poll weekdays are read-only** (Monday–Friday). Only `open_time` and `close_time` are editable, and changes apply to polls that have not opened yet.
10. **`getCurrentPoll` never returns 404.** On a non-poll day it returns the next scheduled poll.
11. **Member emails are not exposed to teammates.** They see only `display_name`, which is now editable and defaults to the part of the email before the `@`.
12. **Sessions** last 30 days with a sliding expiry that renews on use. There is no refresh endpoint.
13. **API token scopes** are `read` and `write`, with no per-team restriction. They are declared per operation in `security`.
14. **No team deletion and no ownership transfer** in the MVP. Admins can promote and demote other admins (`updateMemberRole`), so a team always keeps at least one admin.
15. **No starter-restaurant seeding in the API.** New teams are empty. `seed-restaurants.ts` is used only by a dev/test DB seed script.
16. **Servers.** There is a placeholder `https://api.example.com` plus `localhost`. CORS is a configurable origin allowlist, and bearer auth means cross-origin clients need no cookies or credentials.
17. **Restaurant renames.** A poll snapshots candidate **IDs** and reads names live. An open or scheduled poll shows a new name immediately; a closed poll keeps the name frozen at close in `candidates` and `final_scores`.

## Open questions

None at the moment. All earlier questions are settled in Decisions above.
