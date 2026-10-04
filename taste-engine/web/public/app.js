'use strict';

// Voting client. Every rule is enforced by the server; checks here only give
// faster feedback, using the limits the server sends in /api/config.
// The screen calls the two sites A and B; the API calls them left and right.

const STORE_KEY = 'taste.inviteCode';
const SIDES = ['left', 'right'];
const LETTER = { left: 'A', right: 'B' };
const PICK_KEYS = { 1: 'left', 2: 'right', e: 'equally_good', s: 'cant_decide' };
const DECISIVE = ['left', 'right'];
// The question after each choice. Only A or B must say what decided it; the others may.
const QUESTIONS = {
  left: (max) => ['What made A better?', `Pick up to ${max}, or use your own words`],
  right: (max) => ['What made B better?', `Pick up to ${max}, or use your own words`],
  equally_good: () => ['What makes them equally good?', 'Optional'],
  cant_decide: () => ['What makes it hard to decide?', 'Optional'],
};
const PLACEHOLDERS = {
  left: 'A is better because …',
  right: 'B is better because …',
  equally_good: 'Both work because …',
  cant_decide: 'It is hard to call because …',
};

const state = {
  code: null, name: null, config: null, round: null, pair: null, pick: null, chips: new Set(), terms: [],
  busy: false, cast: 0, session: null,
};

// One id per sign-in, and the position of each vote within it: the database uses them to see
// fatigue (late votes in a long session) and whether two rounds were judged together. A new
// voter in the same tab starts a new session, so two people never share one.
function newSession() {
  return (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

// How this vote was seen: one site at a time on a phone, stacked, or side by side.
function layout() {
  if (getComputedStyle($('.side-switch')).display !== 'none') return 'tabs';
  const left = $('#card-left').getBoundingClientRect();
  const right = $('#card-right').getBoundingClientRect();
  return right.top >= left.bottom - 1 ? 'stacked' : 'side_by_side';
}

function clientDetails() {
  return {
    session: state.session,
    index: state.cast + 1,
    layout: layout(),
    viewport_width: window.innerWidth,
    viewport_height: window.innerHeight,
    pixel_ratio: window.devicePixelRatio || 1,
    pointer: window.matchMedia('(pointer: coarse)').matches ? 'coarse' : 'fine',
    timing: state.pair && timing.token === state.pair.token ? timingDetails() : undefined,
  };
}

// How long each pair was really looked at. The server's seconds_to_vote is wall-clock time, so a
// tab left open overnight looks like hours of looking. These count only time the page was on
// screen (visible), in front (focused), and in use (active): up to the idle cut-off after the
// voter last moved, scrolled, typed, came back, or a reel played. They survive a reload, which
// shows the same pair again. Only durations are kept, nothing outside this page.
const TIMING_KEY = 'taste.timing.';
const timing = {
  token: null, running: false, visible: true, focused: true, last: 0, lastInput: 0, totals: null,
};

function idleCutoffMs() {
  return 1000 * ((state.config && state.config.idle_cutoff_seconds) || 120);
}

// Add the time since the last update to the totals, by what the page was doing meanwhile.
function tally(at = Date.now()) {
  if (!timing.running) return;
  const totals = timing.totals;
  const span = Math.max(0, at - timing.last);
  if (timing.visible) {
    totals.visible_ms += span;
    if (timing.focused) {
      totals.focused_ms += span;
      totals.idle_run_ms += span;
      const from = Math.max(timing.last, timing.lastInput);
      totals.active_ms += Math.max(0, Math.min(at, timing.lastInput + idleCutoffMs()) - from);
    }
  }
  timing.last = at;
}

function saveTiming() {
  if (!timing.token || !timing.totals) return;
  try { sessionStorage.setItem(TIMING_KEY + timing.token, JSON.stringify(timing.totals)); } catch (error) { /* private mode */ }
}

function noteInput(force = false) {
  if (!timing.running) return;
  const at = Date.now();
  if (!force && at - timing.lastInput < 1000) return;  // pointer moves come in floods
  tally(at);
  const totals = timing.totals;
  totals.longest_idle_ms = Math.max(totals.longest_idle_ms, totals.idle_run_ms);
  totals.idle_run_ms = 0;
  timing.lastInput = at;
}

function startTiming(token) {
  if (timing.running && timing.token === token) return;
  pauseTiming();
  let totals = null;
  try { totals = JSON.parse(sessionStorage.getItem(TIMING_KEY + token)); } catch (error) { /* none */ }
  if (totals) totals.resumed += 1;
  const at = Date.now();
  Object.assign(timing, {
    token, running: true, last: at, lastInput: at,
    visible: document.visibilityState === 'visible', focused: document.hasFocus(),
    totals: totals || {
      visible_ms: 0, focused_ms: 0, active_ms: 0, away_count: 0, blur_count: 0,
      longest_idle_ms: 0, idle_run_ms: 0, resumed: 0,
    },
  });
}

function pauseTiming() {
  if (!timing.running) return;
  tally();
  saveTiming();
  timing.running = false;
}

function finishTiming(token) {
  try { sessionStorage.removeItem(TIMING_KEY + token); } catch (error) { /* private mode */ }
  if (timing.token === token) Object.assign(timing, { token: null, running: false, totals: null });
}

function timingDetails() {
  tally();
  const t = timing.totals;
  const seconds = (ms) => Math.round(ms / 100) / 10;
  return {
    visible_s: seconds(t.visible_ms),
    focused_s: seconds(t.focused_ms),
    active_s: seconds(t.active_ms),
    away_count: t.away_count,
    blur_count: t.blur_count,
    longest_idle_s: seconds(Math.max(t.longest_idle_ms, t.idle_run_ms)),
    idle_cutoff_s: idleCutoffMs() / 1000,
    resumed: t.resumed,
  };
}

function onVisibility() {
  if (!timing.running) return;
  tally();
  const visible = document.visibilityState === 'visible';
  if (timing.visible && !visible) {
    timing.totals.away_count += 1;
    saveTiming();  // a phone may close a hidden page without warning
  }
  timing.visible = visible;
  if (visible) noteInput(true);  // coming back is a sign of looking
}

function onFocusChange(focused) {
  if (!timing.running) return;
  tally();
  if (timing.focused && !focused) timing.totals.blur_count += 1;
  timing.focused = focused;
  if (focused) noteInput(true);
}
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const saved = {
  get() { try { return localStorage.getItem(STORE_KEY); } catch (error) { return null; } },
  set(value) { try { localStorage.setItem(STORE_KEY, value); } catch (error) { /* private mode */ } },
  clear() { try { localStorage.removeItem(STORE_KEY); } catch (error) { /* private mode */ } },
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', 'X-Invite-Code': state.code || '' },
  });
  let body = {};
  try { body = await response.json(); } catch (error) { /* empty body */ }
  if (!response.ok) {
    const failure = new Error(body.error || `Request failed (${response.status})`);
    failure.status = response.status;
    throw failure;
  }
  return body;
}

function show(id) {
  for (const section of ['sign-in', 'rounds', 'voting', 'done']) $(`#${section}`).hidden = section !== id;
  const signedIn = id !== 'sign-in';
  $('#menu').hidden = !signedIn;
  $('#who').hidden = !signedIn;
  $('#menu').open = false;
  $('#guide-link').hidden = signedIn;
  $('#round-name').hidden = id !== 'voting';
  $('#progress-wrap').hidden = id !== 'voting';
}

function say(text) { $('#message').textContent = text || ''; }

function setBusy(busy) {
  state.busy = busy;
  $('#voting').setAttribute('aria-busy', String(busy));
  for (const button of $$('#vote-form button, .pane .report')) button.disabled = busy;
}

function progressLabel(row) {
  if (row.calibration_total > 0 && row.calibration_done < row.calibration_total) {
    return `Calibration ${row.calibration_done} of ${row.calibration_total}`;
  }
  if (row.target > 0 && row.votes >= row.target) return 'Target reached, thank you';
  if (row.target > 0) return `${row.votes} of ${row.target} votes`;
  if (row.votes === 0) return 'No votes yet';
  return `${row.votes} vote${row.votes === 1 ? '' : 's'}`;
}

function renderProgress(progress) {
  const rows = progress || [];
  for (const label of $$('.round-progress')) {
    const row = rows.find((r) => r.round === label.dataset.round);
    label.textContent = row ? progressLabel(row) : '';
  }
  const row = rows.find((r) => r.round === state.round);
  if (!row) return;
  const calibrating = row.calibration_total > 0 && row.calibration_done < row.calibration_total;
  const share = calibrating ? row.calibration_done / row.calibration_total
    : (row.target > 0 ? Math.min(1, row.votes / row.target) : 0);
  $('#progress').textContent = progressLabel(row);
  $('#progress-wrap').classList.toggle('has-goal', calibrating || row.target > 0);
  $('#progress-bar').style.setProperty('--done', share);
}

async function refreshProgress() {
  try { renderProgress((await api('/api/progress')).progress); } catch (error) { /* shown elsewhere */ }
}

async function signIn(code) {
  state.code = code;
  try {
    const session = await api('/api/session', { method: 'POST' });
    const config = await api('/api/config');
    if (state.code !== code) return;  // another invite link was opened meanwhile
    Object.assign(state, { config, name: session.name, session: newSession(), cast: 0 });
    saved.set(code);
    $('#greeting').textContent = `Hi ${session.name}. Choose a round.`;
    for (const spot of $$('.voter-name')) spot.textContent = session.name;
    renderProgress(session.progress);
    show('rounds');
  } catch (error) {
    if (state.code !== code) return;
    state.code = null;
    saved.clear();
    $('#sign-in-message').textContent = error.status === 401 ? 'That invite code is not valid.' : error.message;
    show('sign-in');
  }
}

// Drop everything about the signed-in voter, including a pair or reel still on screen.
function forget() {
  pauseTiming();
  saved.clear();
  Object.assign(state, {
    code: null, name: null, config: null, round: null, pair: null, pick: null, session: null, cast: 0,
  });
  for (const media of $$('.media')) media.replaceChildren();
  for (const spot of $$('.voter-name')) spot.textContent = '';
}

function signOut() {
  forget();
  $('#invite').value = '';
  show('sign-in');
}

function renderChips() {
  const container = $('#chips');
  container.replaceChildren();
  state.config.dimensions[state.round].forEach((dimension, index) => {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'chip';
    chip.dataset.id = dimension.id;
    chip.title = dimension.description;  // the definition, from the database
    chip.setAttribute('aria-pressed', 'false');
    const key = document.createElement('kbd');
    key.textContent = String(index + 1);
    chip.append(dimension.label, key);
    chip.addEventListener('click', () => toggleChip(chip));
    container.append(chip);
  });
}

function toggleChip(chip) {
  const id = chip.dataset.id;
  if (state.chips.has(id)) {
    state.chips.delete(id);
  } else if (state.chips.size >= state.config.max_dimensions) {
    say(`Pick at most ${state.config.max_dimensions}.`);
    return;
  } else {
    state.chips.add(id);
  }
  say('');
  chip.setAttribute('aria-pressed', String(state.chips.has(id)));
}

// The voter's own words: any wording, kept as typed. There is no list to choose from.
function addTerm(text) {
  const term = text.trim().replace(/\s+/g, ' ');
  if (!term) return true;
  if (state.terms.some((t) => t.toLowerCase() === term.toLowerCase())) return true;
  if (term.length > state.config.max_term_chars) {
    say(`Keep each of your own words under ${state.config.max_term_chars} characters.`);
    return false;
  }
  if (state.terms.length >= state.config.max_own_terms) {
    say(`Add at most ${state.config.max_own_terms} of your own words.`);
    return false;
  }
  state.terms.push(term);
  const chip = document.createElement('button');
  chip.type = 'button';
  chip.className = 'chip own';
  chip.textContent = term;
  chip.setAttribute('aria-label', `Remove "${term}"`);
  chip.addEventListener('click', () => {
    state.terms = state.terms.filter((t) => t !== term);
    chip.remove();
  });
  $('#own-chips').append(chip);
  say('');
  return true;
}

function rememberTerms(terms) {
  const list = $('#own-term-list');
  const known = new Set([...list.options].map((option) => option.value));
  for (const term of terms) {
    if (known.has(term)) continue;
    const option = document.createElement('option');
    option.value = term;
    list.append(option);
  }
}

async function loadTerms() {
  $('#own-term-list').replaceChildren();
  try {
    rememberTerms((await api(`/api/terms?round=${state.round}`)).terms);
  } catch (error) { /* suggestions are a convenience */ }
}

function selectTab(side) {
  for (const s of SIDES) {
    const selected = s === side;
    $(`#tab-${s}`).setAttribute('aria-selected', String(selected));
    $(`#card-${s}`).classList.toggle('is-active', selected);
  }
}

function logEvent(kind) {
  if (!state.pair) return;
  api('/api/event', { method: 'POST', body: JSON.stringify({ token: state.pair.token, kind }) })
    .catch((error) => console.warn('event not recorded', kind, error.message));
}

function renderSide(side, data) {
  const card = $(`#card-${side}`);
  const media = card.querySelector('.media');
  const name = `Site ${LETTER[side]}`;
  const isVideo = state.round === 'motion' && Boolean(data.reel);
  media.replaceChildren();
  media.classList.toggle('is-video', isVideo);
  media.classList.toggle('is-loading', !isVideo);  // a video shows its poster as it arrives
  if (isVideo) {
    const video = document.createElement('video');
    Object.assign(video, { src: data.reel, controls: true, muted: true, playsInline: true, preload: 'none' });
    if (data.stills[0]) video.poster = data.stills[0];
    video.setAttribute('aria-label', `${name} recording`);
    video.addEventListener('play', () => logEvent(`play_${side}`), { once: true });
    video.addEventListener('timeupdate', () => noteInput());  // watching a reel is looking
    media.append(video);
    card.querySelector('.pane-note').textContent = 'Recording';
  } else {
    const strip = document.createElement('div');
    strip.className = 'strip';
    strip.tabIndex = 0;
    strip.setAttribute('aria-label', `${name}: ${data.stills.length} screens, scroll for more`);
    strip.addEventListener('scroll', () => logEvent(`scroll_${side}`), { once: true });
    data.stills.forEach((url, index) => {
      const image = document.createElement('img');
      Object.assign(image, { src: url, alt: `${name}, screen ${index + 1}`, decoding: 'async' });
      image.loading = index === 0 ? 'eager' : 'lazy';
      if (index === 0) {
        const loaded = () => media.classList.remove('is-loading');
        image.addEventListener('load', loaded, { once: true });
        image.addEventListener('error', loaded, { once: true });
      }
      strip.append(image);
    });
    media.append(strip);
    const count = data.stills.length;
    card.querySelector('.pane-note').textContent = count > 1 ? `${count} screens ↓` : '1 screen';
  }
  const live = card.querySelector('.live');
  live.hidden = !data.live_url;
  if (data.live_url) live.href = data.live_url;
}

function resetDecision() {
  state.pick = null;
  state.chips.clear();
  state.terms = [];
  $('#own-chips').replaceChildren();
  $('#own-term').value = '';
  for (const chip of $$('#chips .chip')) chip.setAttribute('aria-pressed', 'false');
  for (const pane of $$('.pane')) pane.classList.remove('is-picked');
  $('#reason').value = '';
  $('#explain').hidden = true;
  $('#decide').hidden = false;
  say('');
}

function pick(outcome) {
  if (!state.pair || state.busy) return;
  state.pick = outcome;
  const [question, help] = QUESTIONS[outcome](state.config.max_dimensions);
  const hint = document.createElement('span');
  hint.className = 'hint';
  hint.textContent = help;
  $('#chips-legend').replaceChildren(question, hint);
  $('#reason').placeholder = PLACEHOLDERS[outcome];
  $('#reason-hint').textContent = state.pair.reason_requested && DECISIVE.includes(outcome)
    ? `(at least ${state.config.min_reason_chars} characters)`
    : '(optional)';
  for (const s of SIDES) $(`#card-${s}`).classList.toggle('is-picked', s === outcome);
  $('#decide').hidden = true;
  $('#explain').hidden = false;
  say('');
  const first = $('#chips .chip');
  if (first) first.focus();
}

async function loadPair() {
  setBusy(true);
  for (const media of $$('.media')) media.classList.add('is-loading');
  const { code, round } = state;
  try {
    const pair = await api(`/api/pair?round=${round}`);
    if (state.code !== code || state.round !== round) return;  // signed out or switched meanwhile
    state.pair = pair;
    startTiming(pair.token);
    for (const side of SIDES) renderSide(side, pair[side]);
    resetDecision();
    selectTab('left');
    refreshProgress();
  } catch (error) {
    state.pair = null;
    pauseTiming();
    if (error.status === 404) show('done');
    else if (error.status === 401) signOut();
    else say(error.message);
  } finally {
    setBusy(false);
  }
}

async function submitVote(outcome) {
  if (!state.pair || state.busy) return;
  const decisive = DECISIVE.includes(outcome);
  const words = outcome.startsWith('broken') ? [] : null;  // a report says nothing about taste
  const reason = $('#reason').value.trim();
  if (!words && !addTerm($('#own-term').value)) return;  // words typed but not yet added
  $('#own-term').value = '';
  if (decisive && state.chips.size === 0 && state.terms.length === 0) {
    say('Say what decided it: pick one, or use your own words.');
    return;
  }
  if (decisive && state.pair.reason_requested && reason.length < state.config.min_reason_chars) {
    say(`Write a reason of at least ${state.config.min_reason_chars} characters.`);
    $('#reason').focus();
    return;
  }
  setBusy(true);
  try {
    const body = {
      token: state.pair.token,
      outcome,
      dimensions: words || [...state.chips],
      terms: words || state.terms,
      reason: words || !reason ? null : reason,
      client: clientDetails(),
    };
    await api('/api/vote', { method: 'POST', body: JSON.stringify(body) });
    finishTiming(body.token);
    state.cast += 1;
    rememberTerms(body.terms);
    await loadPair();
  } catch (error) {
    if (error.status === 409) await loadPair();  // already recorded, e.g. a double click
    else say(error.message);
  } finally {
    setBusy(false);
  }
}

function report(outcome) {
  const letter = outcome === 'broken_left' ? 'A' : 'B';
  const question = `Report site ${letter} as broken (blank, an error, a cookie wall or the wrong site)? `
    + 'It will be taken out for checking.';
  if (window.confirm(question)) submitVote(outcome);
}

function startRound(round) {
  state.round = round;
  $('#voting').dataset.round = round;
  $('#round-name').textContent = round === 'visual' ? 'Visual round' : 'Motion round';
  renderChips();
  loadTerms();
  show('voting');
  loadPair();
}

function chooseRound() {
  pauseTiming();
  state.round = null;
  state.pair = null;
  show('rounds');
  refreshProgress();
}

function onKey(event) {
  if ($('#voting').hidden || event.altKey) return;
  const active = document.activeElement;
  const typing = active && ['INPUT', 'TEXTAREA', 'SELECT'].includes(active.tagName);
  const modified = event.metaKey || event.ctrlKey;
  const key = event.key.toLowerCase();

  if (state.pick) {
    if (key === 'escape') {
      event.preventDefault();
      resetDecision();
    } else if (key === 'enter' && (!typing || modified) && active !== $('#back')) {
      event.preventDefault();
      submitVote(state.pick);
    } else if (!typing && !modified && /^[1-9]$/.test(key)) {
      const chip = $$('#chips .chip')[Number(key) - 1];
      if (chip) {
        event.preventDefault();
        toggleChip(chip);
      }
    }
    return;
  }
  if (typing || modified) return;
  if (PICK_KEYS[key]) {
    event.preventDefault();
    pick(PICK_KEYS[key]);
  }
}

// An invite link (https://…/#invite=CODE) signs the voter in. The code sits in the
// fragment so it never reaches a server log, and it is removed from the address bar.
function inviteFromLink() {
  const match = window.location.hash.match(/^#invite=([^&]+)/);
  if (!match) return null;
  window.history.replaceState(null, '', window.location.pathname + window.location.search);
  try { return decodeURIComponent(match[1]).trim() || null; } catch (error) { return null; }
}

// Opening another invite link in the same tab changes only the part after #, and the browser
// does not reload the page for that: switch to the new voter, or the last one stays signed in.
function onLinkChange() {
  const code = inviteFromLink();
  if (!code || code === state.code) return;
  forget();
  signIn(code);
}

// Voters paste the whole invite link as often as the code: take the code from either.
function inviteCode(text) {
  const match = text.match(/[#?&]invite=([^&\s]+)/);
  try { return (match ? decodeURIComponent(match[1]) : text).trim() || null; } catch (error) { return null; }
}

document.addEventListener('DOMContentLoaded', () => {
  $('#sign-in-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const code = inviteCode($('#invite').value);
    if (code) signIn(code);
  });
  for (const button of $$('.sign-out')) button.addEventListener('click', signOut);
  window.addEventListener('hashchange', onLinkChange);
  $('.wordmark').addEventListener('click', (event) => {
    if (!state.code) return;
    event.preventDefault();
    chooseRound();
  });
  for (const button of $$('.round')) button.addEventListener('click', () => startRound(button.dataset.round));
  for (const button of $$('.change-round')) button.addEventListener('click', chooseRound);
  for (const item of $$('.menu-list > *')) item.addEventListener('click', () => { $('#menu').open = false; });
  document.addEventListener('click', (event) => {
    if ($('#menu').open && !$('#menu').contains(event.target)) $('#menu').open = false;
  });
  for (const side of SIDES) {
    $(`#tab-${side}`).addEventListener('click', () => {
      selectTab(side);
      logEvent(`view_${side}`);  // on a phone: which site the voter chose to look at
    });
  }
  for (const link of $$('.live')) link.addEventListener('click', () => logEvent(`open_live_${link.dataset.side}`));
  for (const button of $$('.pane .report')) button.addEventListener('click', () => report(button.dataset.outcome));
  for (const button of $$('.pick')) button.addEventListener('click', () => pick(button.dataset.pick));
  $('#back').addEventListener('click', resetDecision);
  $('#own-term').addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' || event.metaKey || event.ctrlKey) return;
    event.preventDefault();
    if (addTerm(event.target.value)) event.target.value = '';
  });
  $('#vote-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    if (!submitter) return;
    if (submitter.id === 'submit-vote') submitVote(state.pick);
  });
  document.addEventListener('keydown', onKey);

  document.addEventListener('visibilitychange', onVisibility);
  window.addEventListener('focus', () => onFocusChange(true));
  window.addEventListener('blur', () => onFocusChange(false));
  for (const kind of ['pointermove', 'pointerdown', 'keydown', 'wheel', 'touchstart']) {
    window.addEventListener(kind, () => noteInput(), { passive: true });
  }
  document.addEventListener('scroll', () => noteInput(), { capture: true, passive: true });
  window.addEventListener('pagehide', pauseTiming);  // a reload resumes from the saved totals
  window.addEventListener('pageshow', (event) => {
    if (event.persisted && state.pair && !$('#voting').hidden) startTiming(state.pair.token);
  });

  const code = inviteFromLink() || saved.get();
  if (code) signIn(code);
  else show('sign-in');
});
