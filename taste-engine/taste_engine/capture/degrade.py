"""Degraded twins: the same site with one design dimension deliberately broken.

A twin is captured exactly like the original, with one profile injected on
every page load. The original should beat its twin, so these pairs are
labelled without votes; designers check a sample to confirm it.
"""

from __future__ import annotations

import json

from taste_engine.schemas import Variant

_TYPOGRAPHY_CSS = """
body *:not(svg):not(svg *) {
  font-family: Arial, Helvetica, sans-serif !important; letter-spacing: normal !important;
  word-spacing: normal !important; font-style: normal !important; text-transform: none !important;
}
h1, h2, h3, h4, h5, h6 { font-size: 28px !important; line-height: 1.25 !important; font-weight: 700 !important; }
p, li, a, span, button, label, small, figcaption, blockquote, td, th {
  font-size: 16px !important; line-height: 1.5 !important; font-weight: 400 !important;
}
"""

_COLOUR_CSS = """
html, body { background-color: #ffffff !important; }
body *:not(img):not(video):not(canvas):not(svg):not(svg *) {
  color: #212529 !important; background-color: transparent !important; border-color: #dee2e6 !important;
}
a, a * { color: #0d6efd !important; }
button, [role="button"], input[type="submit"] {
  background-color: #0d6efd !important; color: #ffffff !important; border-color: #0d6efd !important;
}
"""

_SPACING_JS = """
const done = window.__tasteHalved || (window.__tasteHalved = new WeakSet());
for (const el of document.querySelectorAll('body *')) {
  if (done.has(el)) continue;
  done.add(el);
  const cs = getComputedStyle(el);
  for (const prop of ['padding-top', 'padding-bottom', 'padding-left', 'padding-right',
                      'margin-top', 'margin-bottom', 'row-gap', 'column-gap']) {
    const value = parseFloat(cs.getPropertyValue(prop));
    if (value > 0) el.style.setProperty(prop, (value / 2) + 'px', 'important');
  }
}
"""

_LAYOUT_CSS = """
body * {
  max-width: none !important; text-align: left !important; justify-content: flex-start !important;
  align-items: flex-start !important; justify-items: start !important;
  margin-left: 0 !important; margin-right: 0 !important;
}
"""

_PROFILES: dict[Variant, tuple[str, str]] = {
    Variant.TYPOGRAPHY: (_TYPOGRAPHY_CSS, ""),
    Variant.COLOUR: (_COLOUR_CSS, ""),
    Variant.SPACING: ("", _SPACING_JS),
    Variant.LAYOUT: (_LAYOUT_CSS, ""),
}

_TEMPLATE = r"""
(() => {
  if (window.top !== window) return;
  const css = __CSS__;
  const run = () => { __JS__ };
  const apply = () => {
    if (css && !document.getElementById('taste-degrade')) {
      const style = document.createElement('style');
      style.id = 'taste-degrade';
      style.textContent = css;
      (document.head || document.documentElement).appendChild(style);
    }
    run();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', apply);
  else apply();
  window.addEventListener('load', apply);
})();
"""


def init_script(variant: Variant) -> str | None:
    if variant is Variant.ORIGINAL:
        return None
    css, script = _PROFILES[variant]
    return _TEMPLATE.replace("__CSS__", json.dumps(css)).replace("__JS__", script)
