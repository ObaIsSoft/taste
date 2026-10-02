-- TASTE engine v2 voting schema. A fresh start: the v1 tables are dropped.
-- Apply only when the v1 voting site is retired, because it reads those tables.
--
-- The voting rules live here, in one place: who may vote on what (served-pair
-- tokens), what a valid vote is (constraints and cast_vote), and which pair a
-- voter sees next (next_pair). The API is a thin layer over these functions.
-- Votes are stored exactly as cast; the agreement views line them up.

begin;

drop table if exists match_history cascade;
drop table if exists ratings cascade;
drop table if exists voters cascade;

create extension if not exists pgcrypto;

create type round_kind as enum ('visual', 'motion');
create type vote_outcome as enum (
  'left', 'right', 'equally_good', 'cant_decide', 'broken_left', 'broken_right'
);

-- One row of voting parameters, read by the functions below and by the API.
create table voting_config (
  id boolean primary key default true check (id),
  min_reason_chars integer not null default 10 check (min_reason_chars > 0),
  max_dimensions integer not null default 3 check (max_dimensions > 0),  -- chips per vote
  reason_every integer not null default 3 check (reason_every > 0),  -- ask for a reason on 1 in N
  repeat_count integer not null default 10 check (repeat_count >= 0),  -- swapped repeats per voter
  overlap_share numeric not null default 0.1 check (overlap_share between 0 and 1),
  min_vote_seconds numeric not null default 3,  -- faster votes are flagged as low effort
  resume_minutes integer not null default 60  -- an unanswered pair is served again within this
);
insert into voting_config default values;

create table sites (
  id integer primary key,
  url text not null unique,
  cohort text not null check (cohort in ('award', 'generated', 'ordinary')),
  category text,
  created_at timestamptz not null default now()
);

create table captures (
  id text primary key,  -- e.g. 0001-original
  site_id integer not null references sites (id),
  variant text not null,
  capture_version text not null,
  qa_passed boolean not null,
  qa_note text,
  stills text[] not null check (cardinality(stills) > 0),  -- storage paths, hero first
  reel_path text,
  final_url text,
  features jsonb,
  description jsonb,
  in_pool boolean not null default false,  -- may be served to voters
  updated_at timestamptz not null default now()
);
create index captures_in_pool on captures (in_pool) where in_pool;

create table dimensions (
  id text primary key,
  label text not null,
  round round_kind not null,
  position integer not null,
  unique (round, position)
);
insert into dimensions (id, label, round, position) values
  ('whitespace', 'Whitespace', 'visual', 1),
  ('typography', 'Typography', 'visual', 2),
  ('colour', 'Colour', 'visual', 3),
  ('layout', 'Grid and layout', 'visual', 4),
  ('imagery', 'Texture and imagery', 'visual', 5),
  ('cohesion', 'Overall cohesion', 'visual', 6),
  ('smoothness', 'Smoothness', 'motion', 1),
  ('pacing', 'Pacing', 'motion', 2),
  ('intro_wait', 'Intro wait', 'motion', 3),
  ('scroll_feel', 'Scroll feel', 'motion', 4),
  ('feedback', 'Hover and click feedback', 'motion', 5),
  ('motion_cohesion', 'Overall motion', 'motion', 6);

create table voters (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  invite_code text not null unique,  -- given to the designer out of band; acts as their key
  active boolean not null default true,
  created_at timestamptz not null default now()
);

-- Fixed sets every voter judges, so agreement and transitivity can be measured.
create table calibration_pairs (
  id serial primary key,
  round round_kind not null,
  capture_a text not null references captures (id),
  capture_b text not null references captures (id),
  check (capture_a < capture_b),
  unique (round, capture_a, capture_b)
);

create table served_pairs (
  token uuid primary key default gen_random_uuid(),
  voter_id uuid not null references voters (id),
  round round_kind not null,
  left_capture text not null references captures (id),
  right_capture text not null references captures (id),
  source text not null check (source in ('calibration', 'repeat', 'overlap', 'adaptive')),
  reason_requested boolean not null,
  served_at timestamptz not null default now(),
  used_at timestamptz,
  check (left_capture <> right_capture)
);
create index served_pairs_open on served_pairs (voter_id, round, served_at) where used_at is null;

create table votes (
  id bigserial primary key,
  token uuid not null unique references served_pairs (token),
  voter_id uuid not null references voters (id),
  round round_kind not null,
  left_capture text not null references captures (id),
  right_capture text not null references captures (id),
  pair_low text generated always as (least(left_capture, right_capture)) stored,
  pair_high text generated always as (greatest(left_capture, right_capture)) stored,
  outcome vote_outcome not null,
  dimensions text[] not null default '{}',
  reason text,
  seconds_to_vote numeric not null,
  created_at timestamptz not null default now(),
  check (left_capture <> right_capture)
);
create index votes_pair on votes (round, pair_low, pair_high);
create index votes_voter on votes (voter_id, round);

-- What a voter looked at: reels played and live sites opened. Motion reasons
-- are only trusted when the reels were actually played.
create table vote_events (
  id bigserial primary key,
  token uuid not null references served_pairs (token),
  kind text not null check (kind in ('play_left', 'play_right', 'open_live_left', 'open_live_right')),
  at timestamptz not null default now()
);

alter table voting_config enable row level security;
alter table sites enable row level security;
alter table captures enable row level security;
alter table dimensions enable row level security;
alter table voters enable row level security;
alter table calibration_pairs enable row level security;
alter table served_pairs enable row level security;
alter table votes enable row level security;
alter table vote_events enable row level security;
-- No policies: only the server, using the service key, reads or writes these tables.

-- Whether a capture may be shown in a round: in the pool, and with a reel for motion.
create function servable(c captures, p_round round_kind) returns boolean
language sql stable as $$
  select c.in_pool and (p_round = 'visual' or c.reel_path is not null)
$$;

-- Calibration pairs that can be served now. A capture taken out of the pool, for example
-- reported broken, leaves every voter's calibration set.
create view open_calibration_pairs with (security_invoker = true) as
select cp.*
  from calibration_pairs cp
  join captures ca on ca.id = cp.capture_a
  join captures cb on cb.id = cp.capture_b
 where servable(ca, cp.round) and servable(cb, cp.round);

-- Agreement. A verdict says which capture of a pair is better, whatever side each was shown
-- on: 'low' or 'high' (pair_low or pair_high), 'tie' (equally good), 'unsure' (can't decide)
-- or 'broken'.
create view vote_verdicts with (security_invoker = true) as
select v.id, v.voter_id, v.round, v.pair_low, v.pair_high, s.source,
       case
         when v.outcome in ('left', 'right') then
           case when (v.outcome = 'left') = (v.left_capture = v.pair_low) then 'low' else 'high' end
         when v.outcome = 'equally_good' then 'tie'
         when v.outcome = 'cant_decide' then 'unsure'
         else 'broken'
       end as verdict,
       v.dimensions, v.reason, v.created_at
  from votes v
  join served_pairs s on s.token = v.token;

-- A voter's first verdict on a pair is their judgment of it. A later one is a repeat, which
-- measures their consistency instead.
create view first_verdicts with (security_invoker = true) as
select distinct on (voter_id, round, pair_low, pair_high) *
  from vote_verdicts
 order by voter_id, round, pair_low, pair_high, created_at, id;

-- How the panel split on each pair. agreement is the share of judging voters who gave the
-- most common verdict; split means some voters preferred each capture.
create view pair_agreement with (security_invoker = true) as
select round, pair_low, pair_high,
       count(*) filter (where verdict <> 'unsure') as judged,
       count(*) filter (where verdict = 'low') as low_better,
       count(*) filter (where verdict = 'high') as high_better,
       count(*) filter (where verdict = 'tie') as equally_good,
       count(*) filter (where verdict = 'unsure') as cant_decide,
       round(greatest(count(*) filter (where verdict = 'low'),
                      count(*) filter (where verdict = 'high'),
                      count(*) filter (where verdict = 'tie'))::numeric
             / nullif(count(*) filter (where verdict <> 'unsure'), 0), 3) as agreement,
       count(*) filter (where verdict = 'low') > 0
         and count(*) filter (where verdict = 'high') > 0 as split
  from first_verdicts
 where verdict <> 'broken'
 group by round, pair_low, pair_high;

-- Each voter's consistency on the pairs they judged more than once (the swapped repeats).
-- flipped means they preferred each capture at different times.
create view voter_consistency with (security_invoker = true) as
with repeated as (
  select voter_id, round, pair_low, pair_high,
         count(distinct verdict) = 1 as same,
         count(distinct verdict) filter (where verdict in ('low', 'high')) = 2 as flipped
    from vote_verdicts
   where verdict in ('low', 'high', 'tie')
   group by voter_id, round, pair_low, pair_high
  having count(*) > 1
)
select r.round, r.voter_id, vt.name as voter,
       count(*) as repeated_pairs,
       count(*) filter (where r.same) as same_verdict,
       count(*) filter (where r.flipped) as flipped,
       round(avg(r.same::int), 3) as consistency
  from repeated r
  join voters vt on vt.id = r.voter_id
 group by r.round, r.voter_id, vt.name;

-- How often two voters gave the same verdict on the pairs both judged. opposite means each
-- preferred a different capture.
create view voter_agreement with (security_invoker = true) as
select x.round, x.voter_id as voter_a_id, va.name as voter_a,
       y.voter_id as voter_b_id, vb.name as voter_b,
       count(*) as shared_pairs,
       count(*) filter (where x.verdict = y.verdict) as same_verdict,
       count(*) filter (where x.verdict <> y.verdict and 'tie' not in (x.verdict, y.verdict))
         as opposite,
       round(avg((x.verdict = y.verdict)::int), 3) as agreement
  from first_verdicts x
  join first_verdicts y
    on y.round = x.round and y.pair_low = x.pair_low and y.pair_high = x.pair_high
   and y.voter_id > x.voter_id
  join voters va on va.id = x.voter_id
  join voters vb on vb.id = y.voter_id
 where x.verdict in ('low', 'high', 'tie') and y.verdict in ('low', 'high', 'tie')
 group by x.round, x.voter_id, va.name, y.voter_id, vb.name;

-- One voter's visual and motion verdicts on the same pair. A difference is information, not
-- an error: a site can look better and move worse. Each round's dimensions and reasons say why.
create view round_differences with (security_invoker = true) as
select v.voter_id, vt.name as voter, v.pair_low, v.pair_high,
       v.verdict as visual, m.verdict as motion,
       v.verdict <> m.verdict as differs,
       v.verdict <> m.verdict and 'tie' not in (v.verdict, m.verdict) as opposite,
       v.dimensions as visual_dimensions, m.dimensions as motion_dimensions,
       v.reason as visual_reason, m.reason as motion_reason
  from first_verdicts v
  join first_verdicts m
    on m.voter_id = v.voter_id and m.round = 'motion'
   and m.pair_low = v.pair_low and m.pair_high = v.pair_high
  join voters vt on vt.id = v.voter_id
 where v.round = 'visual'
   and v.verdict in ('low', 'high', 'tie') and m.verdict in ('low', 'high', 'tie');

create function voter_for(p_code text) returns voters
language plpgsql stable as $$
declare
  found_voter voters;
begin
  select * into found_voter from voters where invite_code = p_code and active;
  if not found then
    raise exception 'unknown or inactive invite code' using errcode = '28000';
  end if;
  return found_voter;
end;
$$;

create function next_pair(p_code text, p_round round_kind) returns served_pairs
language plpgsql as $$
declare
  voter voters := voter_for(p_code);
  cfg voting_config;
  a text;
  b text;
  src text;
  first_left text;
  flip boolean;
  contested boolean;
  asked_in_other_round boolean;
  result served_pairs;
begin
  select * into cfg from voting_config;

  -- An unanswered pair served recently comes back, so a refresh never skips work.
  select * into result from served_pairs s
   where s.voter_id = voter.id and s.round = p_round and s.used_at is null
     and s.served_at > now() - make_interval(mins => cfg.resume_minutes)
   order by s.served_at desc
   limit 1;
  if found then
    return result;
  end if;

  -- 1. Calibration: every voter judges every calibration pair once, in their own order.
  select cp.capture_a, cp.capture_b into a, b
    from open_calibration_pairs cp
   where cp.round = p_round
     and not exists (
       select 1 from votes v
        where v.voter_id = voter.id and v.round = p_round
          and v.pair_low = cp.capture_a and v.pair_high = cp.capture_b)
   order by md5(voter.id::text || ':' || cp.id)
   limit 1;
  if found then
    src := 'calibration';
  end if;

  -- 2. Planned repeats: calibration pairs answered once, shown again with sides swapped.
  if src is null and (
       select count(*) from votes v join served_pairs s on s.token = v.token
        where v.voter_id = voter.id and v.round = p_round and s.source = 'repeat'
     ) < cfg.repeat_count then
    select cp.capture_a, cp.capture_b into a, b
      from open_calibration_pairs cp
     where cp.round = p_round
       and (select count(*) from votes v
             where v.voter_id = voter.id and v.round = p_round
               and v.pair_low = cp.capture_a and v.pair_high = cp.capture_b) = 1
     order by md5(voter.id::text || ':repeat:' || cp.id)
     limit 1;
    if found then
      src := 'repeat';
    end if;
  end if;

  -- 3. Overlap: a pair someone else judged, so agreement keeps being measured.
  if src is null and random() < cfg.overlap_share then
    select v.pair_low, v.pair_high into a, b
      from votes v
      join captures cl on cl.id = v.pair_low
      join captures ch on ch.id = v.pair_high
     where v.round = p_round and v.voter_id <> voter.id
       and v.outcome in ('left', 'right', 'equally_good')
       and servable(cl, p_round) and servable(ch, p_round)
       and not exists (
         select 1 from votes mine
          where mine.voter_id = voter.id and mine.round = p_round
            and mine.pair_low = v.pair_low and mine.pair_high = v.pair_high)
     order by random()
     limit 1;
    if found then
      src := 'overlap';
    end if;
  end if;

  -- 4. Adaptive: the least-compared capture in the pool, against one this voter has not
  --    paired it with yet.
  if src is null then
    select c.id into a
      from captures c
     where servable(c, p_round)
     order by (select count(*) from votes v
                where v.round = p_round and (v.left_capture = c.id or v.right_capture = c.id)),
              random()
     limit 1;
    select c.id into b
      from captures c
     where servable(c, p_round) and c.id <> a
       and not exists (
         select 1 from votes v
          where v.voter_id = voter.id and v.round = p_round
            and v.pair_low = least(a, c.id) and v.pair_high = greatest(a, c.id))
     order by random()
     limit 1;
    if a is null or b is null then
      raise exception 'no pairs left for this round' using errcode = 'P0002';
    end if;
    src := 'adaptive';
  end if;

  if src = 'repeat' then
    select v.left_capture into first_left
      from votes v
     where v.voter_id = voter.id and v.round = p_round and v.pair_low = a and v.pair_high = b
     limit 1;
    flip := first_left = a;  -- the side each site was on last time, reversed
  else
    flip := random() < 0.5;
  end if;

  -- A reason is asked on 1 in reason_every pairs at random, and wherever it can explain a
  -- difference: always on a pair other voters split on, and on a pair this voter judged in
  -- the other round exactly when it was asked there, so the two rounds' reasons pair up.
  -- The voter is never told why, so nothing hints at how anyone voted.
  contested := (
    select count(distinct f.verdict) = 2
      from first_verdicts f
     where f.round = p_round and f.pair_low = least(a, b) and f.pair_high = greatest(a, b)
       and f.voter_id <> voter.id and f.verdict in ('low', 'high'));
  select s.reason_requested into asked_in_other_round
    from votes v
    join served_pairs s on s.token = v.token
   where v.voter_id = voter.id and v.round <> p_round
     and v.pair_low = least(a, b) and v.pair_high = greatest(a, b)
   order by v.created_at
   limit 1;

  insert into served_pairs (voter_id, round, left_capture, right_capture, source, reason_requested)
  values (
    voter.id,
    p_round,
    case when flip then b else a end,
    case when flip then a else b end,
    src,
    contested or coalesce(asked_in_other_round, random() < 1.0 / cfg.reason_every)
  )
  returning * into result;
  return result;
end;
$$;

create function cast_vote(
  p_code text, p_token uuid, p_outcome vote_outcome, p_dimensions text[], p_reason text
) returns bigint
language plpgsql as $$
declare
  voter voters := voter_for(p_code);
  cfg voting_config;
  pair served_pairs;
  dims text[] := coalesce(p_dimensions, '{}');
  decisive boolean := p_outcome in ('left', 'right');
  vote_id bigint;
begin
  select * into cfg from voting_config;
  select * into pair from served_pairs where token = p_token for update;
  if not found or pair.voter_id <> voter.id then
    raise exception 'this pair was not served to you' using errcode = '22023';
  end if;
  if pair.used_at is not null then
    raise exception 'this pair already has your vote' using errcode = '23505';
  end if;
  if exists (
       select 1 from unnest(dims) d
        where not exists (select 1 from dimensions x where x.id = d and x.round = pair.round)) then
    raise exception 'unknown dimension for this round' using errcode = '22023';
  end if;
  if decisive and cardinality(dims) = 0 then
    raise exception 'pick at least one dimension that decided it' using errcode = '22023';
  end if;
  if cardinality(dims) > cfg.max_dimensions then
    raise exception 'pick at most % dimensions', cfg.max_dimensions using errcode = '22023';
  end if;
  if decisive and pair.reason_requested
     and length(trim(coalesce(p_reason, ''))) < cfg.min_reason_chars then
    raise exception 'a reason of at least % characters is required', cfg.min_reason_chars
      using errcode = '22023';
  end if;

  insert into votes (
    token, voter_id, round, left_capture, right_capture, outcome, dimensions, reason, seconds_to_vote
  ) values (
    p_token, voter.id, pair.round, pair.left_capture, pair.right_capture, p_outcome, dims,
    nullif(trim(p_reason), ''), extract(epoch from now() - pair.served_at)
  )
  returning id into vote_id;
  update served_pairs set used_at = now() where token = p_token;

  if p_outcome in ('broken_left', 'broken_right') then
    update captures
       set in_pool = false, qa_note = 'reported broken by a voter', updated_at = now()
     where id = case when p_outcome = 'broken_left' then pair.left_capture else pair.right_capture end;
  end if;
  return vote_id;
end;
$$;

create function log_event(p_code text, p_token uuid, p_kind text) returns void
language plpgsql as $$
declare
  voter voters := voter_for(p_code);
begin
  if not exists (select 1 from served_pairs where token = p_token and voter_id = voter.id) then
    raise exception 'this pair was not served to you' using errcode = '22023';
  end if;
  insert into vote_events (token, kind) values (p_token, p_kind);
end;
$$;

create function voter_progress(p_code text)
returns table (round round_kind, calibration_done bigint, calibration_total bigint, votes bigint)
language plpgsql stable as $$
declare
  voter voters := voter_for(p_code);
begin
  return query
  select r.kind,
         (select count(*) from open_calibration_pairs cp
           where cp.round = r.kind and exists (
             select 1 from votes v
              where v.voter_id = voter.id and v.round = r.kind
                and v.pair_low = cp.capture_a and v.pair_high = cp.capture_b)),
         (select count(*) from open_calibration_pairs cp where cp.round = r.kind),
         (select count(*) from votes v where v.voter_id = voter.id and v.round = r.kind)
    from unnest(enum_range(null::round_kind)) as r (kind);
end;
$$;

revoke all on all tables in schema public from anon, authenticated;
revoke execute on all functions in schema public from public, anon, authenticated;

commit;
