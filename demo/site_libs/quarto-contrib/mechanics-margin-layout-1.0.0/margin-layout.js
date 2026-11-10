/* A single live DOM instance remains at its source parent. Only its CSS box moves.
 * No Python, widget mounting, Plotly resize or document scrolling occurs here.
 * Geometry reads happen on invalidation; scrolling uses cached document bounds.
 */
(() => {
  'use strict';
  const SELECTOR = '.margin-item';
  const ids = value => [...new Set((value || '').trim().split(/\s+/).filter(Boolean))];
  class MarginLayout {
    constructor(root = document, pins = new Set()) {
      this.root = root;
      this.main = root.querySelector('main.content') || root.querySelector('main');
      if (!this.main) return;
      this.entries = new Map();
      this.pins = pins;
      this.abort = new AbortController();
      this.dirty = true;
      this.scanDirty = true;
      this.frame = 0;
      this.wide = false;
      this.printing = false;
      this.pointer = null;
      this.diagnostics = new Set();
      this.metrics = { measurements: 0, frames: 0, scans: 0 };
      this.rail = document.createElement('div');
      this.rail.className = 'margin-layout-rail';
      this.rail.tabIndex = 0;
      this.rail.setAttribute('role', 'region');
      this.rail.setAttribute('aria-label', 'Margin items. Scroll to see more items.');
      this.spacer = this.rail.appendChild(document.createElement('div'));
      this.spacer.className = 'margin-layout-rail-spacer';
      this.probe = document.createElement('div');
      this.probe.className = 'margin-layout-body-probe';
      this.rightProbe = document.createElement('div');
      this.rightProbe.className = 'margin-layout-right-probe';
      this.main.append(this.probe, this.rightProbe, this.rail);
      const signal = this.abort.signal;
      this.listen = (target, name, fn, options = {}) =>
        target.addEventListener(name, fn, { ...options, signal });
      this.listen(window, 'scroll', () => this.schedule(), { passive: true });
      this.listen(window, 'resize', () => this.invalidate());
      this.listen(window, 'beforeprint', () => { this.printing = true; this.measure(); this.render(); });
      this.listen(window, 'afterprint', () => { this.printing = false; this.invalidate(); });
      this.listen(this.rail, 'scroll', () => this.schedule(), { passive: true });
      this.listen(this.main, 'load', () => this.invalidate(), { capture: true });
      this.listen(this.main, 'focusin', event => this.focus(event));
      this.listen(this.main, 'focusout', () => this.schedule());
      this.listen(this.main, 'pointerdown', event => {
        this.pointer = [...this.entries.values()].find(e => e.el.contains(event.target)) || null;
        this.schedule();
      });
      this.listen(window, 'pointerup', () => { this.pointer = null; this.schedule(); });
      this.listen(window, 'pointercancel', () => { this.pointer = null; this.schedule(); });
      this.listen(document, 'mechanics:margin-content', event => {
        const { id, state } = event.detail || {};
        const entry = [...this.entries.values()].find(e => e.el.id === id);
        if (entry) {
          if (state === 'updating') entry.updateHeld = entry.shown && entry.y !== null;
          else entry.updateHeld = false;
          if (state === 'ready') entry.hasResult = true;
          entry.status.textContent = state === 'updating' ? 'Updating…' :
            state === 'stale' ? 'Previous result — update failed' : '';
          entry.el.setAttribute('aria-busy', String(state === 'updating'));
        }
        this.scanDirty = true;
        this.invalidate();
      });
      this.resize = new ResizeObserver(() => this.invalidate());
      this.mutation = new MutationObserver(records => {
        // Attribute writes made by this layout are intentionally not observed.
        if (records.some(record => !record.target.closest?.('.margin-layout-toolbar, .margin-layout-rail'))) {
          this.scanDirty = true;
          this.invalidate();
        }
      });
      this.mutation.observe(this.main, { childList: true, subtree: true, characterData: true,
        attributes: true, attributeFilter: ['id', 'margin-for', 'margin-at', 'data-margin-for', 'data-margin-at', 'data-state'] });
      this.documentObserver = new MutationObserver(() => {
        if (!this.main.isConnected) start();
      });
      this.documentObserver.observe(document.body, { childList: true, subtree: true });
      this.resize.observe(this.main);
      this.header = root.querySelector('#mechanics-header, header.fixed-top');
      if (this.header) this.resize.observe(this.header);
      document.fonts?.ready.then(() => this.invalidate());
      if (document.fonts) this.listen(document.fonts, 'loadingdone', () => this.invalidate());
      this.listen(window, 'pagehide', () => this.destroy());
      this.listen(document, 'click', event => this.navigate(event));
      this.invalidate();
    }
    warn(message, el) {
      if (this.diagnostics.has(message)) return;
      this.diagnostics.add(message);
      console.warn(`[margin-layout] ${message}`, el);
      document.dispatchEvent(new CustomEvent('mechanics:margin-diagnostic', { detail: { message } }));
    }
    invalidate() { this.dirty = true; this.schedule(); }
    schedule() {
      if (!this.frame) this.frame = requestAnimationFrame(() => {
        this.frame = 0;
        if (this.dirty) this.measure();
        this.render();
      });
    }
    adapters() {
      // Quarto creates sidenotes after citeproc/crossref. Hide only its duplicate
      // margin rendering, keep the canonical bibliography/footnote for print.
      const references = new Map();
      for (const marker of this.main.querySelectorAll('a[role="doc-noteref"], .citation a[role="doc-biblioref"]')) {
        const href = marker.getAttribute('href') || '';
        if (!href.startsWith('#')) continue;
        let id;
        try { id = decodeURIComponent(href.slice(1)); } catch { continue; }
        const target = document.getElementById(id);
        if (!target || target.closest(SELECTOR)) continue;
        if (!references.has(target)) references.set(target, []);
        references.get(target).push(marker);
      }
      return references;
    }
    scan() {
      this.metrics.scans++;
      const idMap = new Map();
      for (const el of this.root.querySelectorAll('[id]')) {
        const matches = idMap.get(el.id) || [];
        matches.push(el); idMap.set(el.id, matches);
      }
      for (const el of this.main.querySelectorAll('.margin-scope, .margin-anchor')) {
        if (!el.id || idMap.get(el.id)?.length !== 1) this.warn(`Scope/anchor requires a unique ID: ${el.id || '(missing)'}.`, el);
      }
      const candidates = new Map([...this.main.querySelectorAll(SELECTOR + ', .column-margin:not(.column-container), .column-margin.column-container > *')].map(el => [el, null]));
      for (const [el, entry] of this.entries) if (entry.legacyMargin && this.main.contains(el)) candidates.set(el, null);
      for (const [el, markers] of this.adapters()) candidates.set(el, markers);
      // 旧column-container直下へ挿入した位置マーカーも一致するため，生成資材は再管理しない．
      for (const el of candidates.keys()) {
        if (el.closest('.margin-layout-source, .margin-layout-toolbar, .margin-layout-rail, .margin-layout-body-probe')) candidates.delete(el);
      }
      for (const [el, entry] of this.entries) {
        if (!candidates.has(el)) { this.resize.unobserve(el); this.restore(entry); entry.source.remove(); entry.toolbar.remove(); this.entries.delete(el); }
      }
      for (const [el, markers] of candidates) {
        if (el.parentElement?.closest(SELECTOR)) {
          this.warn('Nested margin items remain in source flow.', el); continue;
        }
        let entry = this.entries.get(el);
        if (!entry) {
          const source = document.createElement('span');
          source.className = 'margin-layout-source'; source.setAttribute('aria-hidden', 'true');
          el.before(source);
          const toolbar = document.createElement('div'); toolbar.className = 'margin-layout-toolbar';
          const status = toolbar.appendChild(document.createElement('span'));
          status.setAttribute('role', 'status');
          const button = markers ? null : toolbar.appendChild(document.createElement('button'));
          if (button) {
            button.type = 'button';
            button.innerHTML = '<svg class="margin-layout-pin-icon" viewBox="0 0 16 16" aria-hidden="true"><path class="margin-layout-pin-head" d="M5 2h6v1h-1v4l2 2v1H4V9l2-2V3H5Z"/><path d="M8 10v4"/></svg>';
          }
          el.prepend(toolbar);
          entry = { el, source, toolbar, button, status, ranges: [], original: el.getAttribute('style'),
            legacyMargin: el.classList.contains('column-margin'), originalInert: el.inert, originalHidden: el.getAttribute('aria-hidden'), valid: true, y: null };
          this.entries.set(el, entry);
          this.resize.observe(el);
          if (button) this.listen(button, 'click', () => {
            entry.pinned = !entry.pinned;
            if (el.id) entry.pinned ? this.pins.add(el.id) : this.pins.delete(el.id);
            this.pinState(entry); this.schedule();
          });
          this.listen(el, 'wheel', event => {
            // Native inner scrolling consumes tall content first. The rail's
            // scrollbar/keyboard also exposes an overcrowded pinned stack.
            const canScroll = event.deltaY > 0 ? el.scrollTop + el.clientHeight < el.scrollHeight - 1 : el.scrollTop > 0;
            if (!canScroll && this.wide && this.rail.scrollHeight > this.rail.clientHeight) {
              this.rail.scrollTop += event.deltaY; event.preventDefault();
            }
          }, { passive: false });
        }
        if (markers && el.parentElement.classList.contains('column-margin')) {
          entry.host = el.parentElement;
          entry.host.classList.remove('column-margin', 'column-container');
          entry.host.classList.add('margin-layout-adapter-host');
        }
        if (entry.legacyMargin) el.classList.remove('column-margin');
        entry.pinnable = !markers;
        if (!entry.pinnable) { entry.pinned = false; this.pins.delete(el.id); }
        else entry.pinned = entry.pinned || (el.id && this.pins.has(el.id));
        this.pinState(entry);
        entry.valid = true;
        const resolve = (name, className) => {
          const found = idMap.get(name) || [];
          const endId = found[0]?.getAttribute('data-margin-end');
          const ends = endId ? idMap.get(endId) || [] : null;
          if (found.length !== 1 || !found[0].classList.contains(className) || el.contains(found[0]) ||
              (ends && (ends.length !== 1 || !ends[0].classList.contains('margin-scope-end')))) {
            entry.valid = false;
            this.warn(`Invalid or unresolved ${className} ID: ${name}. Keeping source flow.`, el);
            return null;
          }
          return found[0];
        };
        entry.targets = markers ? markers.map(node => ({ node: node.closest('.prose-block') || node.closest('p') || node, point: false })) : [
          ...ids(el.getAttribute('data-margin-for') || el.getAttribute('margin-for')).map(id => ({ node: resolve(id, 'margin-scope'), point: false })),
          ...ids(el.getAttribute('data-margin-at') || el.getAttribute('margin-at')).map(id => ({ node: resolve(id, 'margin-anchor'), point: true })),
        ];
        if (el.id && idMap.get(el.id)?.length > 1) {
          entry.valid = false; this.warn(`Duplicate item ID: ${el.id}. Keeping source flow.`, el);
        }
        if (!entry.targets.length) entry.targets.push({ node: entry.source, point: true });
      }
      const liveIds = new Set([...this.entries.keys()].map(el => el.id).filter(Boolean));
      for (const id of this.pins) if (!liveIds.has(id)) this.pins.delete(id);
      this.scanDirty = false;
    }
    pinState(entry) {
      if (!entry.button) return;
      const label = entry.pinned ? 'Unpin' : 'Pin';
      entry.button.setAttribute('aria-label', label);
      entry.button.setAttribute('title', label);
      entry.button.setAttribute('aria-pressed', String(!!entry.pinned));
    }
    status(entry) {
      const hosts = entry.el.querySelectorAll('marimo-output[data-state], marimo-cell[data-state]');
      if (!hosts.length) return;
      const states = [...hosts].map(host => host.dataset.state);
      const state = states.includes('error') ? 'stale' :
        states.some(state => ['loading', 'connecting', 'stale'].includes(state)) ? 'updating' : 'ready';
      if (state === 'ready') entry.hasResult = true;
      if (state === 'updating' && entry.runtimeState !== 'updating') {
        entry.updateHeld = !!entry.hasResult && entry.shown && entry.y !== null;
      } else if (state !== 'updating') entry.updateHeld = false;
      entry.runtimeState = state;
      const text = state === 'updating' ? 'Updating…' : state === 'stale' ?
        (entry.hasResult ? 'Previous result — update failed' : 'Update failed') : '';
      if (entry.status.textContent !== text) entry.status.textContent = text;
      entry.el.setAttribute('aria-busy', String(state === 'updating'));
    }
    restore(entry) {
      entry.el.classList.remove('margin-layout-managed');
      if (entry.original === null) entry.el.removeAttribute('style'); else entry.el.setAttribute('style', entry.original);
      entry.el.inert = entry.originalInert;
      if (entry.originalHidden === null) entry.el.removeAttribute('aria-hidden');
      else entry.el.setAttribute('aria-hidden', entry.originalHidden);
      entry.swapAnimation?.cancel(); entry.swapAnimation = null;
      entry.y = null;
    }
    measure() {
      if (this.scanDirty) this.scan();
      this.metrics.measurements++;
      const content = this.main.getBoundingClientRect();
      const container = document.getElementById('quarto-content')?.getBoundingClientRect();
      const available = (container?.right || innerWidth - 24) - content.left;
      const rightTOC = document.querySelector('#quarto-margin-sidebar #TOC');
      const competingNavigation = !document.body.classList.contains('reader-comparing') && rightTOC && document.querySelector('#quarto-sidebar, #report-chapter-sidebar');
      const rightMargin = getComputedStyle(this.main).getPropertyValue('--report-right-margin').trim();
      const wide = !this.printing && !competingNavigation &&
        (rightMargin ? rightMargin === '1' : innerWidth >= 1100 && available >= 760);
      document.body.classList.toggle('margin-layout-wide', wide);
      if (wide !== this.wide) {
        this.wide = wide;
        for (const entry of this.entries.values()) this.restore(entry);
        // The grid change has to settle before measuring the new body width.
      }
      const body = this.probe.getBoundingClientRect();
      const right = this.rightProbe.getBoundingClientRect();
      this.left = wide ? right.left : body.right;
      this.width = rightMargin ? right.width :
        Math.max(240, Math.min(body.width / 2, innerWidth - this.left - 24));
      this.top = Math.max(16, (this.header?.getBoundingClientRect().bottom || 0) + 12);
      this.height = Math.max(120, innerHeight - this.top - 16);
      Object.assign(this.rail.style, { left: `${this.left}px`, top: `${this.top}px`, width: `${this.width}px`, height: `${this.height}px` });
      for (const entry of this.entries.values()) {
        this.status(entry);
        if (!wide || !entry.valid) { this.restore(entry); continue; }
        entry.el.classList.add('margin-layout-managed');
        Object.assign(entry.el.style, { left: `${this.left}px`, width: `${this.width}px`, maxHeight: `${this.height}px` });
      }
      // Batched after width/style changes. No reads in the scroll path.
      const scroll = window.scrollY;
      for (const entry of this.entries.values()) {
        if (!wide || !entry.valid) continue;
        entry.height = Math.min(entry.el.scrollHeight, this.height);
        entry.ranges = entry.targets.map(({ node, point }) => {
          const rect = node.getBoundingClientRect();
          const endId = node.getAttribute('data-margin-end');
          const endNode = endId ? document.getElementById(endId) : null;
          const end = endNode ? endNode.getBoundingClientRect().top : rect.bottom;
          return { start: rect.top + scroll, end: point ? rect.top + scroll : end + scroll, point };
        });
        // Union semantics do not depend on the order of ID declarations.
        entry.intervals = [];
        for (const range of [...entry.ranges].sort((a, b) => a.start - b.start)) {
          const last = entry.intervals.at(-1);
          if (last && last.end >= range.start) {
            last.end = Math.max(last.end, range.end); last.point = last.point && range.point;
          } else entry.intervals.push({ ...range });
        }
      }
      this.dirty = false;
    }
    navigate(event) {
      if (!this.wide || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const link = event.target.closest('a[href]');
      const href = link?.getAttribute('href');
      if (!href?.startsWith('#')) return;
      let target;
      try { target = document.getElementById(decodeURIComponent(href.slice(1))); } catch { return; }
      const entry = [...this.entries.values()].find(e => e.valid && e.el.contains(target));
      if (!entry) return;
      event.preventDefault();
      if (entry.shown) {
        this.rail.scrollTop = Math.max(0, entry.stackY);
        history.replaceState(null, '', href);
        this.schedule();
        return;
      }
      // Cross-reference navigation follows the author target's source scope.
      const anchor = entry.targets[0]?.node || entry.source;
      anchor.scrollIntoView({ block: 'start', behavior: 'instant' });
      history.replaceState(null, '', href);
      this.schedule();
    }
    focus(event) {
      const entry = [...this.entries.values()].find(e => e.el.contains(event.target));
      if (entry && this.wide && entry.stackY !== undefined) {
        const top = entry.stackY - this.rail.scrollTop;
        if (top < 0 || top + entry.height > this.height) this.rail.scrollTop = entry.stackY;
      }
      this.schedule();
    }
    render() {
      this.metrics.frames++;
      if (!this.wide) return;
      const scroll = window.scrollY + this.top;
      const active = [];
      for (const entry of this.entries.values()) {
        if (!entry.valid) continue;
        const held = entry.el.contains(document.activeElement) || this.pointer === entry || entry.updateHeld;
        if (held && !entry.held) entry.lockY = entry.y ?? 0;
        const ranges = entry.intervals.map(range => ({ ...range,
          y: range.point ? range.start - scroll : Math.min(Math.max(range.start - scroll, 0), range.end - scroll - entry.height) }));
        // Each declared scope is independent; a gap never becomes a new scope.
        const range = ranges.find(r => r.y < this.height && r.y + entry.height > 0)
          || ranges.reduce((a, b) => Math.abs(a.y) < Math.abs(b.y) ? a : b);
        entry.natural = range?.y ?? 0;
        entry.end = range?.end ?? 0;
        entry.held = held;
        entry.shown = entry.pinned || held || (range && range.y < this.height && range.y + entry.height > 0);
        if (entry.shown) active.push(entry);
      }
      active.sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned)
        || a.natural - b.natural || a.end - b.end);
      let bottom = -Infinity;
      const held = active.filter(entry => entry.held);
      for (const entry of held) entry.stackY = entry.lockY + this.rail.scrollTop;
      for (const entry of active) {
        if (entry.held) continue;
        let y = entry.pinned ? Math.max(0, bottom) : Math.max(bottom, entry.natural);
        for (const obstacle of held) {
          if (y < obstacle.stackY + obstacle.height + 12 && y + entry.height + 12 > obstacle.stackY) {
            y = obstacle.stackY + obstacle.height + 12;
          }
        }
        entry.stackY = y;
        bottom = y + entry.height + 12;
      }
      bottom = Math.max(bottom, ...held.map(entry => entry.stackY + entry.height + 12));
      const total = Math.max(this.height, bottom);
      if (this.spacer.style.height !== `${total}px`) this.spacer.style.height = `${total}px`;
      const railScroll = Math.min(this.rail.scrollTop, total - this.height);
      const order = active.map(e => e.el);
      const continuous = this.lastScroll !== undefined && Math.abs(scroll - this.lastScroll) < this.height / 2;
      const swapped = continuous && this.order?.length === order.length && this.order.some((el, i) => el !== order[i]);
      for (const entry of this.entries.values()) {
        if (!entry.valid) continue;
        const y = entry.stackY - railScroll;
        const visible = entry.shown && y < this.height && y + entry.height > 0;
        entry.el.inert = !visible || entry.originalInert;
        if (visible) {
          if (entry.originalHidden === null) entry.el.removeAttribute('aria-hidden');
          else entry.el.setAttribute('aria-hidden', entry.originalHidden);
        } else entry.el.setAttribute('aria-hidden', 'true');
        entry.el.style.visibility = visible ? '' : 'hidden';
        if (visible) {
          entry.el.style.clipPath = `inset(${Math.max(0, -y)}px 0 ${Math.max(0, y + entry.height - this.height)}px 0)`;
          entry.el.style.transform = `translateY(${this.top + y}px)`;
          if (swapped && !entry.held && entry.y !== null && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
            entry.swapAnimation?.cancel();
            const offset = Math.max(0, entry.y) - Math.max(0, y);
            entry.swapAnimation = entry.el.animate([{ translate: `0 ${offset}px` }, { translate: '0 0' }], { duration: 160, easing: 'ease-out' });
          }
          entry.y = y;
        }
      }
      this.order = order; this.lastScroll = scroll;
    }
    destroy() {
      this.abort?.abort(); this.resize?.disconnect(); this.mutation?.disconnect(); this.documentObserver?.disconnect();
      cancelAnimationFrame(this.frame);
      for (const entry of this.entries?.values() || []) {
        this.restore(entry); entry.toolbar.remove(); entry.source.remove();
        if (entry.legacyMargin) entry.el.classList.add('column-margin');
        if (entry.host) { entry.host.classList.add('column-margin', 'column-container'); entry.host.classList.remove('margin-layout-adapter-host'); }
      }
      this.rail?.remove(); this.probe?.remove(); this.rightProbe?.remove();
      document.body.classList.remove('margin-layout-wide');
    }
  }
  window.mechanicsMarginLifecycle?.abort();
  const lifecycle = new AbortController();
  window.mechanicsMarginLifecycle = lifecycle;
  const start = () => {
    const pins = window.mechanicsMarginLayout?.pins || new Set();
    window.mechanicsMarginLayout?.destroy();
    if (!document.querySelector('main.content, main')) return;
    window.mechanicsMarginLayout = new MarginLayout(document, pins);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true, signal: lifecycle.signal });
  else start();
  // Quarto's own margin notes are finalized at load. Reconcile afterwards.
  window.addEventListener('load', () => {
    const layout = window.mechanicsMarginLayout;
    if (layout) { layout.scanDirty = true; layout.invalidate(); }
  }, { once: true, signal: lifecycle.signal });
  window.addEventListener('pageshow', event => { if (event.persisted) start(); }, { signal: lifecycle.signal });
})();

