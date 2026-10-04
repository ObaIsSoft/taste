-- TASTE engine v2: pinned media, step 2. Apply after every capture has been published again
-- with pinned media (taste publish), so every capture has a media_id.

begin;

-- Pairs served and votes cast before 0003 showed the only media each capture had then. Those
-- files were checked byte for byte (md5) against the files their media_id was computed from
-- (see docs/operations.md, 2026-10-04), so they are pinned to it.
update served_pairs s set left_media = c.media_id
  from captures c where s.left_media is null and c.id = s.left_capture;
update served_pairs s set right_media = c.media_id
  from captures c where s.right_media is null and c.id = s.right_capture;
update votes v set left_media = s.left_media, right_media = s.right_media
  from served_pairs s
 where s.token = v.token and (v.left_media is null or v.right_media is null);

alter table served_pairs
  alter column left_media set not null, alter column right_media set not null;
alter table votes
  alter column left_media set not null, alter column right_media set not null;

-- A capture can be shown only once its media is published and pinned.
create or replace function servable(c captures, p_round round_kind) returns boolean
language sql stable as $$
  select c.in_pool and c.media_id is not null and (p_round = 'visual' or c.reel_path is not null)
$$;

revoke all on all tables in schema public from anon, authenticated;
revoke execute on all functions in schema public from public, anon, authenticated;

commit;
