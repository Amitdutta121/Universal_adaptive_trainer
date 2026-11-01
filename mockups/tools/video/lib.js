// Shared recorder helpers: caption bar, title cards, a visible cursor, and slow human-like clicks.
const { chromium } = require('playwright-core');
const base = 'file:///C:/Users/amit/orca/workspaces/FInalAdaptiveTrainer/main-2/mockups/';

const INIT = () => {
  const css = `
  #__cap{position:fixed;left:50%;top:14px;transform:translateX(-50%);max-width:min(92vw,900px);z-index:2147483646;
    background:rgba(17,24,28,.88);color:#fff;font:500 17px/1.4 "IBM Plex Sans",system-ui,sans-serif;padding:10px 18px;border-radius:10px;
    box-shadow:0 6px 24px rgba(0,0,0,.25);transition:opacity .3s;text-align:center}
  #__cap:empty{opacity:0}
  #__cur{position:fixed;left:0;top:0;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;z-index:2147483647;pointer-events:none;
    background:rgba(47,125,87,.35);border:2px solid #2f7d57;transition:transform .7s cubic-bezier(.4,0,.2,1)}
  #__cur.down{background:rgba(47,125,87,.7)}
  #__card{position:fixed;inset:0;z-index:2147483647;background:#11181c;color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;
    font-family:"IBM Plex Sans",system-ui,sans-serif;text-align:center;padding:32px;transition:opacity .5s}
  #__card h1{font:700 40px/1.15 Archivo,system-ui,sans-serif;margin:0 0 14px}
  #__card p{font-size:19px;opacity:.8;margin:0;max-width:760px}`;
  const mount = () => {
    if (document.getElementById('__cap')) return;
    const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    const cap = document.createElement('div'); cap.id = '__cap'; cap.textContent = sessionStorage.getItem('__cap') || ''; document.body.appendChild(cap);
    const cur = document.createElement('div'); cur.id = '__cur'; document.body.appendChild(cur);
    const pos = JSON.parse(sessionStorage.getItem('__pos') || '[200,200]');
    cur.style.transition = 'none'; cur.style.transform = `translate(${pos[0]}px,${pos[1]}px)`; cur.offsetWidth; cur.style.transition = '';
  };
  window.__caption = (t) => { sessionStorage.setItem('__cap', t); mount(); document.getElementById('__cap').textContent = t; };
  window.__move = (x, y) => { sessionStorage.setItem('__pos', JSON.stringify([x, y])); mount(); document.getElementById('__cur').style.transform = `translate(${x}px,${y}px)`; };
  window.__down = (on) => document.getElementById('__cur')?.classList.toggle('down', on);
  window.__card = (h, p) => { mount(); let c = document.getElementById('__card'); if (!c) { c = document.createElement('div'); c.id = '__card'; document.body.appendChild(c); }
    c.innerHTML = `<h1>${h}</h1><p>${p || ''}</p>`; c.style.opacity = 1; };
  window.__uncard = () => { const c = document.getElementById('__card'); if (c) { c.style.opacity = 0; setTimeout(() => c.remove(), 500); } };
  document.addEventListener('DOMContentLoaded', mount);
  // Hide the "Mockup · mock data" banner in recordings.
  document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); s.textContent = '.mock-banner{display:none!important}'; document.head.appendChild(s); });
};

async function start(name, { width, height, scale = 1 }) {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width, height }, deviceScaleFactor: scale,
    recordVideo: { dir: `out/${name}`, size: { width: width * scale, height: height * scale } },
  });
  await context.addInitScript(INIT);
  const page = await context.newPage();
  const wait = (ms) => page.waitForTimeout(ms);
  const api = {
    page, wait,
    async go(url, ms = 1800) { await page.goto(base + url); await wait(ms); },
    async caption(t, ms = 0) { await page.evaluate((t) => window.__caption(t), t); if (ms) await wait(ms); },
    async card(h, p, ms = 3000) { await page.evaluate(([h, p]) => window.__card(h, p), [h, p]); await wait(ms); await page.evaluate(() => window.__uncard()); await wait(600); },
    async point(loc) {
      const l = typeof loc === 'string' ? page.locator(loc).first() : loc;
      await l.scrollIntoViewIfNeeded(); await wait(250);
      const b = await l.boundingBox(); if (!b) throw new Error('no box for ' + loc);
      await page.evaluate(([x, y]) => window.__move(x, y), [b.x + b.width / 2, b.y + b.height / 2]); await wait(800);
      return l;
    },
    async click(loc, after = 1200) {
      const l = await api.point(loc);
      await page.evaluate(() => window.__down(true)); await wait(150);
      await l.click(); await page.evaluate(() => window.__down(false)).catch(() => {});
      await wait(after);
    },
    async type(loc, text, after = 500) { const l = await api.point(loc); await l.click(); await l.fill(''); await page.keyboard.type(text, { delay: 55 }); await wait(after); },
    async scroll(y, ms = 1400) { await page.evaluate((y) => window.scrollBy({ top: y, behavior: 'smooth' }), y); await wait(ms); },
    async scrollTo(loc, ms = 1200) { await page.locator(loc).first().evaluate((e) => e.scrollIntoView({ behavior: 'smooth', block: 'center' })); await wait(ms); },
    async end() { await wait(800); const v = page.video(); await context.close(); await browser.close(); return v.path(); },
  };
  return api;
}
module.exports = { start };
