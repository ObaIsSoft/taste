'use strict';

// Voting client. Every rule is enforced by the server; checks here only give
// faster feedback, using the limits the server sends in /api/config.

const STORE_KEY = 'taste.inviteCode';
const SIDES = ['left', 'right'];
const KEYS = { 1: 'left', 2: 'right', e: 'equally_good', s: 'cant_decide' };

const state = { code: null, config: null, round: null, pair: null, chips: new Set(), busy: false };
const $ = (selector) => document.querySelector(selector);

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
  $('#sign-out').hidden = id === 'sign-in';
}

function say(text) { $('#message').textContent = text || ''; }

function setBusy(busy) {
  state.busy = busy;
  $('#voting').setAttribute('aria-busy', String(busy));
  for (const button of document.querySelectorAll('#vote-form button[type="submit"]')) button.disabled = busy;
}

function renderProgress(progress) {
  const rows = progress || [];
  const row = rows.find((r) => r.round === state.round);
  if (row && row.calibration_total > 0 && row.calibration_done < row.calibration_total) {
    $('#progress').textContent = `Calibration ${row.calibration_done} of ${row.calibration_total}`;
  } else {
    const votes = row ? row.votes : rows.reduce((sum, r) => sum + r.votes, 0);
    $('#progress').textContent = `${votes} vote${votes === 1 ? '' : 's'}`;
  }
}

async function refreshProgress() {
  try { renderProgress((await api('/api/progress')).progress); } catch (error) { /* shown elsewhere */ }
}

async function signIn(code) {
  state.code = code;
  try {
    const session = await api('/api/session', { method: 'POST' });
    state.config = await api('/api/config');
    saved.set(code);
    $('#greeting').textContent = `Hi ${session.name}. Choose a round.`;
    renderProgress(session.progress);
    show('rounds');
  } catch (error) {
    state.code = null;
    saved.clear();
    $('#sign-in-message').textContent = error.status === 401 ? 'That invite code is not valid.' : error.message;
    show('sign-in');
  }
}

function signOut() {
  saved.clear();
  Object.assign(state, { code: null, config: null, round: null, pair: null });
  $('#progress').textContent = '';
  show('sign-in');
}

function renderChips() {
  const max = state.config.max_dimensions;
  $('#chips-legend').textContent = `What decided it? Pick 1 to ${max}`;
  const container = $('#chips');
  container.replaceChildren();
  for (const dimension of state.config.dimensions[state.round]) {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'chip';
    chip.dataset.id = dimension.id;
    chip.textContent = dimension.label;
    chip.setAttribute('aria-pressed', 'false');
    chip.addEventListener('click', () => toggleChip(chip));
    container.append(chip);
  }
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
  media.replaceChildren();
  if (state.round === 'motion' && data.reel) {
    const video = document.createElement('video');
    Object.assign(video, { src: data.reel, controls: true, muted: true, playsInline: true, preload: 'none' });
    if (data.stills[0]) video.poster = data.stills[0];
    video.setAttribute('aria-label', `${side} site recording`);
    video.addEventListener('play', () => logEvent(`play_${side}`), { once: true });
    media.append(video);
  } else {
    const strip = document.createElement('div');
    strip.className = 'strip';
    strip.tabIndex = 0;
    strip.setAttribute('aria-label', `${side} site: ${data.stills.length} screens, scroll for more`);
    data.stills.forEach((url, index) => {
      const image = document.createElement('img');
      Object.assign(image, { src: url, alt: `${side} site, screen ${index + 1}`, decoding: 'async' });
      image.loading = index === 0 ? 'eager' : 'lazy';
      strip.append(image);
    });
    media.append(strip);
  }
  card.querySelector('.live').href = data.live_url;
}

async function loadPair() {
  say('');
  setBusy(true);
  try {
    const pair = await api(`/api/pair?round=${state.round}`);
    state.pair = pair;
    for (const side of SIDES) renderSide(side, pair[side]);
    state.chips.clear();
    for (const chip of document.querySelectorAll('.chip')) chip.setAttribute('aria-pressed', 'false');
    $('#reason').value = '';
    $('#reason-block').hidden = !pair.reason_requested;
    $('#reason-hint').textContent = `(at least ${state.config.min_reason_chars} characters)`;
    selectTab('left');
    refreshProgress();
  } catch (error) {
    state.pair = null;
    if (error.status === 404) show('done');
    else if (error.status === 401) signOut();
    else say(error.message);
  } finally {
    setBusy(false);
  }
}

async function submitVote(outcome) {
  if (!state.pair || state.busy) return;
  const decisive = outcome === 'left' || outcome === 'right';
  const reason = $('#reason').value.trim();
  if (decisive && state.chips.size === 0) {
    say('Pick at least one thing that decided it.');
    return;
  }
  if (decisive && state.pair.reason_requested && reason.length < state.config.min_reason_chars) {
    say(`Write a reason of at least ${state.config.min_reason_chars} characters.`);
    $('#reason').focus();
    return;
  }
  setBusy(true);
  try {
    const body = { token: state.pair.token, outcome, dimensions: [...state.chips], reason: reason || null };
    await api('/api/vote', { method: 'POST', body: JSON.stringify(body) });
    await loadPair();
  } catch (error) {
    if (error.status === 409) await loadPair();  // already recorded, e.g. a double click
    else say(error.message);
  } finally {
    setBusy(false);
  }
}

function startRound(round) {
  state.round = round;
  $('#round-name').textContent = round === 'visual' ? 'Visual round' : 'Motion round';
  renderChips();
  show('voting');
  loadPair();
}

function chooseRound() {
  state.round = null;
  show('rounds');
  refreshProgress();
}

document.addEventListener('DOMContentLoaded', () => {
  $('#sign-in-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const code = $('#invite').value.trim();
    if (code) signIn(code);
  });
  $('#sign-out').addEventListener('click', signOut);
  for (const button of document.querySelectorAll('.round')) {
    button.addEventListener('click', () => startRound(button.dataset.round));
  }
  for (const button of document.querySelectorAll('.change-round')) button.addEventListener('click', chooseRound);
  for (const side of SIDES) $(`#tab-${side}`).addEventListener('click', () => selectTab(side));
  for (const link of document.querySelectorAll('.live')) {
    link.addEventListener('click', () => logEvent(`open_live_${link.dataset.side}`));
  }
  $('#vote-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const outcome = event.submitter && event.submitter.dataset.outcome;
    if (outcome) submitVote(outcome);
  });
  document.addEventListener('keydown', (event) => {
    if ($('#voting').hidden || event.metaKey || event.ctrlKey || event.altKey) return;
    const target = document.activeElement;
    if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return;
    const outcome = KEYS[event.key.toLowerCase()];
    if (outcome) {
      event.preventDefault();
      submitVote(outcome);
    }
  });

  const code = saved.get();
  if (code) signIn(code);
  else show('sign-in');
});
