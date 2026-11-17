
-- Profiles
create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null default '',
  created_at timestamptz not null default now()
);
grant select, insert, update on public.profiles to authenticated;
grant all on public.profiles to service_role;
alter table public.profiles enable row level security;

create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name', split_part(new.email,'@',1)))
  on conflict (id) do nothing;
  return new;
end $$;
create trigger on_auth_user_created after insert on auth.users
for each row execute function public.handle_new_user();

-- Teams
create table public.teams (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(trim(name)) between 1 and 80),
  timezone text not null default 'Europe/Berlin',
  office_location text,
  open_time time not null default '08:00',
  close_time time not null default '11:30',
  created_by uuid not null,
  created_at timestamptz not null default now()
);
grant select, update on public.teams to authenticated;
grant all on public.teams to service_role;
alter table public.teams enable row level security;

create or replace function public.validate_team()
returns trigger language plpgsql set search_path = public as $$
begin
  if not exists (select 1 from pg_timezone_names where name = new.timezone) then
    raise exception 'Invalid timezone: %', new.timezone;
  end if;
  if new.open_time >= new.close_time then
    raise exception 'Opening time must be before closing time';
  end if;
  return new;
end $$;
create trigger teams_validate before insert or update on public.teams
for each row execute function public.validate_team();

create table public.team_members (
  team_id uuid not null references public.teams(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  role text not null default 'member' check (role in ('admin','member')),
  joined_at timestamptz not null default now(),
  primary key (team_id, user_id)
);
grant select, update, delete on public.team_members to authenticated;
grant all on public.team_members to service_role;
alter table public.team_members enable row level security;

create or replace function public.is_team_member(_team uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.team_members where team_id = _team and user_id = auth.uid())
$$;
create or replace function public.is_team_admin(_team uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.team_members where team_id = _team and user_id = auth.uid() and role = 'admin')
$$;
create or replace function public.shares_team(_user uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.team_members a join public.team_members b on a.team_id = b.team_id
                 where a.user_id = auth.uid() and b.user_id = _user)
$$;

create policy "profiles readable by self and teammates" on public.profiles for select to authenticated
  using (id = auth.uid() or public.shares_team(id));
create policy "profiles insert self" on public.profiles for insert to authenticated with check (id = auth.uid());
create policy "profiles update self" on public.profiles for update to authenticated using (id = auth.uid()) with check (id = auth.uid());

create policy "teams readable by members" on public.teams for select to authenticated using (public.is_team_member(id));
create policy "teams updatable by admins" on public.teams for update to authenticated using (public.is_team_admin(id)) with check (public.is_team_admin(id));

create policy "members readable by teammates" on public.team_members for select to authenticated using (public.is_team_member(team_id));
create policy "admins update members" on public.team_members for update to authenticated using (public.is_team_admin(team_id)) with check (public.is_team_admin(team_id));
create policy "leave or admin remove" on public.team_members for delete to authenticated using (user_id = auth.uid() or public.is_team_admin(team_id));

-- Invites
create table public.team_invites (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null references public.teams(id) on delete cascade,
  token text not null unique default replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''),
  created_by uuid,
  created_at timestamptz not null default now(),
  revoked_at timestamptz
);
grant select, update on public.team_invites to authenticated;
grant all on public.team_invites to service_role;
alter table public.team_invites enable row level security;
create policy "admins read invites" on public.team_invites for select to authenticated using (public.is_team_admin(team_id));
create policy "admins revoke invites" on public.team_invites for update to authenticated using (public.is_team_admin(team_id)) with check (public.is_team_admin(team_id));

-- Restaurants
create table public.restaurants (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null references public.teams(id) on delete cascade,
  name text not null check (char_length(trim(name)) between 1 and 100),
  normalized_name text generated always as (lower(regexp_replace(trim(name), '\s+', ' ', 'g'))) stored,
  cuisine text,
  address text,
  website_url text,
  map_url text,
  notes text,
  created_by uuid,
  created_at timestamptz not null default now(),
  archived_at timestamptz
);
create unique index restaurants_unique_active on public.restaurants
  (team_id, normalized_name, lower(coalesce(trim(address), ''))) where archived_at is null;
grant select, insert, update on public.restaurants to authenticated;
grant all on public.restaurants to service_role;
alter table public.restaurants enable row level security;
create policy "members read restaurants" on public.restaurants for select to authenticated using (public.is_team_member(team_id));
create policy "members add restaurants" on public.restaurants for insert to authenticated
  with check (public.is_team_member(team_id) and created_by = auth.uid() and archived_at is null);
create policy "admins or creators edit restaurants" on public.restaurants for update to authenticated
  using (public.is_team_admin(team_id) or created_by = auth.uid())
  with check (public.is_team_admin(team_id) or created_by = auth.uid());

-- Polls
create table public.polls (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null references public.teams(id) on delete cascade,
  poll_date date not null,
  timezone text not null,
  opens_at timestamptz not null,
  closes_at timestamptz not null,
  status text not null default 'scheduled' check (status in ('scheduled','open','closed')),
  winner_id uuid references public.restaurants(id),
  no_winner boolean not null default false,
  ballot_count int,
  final_scores jsonb,
  tie_break text,
  finalized_at timestamptz,
  created_at timestamptz not null default now(),
  unique (team_id, poll_date)
);
grant select on public.polls to authenticated;
grant all on public.polls to service_role;
alter table public.polls enable row level security;
create policy "members read polls" on public.polls for select to authenticated using (public.is_team_member(team_id));

create table public.poll_seeds (
  poll_id uuid primary key references public.polls(id) on delete cascade,
  seed text not null
);
grant all on public.poll_seeds to service_role;
alter table public.poll_seeds enable row level security;

create table public.poll_candidates (
  poll_id uuid not null references public.polls(id) on delete cascade,
  restaurant_id uuid not null references public.restaurants(id),
  team_id uuid not null,
  primary key (poll_id, restaurant_id)
);
grant select on public.poll_candidates to authenticated;
grant all on public.poll_candidates to service_role;
alter table public.poll_candidates enable row level security;
create policy "members read candidates" on public.poll_candidates for select to authenticated using (public.is_team_member(team_id));

create table public.ballots (
  poll_id uuid not null references public.polls(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  team_id uuid not null,
  choices uuid[] not null check (array_length(choices, 1) between 1 and 3),
  submitted_at timestamptz not null default now(),
  primary key (poll_id, user_id)
);
grant select on public.ballots to authenticated;
grant all on public.ballots to service_role;
alter table public.ballots enable row level security;
create policy "members read ballots" on public.ballots for select to authenticated using (public.is_team_member(team_id));

-- Finalize poll (idempotent)
create or replace function public.finalize_poll(_poll uuid)
returns void language plpgsql security definer set search_path = public as $$
declare
  p public.polls%rowtype;
  s text;
  n int;
  scores jsonb;
  w uuid;
  tb text := null;
  top record;
  c1 int; c2 int; c3 int;
begin
  select * into p from public.polls where id = _poll for update;
  if not found or p.status = 'closed' or now() < p.closes_at then return; end if;
  select seed into s from public.poll_seeds where poll_id = _poll;
  select count(*) into n from public.ballots where poll_id = _poll;

  with sc as (
    select c.restaurant_id, r.name,
      count(b.*) filter (where b.choices[1] = c.restaurant_id) as f,
      count(b.*) filter (where b.choices[2] = c.restaurant_id) as sec,
      count(b.*) filter (where b.choices[3] = c.restaurant_id) as t
    from public.poll_candidates c
    join public.restaurants r on r.id = c.restaurant_id
    left join public.ballots b on b.poll_id = _poll
    where c.poll_id = _poll
    group by c.restaurant_id, r.name
  ), ranked as (
    select *, 3*f + 2*sec + t as score, md5(coalesce(s,'') || restaurant_id::text) as draw from sc
  )
  select coalesce(jsonb_agg(jsonb_build_object('restaurant_id', restaurant_id, 'name', name, 'score', score,
           'first', f, 'second', sec, 'third', t) order by score desc, f desc, sec desc, draw), '[]'::jsonb)
  into scores from ranked;

  if n > 0 then
    w := (scores->0->>'restaurant_id')::uuid;
    select count(*) filter (where (e->>'score')::int = (scores->0->>'score')::int),
           count(*) filter (where (e->>'score')::int = (scores->0->>'score')::int and (e->>'first')::int = (scores->0->>'first')::int),
           count(*) filter (where (e->>'score')::int = (scores->0->>'score')::int and (e->>'first')::int = (scores->0->>'first')::int and (e->>'second')::int = (scores->0->>'second')::int)
      into c1, c2, c3 from jsonb_array_elements(scores) e;
    if c1 > 1 then
      tb := case when c2 = 1 then 'first_place_votes' when c3 = 1 then 'second_place_votes' else 'random_draw' end;
    end if;
  end if;

  update public.polls set status = 'closed', winner_id = w, no_winner = (n = 0), ballot_count = n,
    final_scores = scores, tie_break = tb, finalized_at = now()
  where id = _poll;
end $$;

-- Ensure today's poll exists and lifecycle is reconciled
create or replace function public.ensure_today_poll(_team uuid)
returns uuid language plpgsql security definer set search_path = public as $$
declare
  t public.teams%rowtype;
  local_now timestamp;
  d date;
  pid uuid;
  r record;
begin
  if auth.uid() is not null and not public.is_team_member(_team) then
    raise exception 'Not a member of this team';
  end if;
  select * into t from public.teams where id = _team;
  if not found then return null; end if;

  for r in select id from public.polls where team_id = _team and status <> 'closed' and closes_at <= now() loop
    perform public.finalize_poll(r.id);
  end loop;

  local_now := now() at time zone t.timezone;
  d := local_now::date;
  if extract(isodow from d) > 5 then return null; end if;

  insert into public.polls (team_id, poll_date, timezone, opens_at, closes_at)
  values (_team, d, t.timezone, (d + t.open_time) at time zone t.timezone, (d + t.close_time) at time zone t.timezone)
  on conflict (team_id, poll_date) do nothing
  returning id into pid;

  if pid is not null then
    insert into public.poll_seeds (poll_id, seed) values (pid, replace(gen_random_uuid()::text, '-', ''));
    insert into public.poll_candidates (poll_id, restaurant_id, team_id)
      select pid, id, _team from public.restaurants where team_id = _team and archived_at is null;
  else
    select id into pid from public.polls where team_id = _team and poll_date = d;
  end if;

  update public.polls set status = 'open' where id = pid and status = 'scheduled' and opens_at <= now() and now() < closes_at;
  if (select closes_at from public.polls where id = pid) <= now() then
    perform public.finalize_poll(pid);
  end if;
  return pid;
end $$;

create or replace function public.reconcile_all_polls()
returns void language plpgsql security definer set search_path = public as $$
declare r record;
begin
  for r in select id from public.teams loop perform public.ensure_today_poll(r.id); end loop;
end $$;
revoke execute on function public.reconcile_all_polls() from public, anon, authenticated;
revoke execute on function public.finalize_poll(uuid) from public, anon;

-- New restaurants join any not-yet-closed poll
create or replace function public.add_restaurant_to_open_polls()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.poll_candidates (poll_id, restaurant_id, team_id)
  select id, new.id, new.team_id from public.polls
  where team_id = new.team_id and status <> 'closed' and closes_at > now()
  on conflict do nothing;
  return new;
end $$;
create trigger restaurants_join_open_polls after insert on public.restaurants
for each row execute function public.add_restaurant_to_open_polls();

-- Submit ballot
create or replace function public.submit_ballot(_poll uuid, _choices uuid[])
returns timestamptz language plpgsql security definer set search_path = public as $$
declare p public.polls%rowtype; ts timestamptz := now();
begin
  select * into p from public.polls where id = _poll;
  if not found or not public.is_team_member(p.team_id) then raise exception 'Poll not found'; end if;
  if p.status = 'closed' or ts < p.opens_at or ts >= p.closes_at then raise exception 'Voting is closed'; end if;
  if coalesce(array_length(_choices, 1), 0) not between 1 and 3 then raise exception 'Pick between 1 and 3 restaurants'; end if;
  if (select count(distinct x) from unnest(_choices) x) <> array_length(_choices, 1) then raise exception 'Each restaurant can only be picked once'; end if;
  if (select count(*) from public.poll_candidates where poll_id = _poll and restaurant_id = any(_choices)) <> array_length(_choices, 1) then
    raise exception 'Choice is not in today''s poll';
  end if;
  insert into public.ballots (poll_id, user_id, team_id, choices, submitted_at)
  values (_poll, auth.uid(), p.team_id, _choices, ts)
  on conflict (poll_id, user_id) do update set choices = excluded.choices, submitted_at = excluded.submitted_at;
  update public.polls set status = 'open' where id = _poll and status = 'scheduled';
  return ts;
end $$;

-- Team creation & joining
create or replace function public.create_team(_name text, _timezone text, _office text default null)
returns uuid language plpgsql security definer set search_path = public as $$
declare tid uuid;
begin
  if auth.uid() is null then raise exception 'Not signed in'; end if;
  insert into public.profiles (id) values (auth.uid()) on conflict do nothing;
  insert into public.teams (name, timezone, office_location, created_by) values (trim(_name), _timezone, nullif(trim(_office), ''), auth.uid()) returning id into tid;
  insert into public.team_members (team_id, user_id, role) values (tid, auth.uid(), 'admin');
  insert into public.team_invites (team_id, created_by) values (tid, auth.uid());
  return tid;
end $$;

create or replace function public.invite_info(_token text)
returns table (team_id uuid, team_name text, already_member boolean)
language sql stable security definer set search_path = public as $$
  select t.id, t.name, public.is_team_member(t.id) from public.team_invites i join public.teams t on t.id = i.team_id
  where i.token = _token and i.revoked_at is null
$$;

create or replace function public.join_team(_token text)
returns uuid language plpgsql security definer set search_path = public as $$
declare tid uuid;
begin
  if auth.uid() is null then raise exception 'Not signed in'; end if;
  select team_id into tid from public.team_invites where token = _token and revoked_at is null;
  if tid is null then raise exception 'This invite link is invalid or has been revoked'; end if;
  insert into public.profiles (id) values (auth.uid()) on conflict do nothing;
  insert into public.team_members (team_id, user_id) values (tid, auth.uid()) on conflict do nothing;
  return tid;
end $$;

create or replace function public.regenerate_invite(_team uuid)
returns text language plpgsql security definer set search_path = public as $$
declare tok text;
begin
  if not public.is_team_admin(_team) then raise exception 'Admins only'; end if;
  update public.team_invites set revoked_at = now() where team_id = _team and revoked_at is null;
  insert into public.team_invites (team_id, created_by) values (_team, auth.uid()) returning token into tok;
  return tok;
end $$;

revoke execute on all functions in schema public from anon;

alter publication supabase_realtime add table public.ballots, public.restaurants, public.polls, public.poll_candidates;
