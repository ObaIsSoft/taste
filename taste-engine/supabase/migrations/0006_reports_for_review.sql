-- TASTE engine v2: reports on calibration sites go to the operator for review.
-- Before this, one voter's "broken" report took a capture out of the pool for everyone at once. On
-- 5 October a voter on a phone reported a dark, sparse calibration site that was not broken, and
-- the visual calibration set fell from 14 sites to 13 for every voter. Now:
--   - a report on a calibration site waits for review; the site stays in the pool, and only the
--     voter who reported it stops seeing it until it is decided;
--   - a report on any other site still takes it out at once, and is logged so it can be undone;
--   - review_report(id, 'uphold' | 'dismiss', note) decides a report (`taste reports`).
-- The report vote itself is unchanged. No existing data changes.

begin;

create table capture_reports (
  id bigserial primary key,
  vote_id bigint not null unique references votes (id),
  capture_id text not null references captures (id),
  voter_id uuid not null references voters (id),
  reported_at timestamptz not null default now(),
  -- pending: a calibration site, waiting for review, still in the pool
  -- removed: any other site, taken out at once, not yet reviewed
  -- upheld / dismissed: decided by the operator
  status text not null check (status in ('pending', 'removed', 'upheld', 'dismissed')),
  decided_at timestamptz,
  note text
);
create index capture_reports_open on capture_reports (voter_id, capture_id) where status = 'pending';
alter table capture_reports enable row level security;

-- Whether this voter has a report on this capture waiting for review: they are not shown it again
-- until it is decided.
create function reported_by(p_voter uuid, p_capture text) returns boolean
language sql stable as $$
  select exists (
    select 1 from capture_reports r
     where r.voter_id = p_voter and r.capture_id = p_capture and r.status = 'pending')
$$;

create or replace function cast_vote(
  p_code text, p_token uuid, p_outcome vote_outcome, p_dimensions text[], p_reason text,
  p_terms text[] default '{}', p_client jsonb default '{}'
) returns bigint
language plpgsql as $$
declare
  voter voters := voter_for(p_code);
  cfg voting_config;
  pair served_pairs;
  dims text[] := coalesce(p_dimensions, '{}');
  terms text[] := coalesce(
    (select array_agg(distinct trim(t)) from unnest(p_terms) t where trim(t) <> ''), '{}');
  decisive boolean := p_outcome in ('left', 'right');
  vote_id bigint;
  reported text;
begin
  select * into cfg from voting_config;
  select * into pair from served_pairs where token = p_token for update;
  if not found or pair.voter_id <> voter.id then
    raise exception 'this pair was not served to you' using errcode = '22023';
  end if;
  if pair.used_at is not null then
    raise exception 'this pair already has your vote' using errcode = '23505';
  end if;
  if extract(epoch from now() - pair.served_at) < cfg.min_vote_seconds then
    raise exception 'take a moment to look at both sites' using errcode = 'P0429';
  end if;
  if exists (
       select 1 from unnest(dims) d
        where not exists (select 1 from dimensions x where x.id = d and x.round = pair.round)) then
    raise exception 'unknown dimension for this round' using errcode = '22023';
  end if;
  if decisive and cardinality(dims) + cardinality(terms) = 0 then
    raise exception 'say what decided it: pick one, or add your own words' using errcode = '22023';
  end if;
  if cardinality(terms) > cfg.max_own_terms then
    raise exception 'add at most % of your own words', cfg.max_own_terms using errcode = '22023';
  end if;
  if jsonb_typeof(coalesce(p_client, '{}')) <> 'object'
     or length(p_client::text) > cfg.max_client_chars then
    raise exception 'client details must be a small object' using errcode = '22023';
  end if;
  if exists (select 1 from unnest(terms) t where length(t) > cfg.max_term_chars) then
    raise exception 'keep each of your own words under % characters', cfg.max_term_chars
      using errcode = '22023';
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
    token, voter_id, round, left_capture, right_capture, outcome, dimensions, own_terms, reason,
    seconds_to_vote, client
  ) values (
    p_token, voter.id, pair.round, pair.left_capture, pair.right_capture, p_outcome, dims, terms,
    nullif(trim(p_reason), ''), extract(epoch from now() - pair.served_at),
    coalesce(p_client, '{}')
  )
  returning id into vote_id;
  update served_pairs set used_at = now() where token = p_token;

  -- A report on a calibration site waits for the operator: every voter compares those sites, so
  -- one report must not change the set for everyone. Meanwhile only the reporter stops seeing it.
  -- A report on any other site takes it out at once, and is logged so a wrong removal can be undone.
  if p_outcome in ('broken_left', 'broken_right') then
    reported := case when p_outcome = 'broken_left' then pair.left_capture else pair.right_capture end;
    if exists (select 1 from calibration_pairs cp where reported in (cp.capture_a, cp.capture_b)) then
      insert into capture_reports (vote_id, capture_id, voter_id, status)
      values (vote_id, reported, voter.id, 'pending');
    else
      update captures
         set in_pool = false, qa_note = 'reported broken by a voter', updated_at = now()
       where id = reported;
      insert into capture_reports (vote_id, capture_id, voter_id, status)
      values (vote_id, reported, voter.id, 'removed');
    end if;
  end if;
  return vote_id;
end;
$$;

create or replace function next_pair(p_code text, p_round round_kind) returns served_pairs
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
  lean bigint;
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

  -- 1. Calibration: every voter judges every calibration pair once. The next one is the pair
  --    whose sites this voter has seen least, avoiding a site from their previous pair, so every
  --    stretch of votes shows the sites evenly (no site more than about two showings ahead, and
  --    never the same site twice in a row where avoidable). Ties fall to a per-voter shuffle.
  with seen as (
    select x.capture, count(*) as n
      from votes v, lateral (values (v.left_capture), (v.right_capture)) x (capture)
     where v.voter_id = voter.id and v.round = p_round
     group by x.capture
  ), previous as (
    select v.left_capture, v.right_capture
      from votes v
     where v.voter_id = voter.id and v.round = p_round
     order by v.created_at desc, v.id desc
     limit 1
  )
  select cp.capture_a, cp.capture_b into a, b
    from open_calibration_pairs cp
    left join seen sa on sa.capture = cp.capture_a
    left join seen sb on sb.capture = cp.capture_b
   where cp.round = p_round
     and not reported_by(voter.id, cp.capture_a) and not reported_by(voter.id, cp.capture_b)
     and not exists (
       select 1 from votes v
        where v.voter_id = voter.id and v.round = p_round
          and v.pair_low = cp.capture_a and v.pair_high = cp.capture_b)
   order by greatest(coalesce(sa.n, 0), coalesce(sb.n, 0)),
            coalesce(sa.n, 0) + coalesce(sb.n, 0),
            (select count(*) from previous p
              where cp.capture_a in (p.left_capture, p.right_capture)
                 or cp.capture_b in (p.left_capture, p.right_capture)),
            md5(voter.id::text || ':' || cp.id)
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
       and not reported_by(voter.id, cp.capture_a) and not reported_by(voter.id, cp.capture_b)
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
       and not reported_by(voter.id, v.pair_low) and not reported_by(voter.id, v.pair_high)
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

  -- 4. Adaptive: the least-compared capture in the pool that this voter can still pair, against
  --    one they have not paired it with yet. A capture they have paired with everything is
  --    skipped, so a busy voter is never told there is nothing left while pairs remain.
  if src is null then
    for a in
      select c.id
        from captures c
        left join (
          select x.capture, count(*) as n
            from (select left_capture as capture from votes where round = p_round
                  union all
                  select right_capture from votes where round = p_round) x
           group by x.capture
        ) seen on seen.capture = c.id
       where servable(c, p_round) and not reported_by(voter.id, c.id)
       order by coalesce(seen.n, 0), random()
    loop
      select c.id into b
        from captures c
       where servable(c, p_round) and c.id <> a and not reported_by(voter.id, c.id)
         and not exists (
           select 1 from votes v
            where v.voter_id = voter.id and v.round = p_round
              and v.pair_low = least(a, c.id) and v.pair_high = greatest(a, c.id))
       order by random()
       limit 1;
      exit when b is not null;
    end loop;
    if b is null then
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
    -- Balanced sides: the site that has been on the left less often (relative to the right)
    -- goes on the left, so every site is seen about as often on each side; ties are random.
    select coalesce(sum(case when s.left_capture = a then 1 when s.right_capture = a then -1 end), 0)
         - coalesce(sum(case when s.left_capture = b then 1 when s.right_capture = b then -1 end), 0)
      into lean
      from served_pairs s
     where s.round = p_round and (a in (s.left_capture, s.right_capture) or b in (s.left_capture, s.right_capture));
    flip := lean > 0 or (lean = 0 and random() < 0.5);
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

-- Decide a report. Upholding takes the capture out of the pool for everyone (its qa_note keeps it
-- out on later publishes). Dismissing keeps it in, and puts back a capture that a report on a
-- non-calibration site had taken out.
create function review_report(p_report bigint, p_decision text, p_note text default null)
returns capture_reports
language plpgsql as $$
declare
  report capture_reports;
begin
  select * into report from capture_reports where id = p_report for update;
  if not found then
    raise exception 'no report %', p_report using errcode = 'P0002';
  end if;
  if report.status not in ('pending', 'removed') then
    raise exception 'report % was already decided: %', p_report, report.status using errcode = '23505';
  end if;
  if p_decision = 'uphold' then
    update captures
       set in_pool = false, qa_note = 'reported broken by a voter; upheld on review', updated_at = now()
     where id = report.capture_id;
  elsif p_decision = 'dismiss' then
    if report.status = 'removed' then
      update captures set in_pool = true, qa_note = null, updated_at = now()
       where id = report.capture_id and qa_note = 'reported broken by a voter';
    end if;
  else
    raise exception 'decision must be uphold or dismiss' using errcode = '22023';
  end if;
  update capture_reports
     set status = case when p_decision = 'uphold' then 'upheld' else 'dismissed' end,
         decided_at = now(), note = p_note
   where id = p_report
  returning * into report;
  return report;
end;
$$;

revoke all on all tables in schema public from anon, authenticated;
revoke execute on all functions in schema public from public, anon, authenticated;

commit;
