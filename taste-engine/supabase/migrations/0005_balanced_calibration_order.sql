-- TASTE engine v2: calibration pairs in a balanced order, to reduce fatigue.
-- Before this, each voter got the calibration pairs in a random order. Random is not even: by
-- their 43rd vote one voter had seen one site 10 times and another twice, and the same site
-- often came up in back-to-back pairs. The set of pairs is unchanged; only the order is: the next
-- calibration pair is the one whose sites this voter has seen least, avoiding a site from their
-- previous pair. Everything else in next_pair is as it was. No data changes.

begin;

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
       where servable(c, p_round)
       order by coalesce(seen.n, 0), random()
    loop
      select c.id into b
        from captures c
       where servable(c, p_round) and c.id <> a
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

revoke all on all tables in schema public from anon, authenticated;
revoke execute on all functions in schema public from public, anon, authenticated;

commit;
