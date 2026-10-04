-- TASTE engine v2: active time. seconds_to_vote is wall-clock time from serving a pair to the
-- vote, so a tab left open overnight looks like hours of looking. The voting page now measures,
-- for each pair, how long it was on screen (visible), in front (focused) and in use (active: up
-- to idle_cutoff_seconds after the last input or a playing reel), how often the voter left it,
-- and the longest stretch on screen without input. It sends them with the vote in
-- client.timing. This migration processes them. No data changes: two settings, one helper, and
-- views that only gain columns at their end.

begin;

alter table voting_config
  -- No input for this long and the page stops counting time as active, until the next input.
  -- The voting page reads it through voting_facts(), so page and views share one definition.
  add column idle_cutoff_seconds numeric not null default 120 check (idle_cutoff_seconds > 0),
  -- This long between two of a voter's votes starts a new sitting, whatever the browser tab:
  -- a tab left open overnight is two sittings, not one long session.
  add column session_gap_minutes integer not null default 30 check (session_gap_minutes > 0);

-- One number from a vote's client.timing, or null when the vote has none (votes cast before the
-- page measured time, or a value that is not a number).
create function timing_value(p_client jsonb, p_key text) returns numeric
language sql immutable as $$
  select case when jsonb_typeof(p_client -> 'timing' -> p_key) = 'number'
              then (p_client -> 'timing' ->> p_key)::numeric end
$$;

create or replace function voting_facts() returns jsonb
language sql stable as $$
  select jsonb_build_object(
    'min_reason_chars', c.min_reason_chars,
    'max_dimensions', c.max_dimensions,
    'max_own_terms', c.max_own_terms,
    'max_term_chars', c.max_term_chars,
    'idle_cutoff_seconds', c.idle_cutoff_seconds,
    'rounds', (
      select jsonb_object_agg(r.kind, jsonb_build_object(
        'target_votes', coalesce((select t.target_votes from round_targets t where t.round = r.kind), 0),
        'calibration_pairs', (select count(*) from open_calibration_pairs p where p.round = r.kind),
        'repeats', c.repeat_count))
        from unnest(enum_range(null::round_kind)) as r (kind)))
  from voting_config c
$$;

-- How each voter votes. The first columns are as before (wall-clock time, sessions as the page
-- counts them). Then active time: its median overall, early in a sitting (its first 10 votes)
-- and late (after its 20th); sittings, split where votes are session_gap_minutes apart;
-- votes where the voter left the page; and votes whose wall-clock time exceeds their active
-- time by more than the idle cut-off, which wall-clock medians would overstate.
create or replace view voter_effort with (security_invoker = true) as
with timed as (
  select v.*,
         case when v.client ->> 'index' ~ '^[0-9]+$' then (v.client ->> 'index')::int end
           as position,
         timing_value(v.client, 'active_s') as active_seconds,
         timing_value(v.client, 'away_count') as away_count,
         coalesce(v.created_at - lag(v.created_at) over (partition by v.voter_id
                                                         order by v.created_at, v.id)
                  > make_interval(mins => c.session_gap_minutes), true) as starts_sitting,
         c.idle_cutoff_seconds
    from vote_verdicts v
   cross join voting_config c
), sittings as (
  select t.*, sum(t.starts_sitting::int) over (partition by t.voter_id
                                               order by t.created_at, t.id) as sitting
    from timed t
), placed as (
  select s.*, row_number() over (partition by s.voter_id, s.sitting
                                 order by s.created_at, s.id) as sitting_position
    from sittings s
)
select v.round, v.voter_id, vt.name as voter,
       count(*) as votes,
       count(*) filter (where v.fast) as fast_votes,
       round(percentile_cont(0.5) within group (order by v.seconds_to_vote)::numeric, 1)
         as median_seconds,
       round((percentile_cont(0.5) within group (order by v.seconds_to_vote)
              filter (where v.position <= 10))::numeric, 1) as early_median_seconds,
       round((percentile_cont(0.5) within group (order by v.seconds_to_vote)
              filter (where v.position > 20))::numeric, 1) as late_median_seconds,
       count(distinct v.client ->> 'session') as sessions,
       count(v.active_seconds) as timed_votes,
       round(percentile_cont(0.5) within group (order by v.active_seconds)::numeric, 1)
         as median_active_seconds,
       round((percentile_cont(0.5) within group (order by v.active_seconds)
              filter (where v.sitting_position <= 10))::numeric, 1) as early_median_active_seconds,
       round((percentile_cont(0.5) within group (order by v.active_seconds)
              filter (where v.sitting_position > 20))::numeric, 1) as late_median_active_seconds,
       count(distinct v.sitting) as sittings,
       count(*) filter (where v.away_count > 0) as left_page_votes,
       count(*) filter (where v.seconds_to_vote > v.active_seconds + v.idle_cutoff_seconds)
         as idle_votes
  from placed v
  join voters vt on vt.id = v.voter_id
 group by v.round, v.voter_id, vt.name;

-- What the voter looked at before voting (as before), then for how long: seconds the pair was on
-- screen and in use, how often the voter left the page, the longest stretch on screen without
-- input, and whether they left at all. Null where the vote has no timing.
create or replace view vote_attention with (security_invoker = true) as
select v.id as vote_id, v.token, v.voter_id, v.round,
       coalesce(v.client ->> 'layout', 'unknown') as layout,
       (v.client ->> 'layout') is distinct from 'tabs'
         or exists (select 1 from vote_events e where e.token = v.token and e.kind = 'view_right')
         as saw_both,
       exists (select 1 from vote_events e where e.token = v.token and e.kind = 'scroll_left')
         and exists (select 1 from vote_events e where e.token = v.token and e.kind = 'scroll_right')
         as scrolled_both,
       exists (select 1 from vote_events e where e.token = v.token and e.kind = 'play_left')
         and exists (select 1 from vote_events e where e.token = v.token and e.kind = 'play_right')
         as played_both,
       exists (select 1 from vote_events e where e.token = v.token and e.kind like 'open_live_%')
         as opened_live,
       timing_value(v.client, 'visible_s') as visible_seconds,
       timing_value(v.client, 'active_s') as active_seconds,
       timing_value(v.client, 'away_count') as away_count,
       timing_value(v.client, 'longest_idle_s') as longest_idle_seconds,
       timing_value(v.client, 'away_count') > 0 as left_page
  from votes v;

-- How each voter leans (as before), and how often they left the page mid-vote.
create or replace view voter_bias with (security_invoker = true) as
select v.round, v.voter_id, vt.name as voter, a.layout,
       count(*) as votes,
       round(avg((v.outcome = 'left')::int) filter (where v.outcome in ('left', 'right')), 3)
         as left_share,
       round(avg((v.outcome = 'equally_good')::int), 3) as tie_share,
       round(avg((v.outcome = 'cant_decide')::int), 3) as cant_decide_share,
       round(avg((cardinality(v.own_terms) > 0)::int) filter (where v.outcome in ('left', 'right')), 3)
         as own_words_share,
       round(avg(a.saw_both::int), 3) as saw_both_share,
       round(avg(a.scrolled_both::int) filter (where v.round = 'visual'), 3) as scrolled_both_share,
       round(avg(a.played_both::int) filter (where v.round = 'motion'), 3) as played_both_share,
       round(avg(a.opened_live::int), 3) as opened_live_share,
       round(avg(a.left_page::int), 3) as left_page_share
  from votes v
  join vote_attention a on a.vote_id = v.id
  join voters vt on vt.id = v.voter_id
 group by v.round, v.voter_id, vt.name, a.layout;

revoke all on all tables in schema public from anon, authenticated;
revoke execute on all functions in schema public from public, anon, authenticated;

commit;
