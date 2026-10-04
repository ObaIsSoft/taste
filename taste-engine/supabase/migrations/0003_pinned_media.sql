-- TASTE engine v2: pinned media. A vote must always point at exactly what the voter saw.
-- Before this, a vote named only a capture id, and publishing a capture again overwrote its media
-- under the same paths, so a re-capture would have silently changed what old votes point at.
--
-- Now every version of a capture's media is kept, under a fingerprint of its files (media_id);
-- every served pair and vote records the media_id each side showed; and none of it can change
-- afterwards. A site id always means the same URL. Applied in two steps around a re-publish:
-- this file adds the structure (media optional), 0004 fills in the pairs served before it and
-- makes media required.

begin;

-- Every version of a capture's media that was ever published. Rows are never changed or removed.
-- A version is registered before the capture points at it, so a new capture's first version can
-- exist before its row: capture_id is not a foreign key here, but everything that uses a version
-- (the capture, served pairs, votes) refers to it by capture and media id together.
create table capture_media (
  capture_id text not null,
  media_id text not null,  -- sha256 over the files' hashes in order, first 16 hex characters
  capture_version text not null,  -- the capture code that made these files
  stills text[] not null check (cardinality(stills) > 0),  -- storage paths, hero first
  reel_path text,
  files jsonb not null,  -- each storage path with the sha256 of its bytes
  published_at timestamptz not null default now(),
  primary key (capture_id, media_id)
);
alter table capture_media enable row level security;

-- The media a capture shows now. Pairs served from here on record it.
alter table captures add column media_id text;
alter table captures add constraint captures_media_fkey
  foreign key (id, media_id) references capture_media (capture_id, media_id);

alter table served_pairs add column left_media text, add column right_media text;
alter table served_pairs
  add constraint served_pairs_left_media_fkey
    foreign key (left_capture, left_media) references capture_media (capture_id, media_id),
  add constraint served_pairs_right_media_fkey
    foreign key (right_capture, right_media) references capture_media (capture_id, media_id);

alter table votes add column left_media text, add column right_media text;
alter table votes
  add constraint votes_left_media_fkey
    foreign key (left_capture, left_media) references capture_media (capture_id, media_id),
  add constraint votes_right_media_fkey
    foreign key (right_capture, right_media) references capture_media (capture_id, media_id);

-- When a pair is served, record the media each side shows at that moment.
create function pin_served_media() returns trigger
language plpgsql as $$
begin
  select c.media_id into new.left_media from captures c where c.id = new.left_capture;
  select c.media_id into new.right_media from captures c where c.id = new.right_capture;
  return new;
end;
$$;
create trigger served_pairs_pin_media before insert on served_pairs
  for each row execute function pin_served_media();

-- A vote records the media of the pair it answers.
create function pin_vote_media() returns trigger
language plpgsql as $$
begin
  select s.left_media, s.right_media into new.left_media, new.right_media
    from served_pairs s where s.token = new.token;
  return new;
end;
$$;
create trigger votes_pin_media before insert on votes
  for each row execute function pin_vote_media();

-- What a pair or vote showed is fixed once recorded. (Rows can still be deleted, as the
-- smoke-test clean-up does; a missing pin can be filled in once, as 0004 does.)
create function keep_pins() returns trigger
language plpgsql as $$
begin
  if new.left_capture is distinct from old.left_capture
     or new.right_capture is distinct from old.right_capture
     or (old.left_media is not null and new.left_media is distinct from old.left_media)
     or (old.right_media is not null and new.right_media is distinct from old.right_media) then
    raise exception 'what a pair showed is fixed once recorded' using errcode = '55000';
  end if;
  return new;
end;
$$;
create trigger served_pairs_keep_pins before update on served_pairs
  for each row execute function keep_pins();
create trigger votes_keep_pins before update on votes
  for each row execute function keep_pins();

create function refuse_change() returns trigger
language plpgsql as $$
begin
  raise exception 'published media is never changed or removed (%)', tg_table_name
    using errcode = '55000';
end;
$$;
create trigger capture_media_append_only before update or delete on capture_media
  for each row execute function refuse_change();

-- A site id always means the same URL, and a capture always belongs to the same site.
create function keep_site_url() returns trigger
language plpgsql as $$
begin
  if new.id is distinct from old.id or new.url is distinct from old.url then
    raise exception 'site % is %; a site id never points at another URL', old.id, old.url
      using errcode = '55000';
  end if;
  return new;
end;
$$;
create trigger sites_keep_url before update on sites
  for each row execute function keep_site_url();

create function keep_capture_site() returns trigger
language plpgsql as $$
begin
  if new.id is distinct from old.id or new.site_id is distinct from old.site_id
     or new.variant is distinct from old.variant then
    raise exception 'capture % belongs to site % as %', old.id, old.site_id, old.variant
      using errcode = '55000';
  end if;
  return new;
end;
$$;
create trigger captures_keep_site before update on captures
  for each row execute function keep_capture_site();

revoke all on all tables in schema public from anon, authenticated;
revoke execute on all functions in schema public from public, anon, authenticated;

commit;
