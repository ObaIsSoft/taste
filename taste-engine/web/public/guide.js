'use strict';

// Fills the voter guide from /api/config, so its numbers and definitions are always the ones the
// voting page uses, straight from the database.

document.addEventListener('DOMContentLoaded', async () => {
  let config;
  try {
    const response = await fetch('/api/config');
    if (!response.ok) throw new Error(`config ${response.status}`);
    config = await response.json();
  } catch (error) {
    for (const list of document.querySelectorAll('[data-dimensions]')) {
      list.querySelector('dt').textContent = 'The list is shown on the voting page.';
    }
    return;
  }
  for (const span of document.querySelectorAll('[data-fact]')) {
    const value = span.dataset.fact.split('.').reduce((node, key) => (node ? node[key] : undefined), config);
    if (value !== undefined) span.textContent = String(value);
  }
  for (const list of document.querySelectorAll('[data-dimensions]')) {
    list.replaceChildren(...(config.dimensions[list.dataset.dimensions] || []).map((dimension) => {
      const row = document.createElement('div');
      const term = document.createElement('dt');
      const meaning = document.createElement('dd');
      term.textContent = dimension.label;
      meaning.textContent = dimension.description;
      row.append(term, meaning);
      return row;
    }));
  }
});
