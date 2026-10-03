"""JavaScript run inside captured pages. All in-page code lives here.

``init_script`` is passed to ``context.add_init_script``, which executes the
source as-is, so it must be an immediately invoked function. The others are
function expressions for ``page.evaluate``, which calls them with one argument.
"""

from __future__ import annotations

import json

_INIT_TEMPLATE = r"""
(() => {
  if (window.top !== window || window.__taste) return;
  const MAX_CALLS = __MAX_CALLS__;
  const POLL_MS = __POLL_MS__;
  const state = (window.__taste = {
    perf: { fcp: null, lcp: null, cls: 0, longTasks: 0, longTaskMs: 0 },
    gsapCalls: [],
    gsapSeen: false,
    canvasContexts: {},
    styleMutations: 0,
    frames: null,
  });

  const observe = (type, handler) => {
    try {
      new PerformanceObserver((list) => list.getEntries().forEach(handler))
        .observe({ type, buffered: true });
    } catch (e) {}
  };
  observe('paint', (e) => { if (e.name === 'first-contentful-paint') state.perf.fcp = e.startTime; });
  observe('largest-contentful-paint', (e) => { state.perf.lcp = e.startTime; });
  observe('layout-shift', (e) => { if (!e.hadRecentInput) state.perf.cls += e.value; });
  observe('longtask', (e) => { state.perf.longTasks += 1; state.perf.longTaskMs += e.duration; });

  const getContext = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (type, ...rest) {
    state.canvasContexts[type] = (state.canvasContexts[type] || 0) + 1;
    return getContext.call(this, type, ...rest);
  };

  const countTargets = (t) => {
    try {
      if (!t) return 0;
      if (typeof t === 'string') return document.querySelectorAll(t).length;
      if (typeof t.length === 'number') return t.length;
      return 1;
    } catch (e) { return 0; }
  };
  const isVars = (a) => a && typeof a === 'object' && !Array.isArray(a) && !(a instanceof Element);
  const record = (method, target, vars) => {
    if (state.gsapCalls.length >= MAX_CALLS) return;
    vars = vars || {};
    state.gsapCalls.push({
      method,
      targets: countTargets(target),
      duration: typeof vars.duration === 'number' ? vars.duration : null,
      ease: typeof vars.ease === 'string' ? vars.ease : null,
      delay: typeof vars.delay === 'number' ? vars.delay : null,
      stagger: vars.stagger !== undefined,
      scroll_trigger: vars.scrollTrigger !== undefined,
      at_ms: Math.round(performance.now()),
    });
  };
  const wrapTweens = (owner, prefix) => {
    for (const method of ['to', 'from', 'fromTo', 'set']) {
      const original = owner[method];
      if (typeof original !== 'function') continue;
      owner[method] = function (...args) {
        record(prefix + method, args[0], args.slice(1).reverse().find(isVars));
        return original.apply(this, args);
      };
    }
  };
  const wrap = (gsap) => {
    if (!gsap || gsap.__tasteWrapped) return;
    try {
      gsap.__tasteWrapped = true;
      state.gsapSeen = true;
      wrapTweens(gsap, '');
      const timeline = gsap.timeline;
      if (typeof timeline === 'function') {
        gsap.timeline = function (...args) {
          record('timeline', null, isVars(args[0]) ? args[0] : null);
          const tl = timeline.apply(this, args);
          if (tl) wrapTweens(tl, 'timeline.');
          return tl;
        };
      }
    } catch (e) {}
  };
  let current = window.gsap;
  try {
    Object.defineProperty(window, 'gsap', {
      configurable: true,
      enumerable: true,
      get() { return current; },
      set(value) { current = value; wrap(value); },
    });
  } catch (e) {}
  if (current) wrap(current);
  const pollStart = Date.now();
  const poll = setInterval(() => {
    if (window.gsap) wrap(window.gsap);
    if (Date.now() - pollStart > POLL_MS) clearInterval(poll);
  }, 100);

  try {
    new MutationObserver((records) => {
      for (const r of records) {
        const v = r.target && r.target.getAttribute && r.target.getAttribute('style');
        if (v && (v.includes('transform') || v.includes('opacity'))) state.styleMutations += 1;
      }
    }).observe(document, { attributes: true, attributeFilter: ['style'], subtree: true });  // <html> does not exist yet when init scripts run
  } catch (e) {}

  state.startFrames = () => {
    state.frames = [];
    let last = performance.now();
    const tick = (now) => {
      if (!state.frames) return;
      state.frames.push(now - last);
      last = now;
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  };
  state.stopFrames = () => {
    const frames = state.frames || [];
    state.frames = null;
    return frames;
  };
})();
"""


def init_script(max_gsap_calls: int, gsap_poll_s: float) -> str:
    return _INIT_TEMPLATE.replace("__MAX_CALLS__", json.dumps(max_gsap_calls)).replace(
        "__POLL_MS__", json.dumps(int(gsap_poll_s * 1000))
    )


START_FRAMES = "() => window.__taste && window.__taste.startFrames()"
STOP_FRAMES = "() => (window.__taste ? window.__taste.stopFrames() : [])"

SCROLL_STATE = """() => ({
  y: window.scrollY,
  height: Math.max(document.documentElement.scrollHeight,
                   document.body ? document.body.scrollHeight : 0),
})"""

SCROLL_TO = "(y) => window.scrollTo(0, y)"

TEXT_SAMPLE = "(n) => (document.body ? document.body.innerText : '').slice(0, n)"

RUNNING_ANIMATIONS = (
    "() => document.getAnimations().filter((a) => a.playState === 'running').length"
)

EXTRACT_DOM = r"""(maxElements) => {
  const vw = window.innerWidth, vh = window.innerHeight, sy = window.scrollY;
  const elements = [];
  const fonts = new Map(), sizes = new Map(), textColors = new Map(), backgrounds = new Map();
  const spacing = new Map(), radii = new Map();
  let shadows = 0, visited = 0;
  const bump = (map, key, by = 1) => map.set(key, (map.get(key) || 0) + by);
  const family = (cs) => cs.fontFamily.split(',')[0].replace(/["']/g, '').trim();
  const LANDMARKS = new Set(['h1', 'h2', 'h3', 'h4', 'p', 'a', 'button', 'img', 'video', 'canvas',
    'svg', 'section', 'header', 'footer', 'nav', 'main', 'li', 'input', 'form']);
  for (const el of document.body ? document.body.querySelectorAll('*') : []) {
    if (visited >= maxElements) break;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    visited += 1;
    const hasText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (hasText) {
      bump(fonts, family(cs));
      bump(sizes, Math.round(parseFloat(cs.fontSize)));
      bump(textColors, cs.color);
    }
    if (cs.backgroundColor && cs.backgroundColor !== 'rgba(0, 0, 0, 0)') {
      bump(backgrounds, cs.backgroundColor, Math.round(r.width * r.height));
    }
    for (const p of ['paddingTop', 'paddingBottom', 'paddingLeft', 'paddingRight',
                     'marginTop', 'marginBottom', 'rowGap', 'columnGap']) {
      const v = Math.round(parseFloat(cs[p]));
      if (v > 0) bump(spacing, v);
    }
    const radius = Math.round(parseFloat(cs.borderTopLeftRadius));
    if (radius > 0) bump(radii, radius);
    if (cs.boxShadow && cs.boxShadow !== 'none') shadows += 1;
    const tag = el.tagName.toLowerCase();
    if (!hasText && !LANDMARKS.has(tag)) continue;
    elements.push({
      tag,
      role: el.getAttribute('role'),
      text_length: hasText ? (el.innerText || '').trim().length : 0,
      x: Math.round(r.left), y: Math.round(r.top + sy), w: Math.round(r.width), h: Math.round(r.height),
      font_family: hasText ? family(cs) : null,
      font_size: parseFloat(cs.fontSize),
      font_weight: parseInt(cs.fontWeight, 10) || null,
      line_height: cs.lineHeight,
      letter_spacing: cs.letterSpacing,
      color: cs.color,
      background: cs.backgroundColor,
      position: cs.position,
      z_index: cs.zIndex,
    });
  }
  const ranked = (map, n, key) => [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, n)
    .map(([k, v]) => ({ [key]: k, count: v }));
  return {
    viewport: { width: vw, height: vh },
    page_height: Math.max(document.documentElement.scrollHeight,
                          document.body ? document.body.scrollHeight : 0),
    title: document.title,
    elements,
    tokens: {
      fonts: ranked(fonts, 12, 'family'),
      font_sizes: ranked(sizes, 24, 'px'),
      text_colors: ranked(textColors, 16, 'color'),
      background_colors: ranked(backgrounds, 16, 'color'),
      spacing: ranked(spacing, 24, 'px'),
      radii: ranked(radii, 12, 'px'),
      shadows,
    },
  };
}"""

ANIMATIONS = r"""(maxAnimations) => {
  const describe = (el) => {
    if (!el || !el.tagName) return null;
    const tag = el.tagName.toLowerCase();
    if (el.id) return tag + '#' + el.id;
    const cls = typeof el.className === 'string'
      ? el.className.trim().split(/\s+/).filter(Boolean).slice(0, 2) : [];
    return cls.length ? tag + '.' + cls.join('.') : tag;
  };
  return document.getAnimations().slice(0, maxAnimations).map((a) => {
    const timing = a.effect && a.effect.getTiming ? a.effect.getTiming() : {};
    return {
      kind: a.constructor ? a.constructor.name : 'Animation',
      name: a.animationName || a.transitionProperty || a.id || null,
      target: describe(a.effect && a.effect.target),
      duration_ms: typeof timing.duration === 'number' ? timing.duration : null,
      delay_ms: typeof timing.delay === 'number' ? timing.delay : null,
      iterations: Number.isFinite(timing.iterations) ? timing.iterations : -1,
      easing: timing.easing || null,
    };
  });
}"""

PAGE_SIGNALS = r"""() => {
  const t = window.__taste || { perf: {}, canvasContexts: {} };
  const resources = performance.getEntriesByType('resource');
  const nav = performance.getEntriesByType('navigation')[0];
  let bytes = nav ? (nav.transferSize || 0) : 0;
  for (const r of resources) bytes += r.transferSize || 0;
  const names = resources.map((r) => r.name.toLowerCase());
  const loaded = (re) => names.some((n) => re.test(n));
  const gl = t.canvasContexts || {};
  return {
    perf: {
      fcp: t.perf.fcp, lcp: t.perf.lcp, cls: t.perf.cls,
      long_tasks: t.perf.longTasks, long_task_ms: t.perf.longTaskMs,
    },
    transfer_bytes: bytes,
    request_count: resources.length + 1,
    style_mutations: t.styleMutations || 0,
    gsap_calls: (t.gsapCalls || []).slice(),
    libraries: {
      gsap: !!window.gsap || !!t.gsapSeen || loaded(/gsap|greensock/),
      scroll_trigger: !!window.ScrollTrigger || loaded(/scrolltrigger/),
      three: !!window.THREE || loaded(/three(\.module)?(\.min)?\.js|\/three@/),
      lenis: !!window.lenis || !!document.querySelector('html.lenis, .lenis') || loaded(/lenis/),
      locomotive: !!document.querySelector('[data-scroll-container], .has-scroll-smooth')
        || loaded(/locomotive/),
      lottie: !!(window.lottie || window.bodymovin)
        || !!document.querySelector('lottie-player, dotlottie-player') || loaded(/lottie|bodymovin/),
      framer: !!document.querySelector('[data-framer-component-type], [data-framer-name]'),
      webflow_interactions: !!document.querySelector('[data-w-id]'),
      webgl: !!(gl.webgl || gl.webgl2 || gl['experimental-webgl']),
    },
  };
}"""

REDUCED_MOTION_QUERY = r"""() => {
  const walk = (rules) => {
    for (const r of rules) {
      if (r.media && r.media.mediaText && r.media.mediaText.includes('prefers-reduced-motion')) return true;
      if (r.cssRules && walk(r.cssRules)) return true;
    }
    return false;
  };
  for (const sheet of document.styleSheets) {
    try { if (walk(sheet.cssRules)) return true; } catch (e) {}
  }
  return false;
}"""

CONSENT_VISIBLE = r"""([scopes, minRatio]) => {
  const vw = innerWidth, vh = innerHeight, hits = new Set();
  for (const selector of scopes) {
    let nodes = [];
    try { nodes = document.querySelectorAll(selector); } catch (e) { continue; }
    for (const el of nodes) {
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) continue;
      const overlay = ['fixed', 'sticky', 'absolute'].includes(cs.position)
        || el.getAttribute('role') === 'dialog' || el.getAttribute('aria-modal') === 'true';
      if (!overlay) continue;
      const r = el.getBoundingClientRect();
      const w = Math.max(0, Math.min(r.right, vw) - Math.max(r.left, 0));
      const h = Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0));
      if ((w * h) / (vw * vh) >= minRatio && /cookie|consent|privacy|gdpr/i.test(el.innerText || '')) {
        hits.add(selector);
      }
    }
  }
  return [...hits];
}"""

BLOCKING_OVERLAY = r"""([coverRatio, maxControls, maxChars]) => {
  for (const old of document.querySelectorAll('[data-taste-gate]')) old.removeAttribute('data-taste-gate');
  const vw = innerWidth, vh = innerHeight, grid = 5, hits = new Map();
  const covers = (el) => {
    const r = el.getBoundingClientRect();
    return r.width >= vw * 0.9 && r.height >= vh * 0.9;
  };
  // Every fixed or absolute layer covering the screen at a point counts, not only the innermost:
  // a gate is often a backdrop and a box side by side inside one wrapper.
  for (let i = 1; i <= grid; i++) {
    for (let j = 1; j <= grid; j++) {
      let n = document.elementFromPoint((vw * i) / (grid + 1), (vh * j) / (grid + 1));
      for (; n && n !== document.body && n !== document.documentElement; n = n.parentElement) {
        const position = getComputedStyle(n).position;
        if ((position === 'fixed' || position === 'absolute') && covers(n)) hits.set(n, (hits.get(n) || 0) + 1);
      }
    }
  }
  const shown = (el) => {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none';
  };
  const depth = (el) => { let d = 0; for (; el; el = el.parentElement) d += 1; return d; };
  let layer = null, text = '';
  for (const [el, count] of hits) {
    if (count < coverRatio * grid * grid) continue;
    const controls = [...el.querySelectorAll(
      'a, button, [role="button"], input[type="submit"], input[type="button"]')].filter(shown);
    const words = (el.innerText || '').replace(/\s+/g, ' ').trim();
    if (!controls.length || controls.length > maxControls || words.length > maxChars) continue;
    if (!layer || depth(el) > depth(layer)) { layer = el; text = words; }  // the most specific
  }
  if (!layer) return null;
  layer.setAttribute('data-taste-gate', '');
  return { text: text.slice(0, 300) };
}"""
FIND_POPUP = r"""([minArea, maxControls]) => {
  for (const old of document.querySelectorAll('[data-taste-popup]')) old.removeAttribute('data-taste-popup');
  const vw = innerWidth, vh = innerHeight;
  const shown = (el) => {
    const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    return cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity) > 0.05
      && r.width > 0 && r.height > 0;
  };
  let best = null;
  for (const el of document.querySelectorAll('body *')) {
    const dialog = el.matches('dialog[open], [role="dialog"], [role="alertdialog"], [aria-modal="true"]');
    const cs = getComputedStyle(el);
    if ((!dialog && cs.position !== 'fixed') || !shown(el)) continue;
    const r = el.getBoundingClientRect();
    const w = Math.max(0, Math.min(r.right, vw) - Math.max(r.left, 0));
    const h = Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0));
    if ((w * h) / (vw * vh) < minArea) continue;
    if (!dialog && r.width >= vw * 0.9 && r.height <= vh * 0.25) continue;  // a header or footer bar
    const controls = [...el.querySelectorAll(
      'a, button, [role="button"], input[type="submit"], input[type="button"]')].filter(shown);
    if (!controls.length || controls.length > maxControls) continue;
    const z = parseInt(cs.zIndex, 10) || 0;
    if (!best || z > best.z) best = { el, z };
  }
  if (!best) return null;
  best.el.setAttribute('data-taste-popup', '');
  return { text: (best.el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 300) };
}"""
POPUP_GONE = "() => { const el = document.querySelector('[data-taste-popup]'); if (!el) return true; const cs = getComputedStyle(el), r = el.getBoundingClientRect(); return cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) <= 0.05 || r.width === 0 || r.height === 0; }"
SCROLL_INNER = r"""(distance) => {
  let best = null, area = 0;
  for (const el of document.querySelectorAll('body *')) {
    if (el.scrollHeight - el.clientHeight < 100) continue;
    if (!['auto', 'scroll', 'overlay'].includes(getComputedStyle(el).overflowY)) continue;
    const r = el.getBoundingClientRect();
    const w = Math.max(0, Math.min(r.right, innerWidth) - Math.max(r.left, 0));
    const h = Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0));
    if (w * h > area) { best = el; area = w * h; }
  }
  if (!best || area < 0.5 * innerWidth * innerHeight) return null;
  const before = best.scrollTop;
  best.scrollTop = before + distance;
  return { moved: best.scrollTop - before, top: best.scrollTop };
}"""
IDLE_MOTION = r"""(ms) => new Promise((resolve) => {
  const t = window.__taste;
  if (!t) return resolve(null);
  const start = t.styleMutations;
  setTimeout(() => resolve(t.styleMutations - start), ms);
})"""
HOVER_TARGETS = r"""(n) => {
  const vw = innerWidth, vh = innerHeight, out = [], seen = new Set();
  for (const el of document.querySelectorAll('header a, header button, nav a, nav button, a, button')) {
    if (out.length >= n) break;
    if (seen.has(el)) continue;
    seen.add(el);
    const r = el.getBoundingClientRect();
    if (r.width < 8 || r.height < 8 || r.top < 0 || r.left < 0 || r.bottom > vh || r.right > vw) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) continue;
    out.push({ x: r.left + r.width / 2, y: r.top + r.height / 2 });
  }
  return out;
}"""

MENU_BUTTON = r"""() => {
  const vw = innerWidth, vh = innerHeight;
  const NAMES = ['menu', 'open menu', 'menú', 'menü', 'menu ouvrir', '☰', '≡'];
  const named = (el) => NAMES.includes((el.innerText || '').trim().toLowerCase());
  const specific = 'button[aria-label*="menu" i], [role="button"][aria-label*="menu" i], '
    + 'a[aria-label*="menu" i], button[aria-controls*="menu" i], button[aria-controls*="nav" i], '
    + '[class*="hamburger" i], [class*="burger" i], [class*="menu-toggle" i], '
    + '[class*="menu-button" i], [class*="nav-toggle" i]';
  const candidates = [...document.querySelectorAll(specific),
    ...[...document.querySelectorAll('button, [role="button"]')].filter(named)];
  for (const el of candidates) {
    const r = el.getBoundingClientRect();
    if (r.width < 8 || r.height < 8 || r.top < 0 || r.left < 0 || r.bottom > vh || r.right > vw) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) continue;
    const href = el.tagName === 'A' ? el.getAttribute('href') : null;
    if (href && !href.startsWith('#')) continue;
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }
  return null;
}"""
