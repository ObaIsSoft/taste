'use strict';

// Voting client. Every rule is enforced by the server; checks here only give
// faster feedback, using the limits the server sends in /api/config.
// The screen calls the two sites A and B; the API calls them left and right.

const STORE_KEY = 'taste.inviteCode';
const SIDES = ['left', 'right'];
const LETTER = { left: 'A', right: 'B' };
const PICK_KEYS = { 1: 'left', 2: 'right' };
const OUTCOME_KEYS = { e: 'equally_good', s: 'cant_decide' };

const state = {
  code: null, name: null, config: null, round: null, pair: null, pick: null, chips: new Set(), busy: false,
};
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
  $('#progress').textContent = progressLabel(row);
  $('#progress-wrap').classList.toggle('is-calibrating', calibrating);
  $('#progress-bar').style.setProperty('--done', calibrating ? row.calibration_done / row.calibration_total : 0);
}

async function refreshProgress() {
  try { renderProgress((await api('/api/progress')).progress); } catch (error) { /* shown elsewhere */ }
}

async function signIn(code) {
  state.code = code;
  try {
    const session = await api('/api/session', { method: 'POST' });
    state.config = await api('/api/config');
    state.name = session.name;
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
  Object.assign(state, { code: null, name: null, config: null, round: null, pair: null, pick: null });
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
  if (isVideo) {
    const video = document.createElement('video');
    Object.assign(video, { src: data.reel, controls: true, muted: true, playsInline: true, preload: 'none' });
    if (data.stills[0]) video.poster = data.stills[0];
    video.setAttribute('aria-label', `${name} recording`);
    video.addEventListener('play', () => logEvent(`play_${side}`), { once: true });
    media.append(video);
    card.querySelector('.pane-note').textContent = 'Recording';
  } else {
    const strip = document.createElement('div');
    strip.className = 'strip';
    strip.tabIndex = 0;
    strip.setAttribute('aria-label', `${name}: ${data.stills.length} screens, scroll for more`);
    data.stills.forEach((url, index) => {
      const image = document.createElement('img');
      Object.assign(image, { src: url, alt: `${name}, screen ${index + 1}`, decoding: 'async' });
      image.loading = index === 0 ? 'eager' : 'lazy';
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
  for (const chip of $$('.chip')) chip.setAttribute('aria-pressed', 'false');
  for (const pane of $$('.pane')) pane.classList.remove('is-picked');
  $('#reason').value = '';
  $('#explain').hidden = true;
  $('#decide').hidden = false;
  say('');
}

function pick(side) {
  if (!state.pair || state.busy) return;
  state.pick = side;
  const letter = LETTER[side];
  const legend = $('#chips-legend');
  const hint = document.createElement('span');
  hint.className = 'hint';
  hint.textContent = `Pick 1 to ${state.config.max_dimensions}`;
  legend.replaceChildren(`What made ${letter} better?`, hint);
  $('#reason').placeholder = `${letter} is better because …`;
  $('#reason-hint').textContent = `(at least ${state.config.min_reason_chars} characters)`;
  $('#reason-block').hidden = !state.pair.reason_requested;
  for (const s of SIDES) $(`#card-${s}`).classList.toggle('is-picked', s === side);
  $('#decide').hidden = true;
  $('#explain').hidden = false;
  say('');
  const first = $('.chip');
  if (first) first.focus();
}

async function loadPair() {
  setBusy(true);
  try {
    const pair = await api(`/api/pair?round=${state.round}`);
    state.pair = pair;
    for (const side of SIDES) renderSide(side, pair[side]);
    resetDecision();
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
    const body = {
      token: state.pair.token,
      outcome,
      dimensions: decisive ? [...state.chips] : [],
      reason: decisive && reason ? reason : null,
    };
    await api('/api/vote', { method: 'POST', body: JSON.stringify(body) });
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
  $('#round-name').textContent = round === 'visual' ? 'Visual round' : 'Motion round';
  renderChips();
  show('voting');
  loadPair();
}

function chooseRound() {
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
      const chip = $$('.chip')[Number(key) - 1];
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
  } else if (OUTCOME_KEYS[key]) {
    event.preventDefault();
    submitVote(OUTCOME_KEYS[key]);
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

document.addEventListener('DOMContentLoaded', () => {
  $('#sign-in-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const code = $('#invite').value.trim();
    if (code) signIn(code);
  });
  $('#sign-out').addEventListener('click', signOut);
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
  for (const side of SIDES) $(`#tab-${side}`).addEventListener('click', () => selectTab(side));
  for (const link of $$('.live')) link.addEventListener('click', () => logEvent(`open_live_${link.dataset.side}`));
  for (const button of $$('.pane .report')) button.addEventListener('click', () => report(button.dataset.outcome));
  for (const button of $$('.pick')) button.addEventListener('click', () => pick(button.dataset.pick));
  $('#back').addEventListener('click', resetDecision);
  $('#vote-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    if (!submitter) return;
    if (submitter.id === 'submit-vote') submitVote(state.pick);
    else if (submitter.dataset.outcome) submitVote(submitter.dataset.outcome);
  });
  document.addEventListener('keydown', onKey);

  const code = inviteFromLink() || saved.get();
  if (code) signIn(code);
  else show('sign-in');
});
