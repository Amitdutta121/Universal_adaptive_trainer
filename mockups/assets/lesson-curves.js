/*
 * The "loss_curves" explorable (see assets/lesson-finetuning.js), framework-free so both the React
 * editor and the Alpine student player can use it: LossCurves.mount(element, block[, { approach, rate }]).
 * Students pick a starting point and a learning rate; it draws training error (solid) and error on
 * new examples (dashed) per epoch from real runs, and marks the epoch with the lowest validation error.
 */
window.LossCurves = (function () {
  let W = 560, H = 230;
  const L = 40, R = 10, T = 14, B = 34;
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const fmt = (v) => (v < 0.01 ? v.toFixed(4) : v < 1 ? v.toFixed(3) : v.toFixed(2));

  function svg(b, approach, rate) {
    const run = b.runs[`${approach}@${rate}`];
    const ys = [...run.train, ...run.val].filter((v) => v > 0);
    // log scale so 0.003 and 0.5 both read
    const lo = Math.log10(Math.min(...ys, 0.001)), hi = Math.log10(Math.max(...ys, 1.5));
    const n = run.train.length;
    const x = (i) => L + (i / (n - 1)) * (W - L - R);
    const y = (v) => T + (1 - (Math.log10(Math.max(v, 1e-4)) - lo) / (hi - lo)) * (H - T - B);
    const path = (arr) => arr.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
    const ticks = [0.001, 0.01, 0.1, 1].filter((v) => Math.log10(v) >= lo - 0.01 && Math.log10(v) <= hi + 0.01);
    const bi = Math.round(run.best_epoch / b.every);
    const ref = y(b.pretrained_val);
    let g = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Training and validation error by epoch" style="display:block;font:11px 'IBM Plex Sans',system-ui,sans-serif">`;
    ticks.forEach((v) => { g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" style="stroke:var(--border)"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end" style="fill:var(--muted-foreground)">${v}</text>`; });
    [0, 100, 200, 300].forEach((e) => { const xx = x(e / b.every); g += `<text x="${xx}" y="${H - B + 16}" text-anchor="middle" style="fill:var(--muted-foreground)">${e}</text>`; });
    g += `<text x="${(L + W - R) / 2}" y="${H - 4}" text-anchor="middle" style="fill:var(--muted-foreground)">epoch</text>`;
    g += `<line x1="${L}" x2="${W - R}" y1="${ref}" y2="${ref}" style="stroke:var(--muted-foreground);stroke-dasharray:2 4"/><text x="${W - R}" y="${ref - 5}" text-anchor="end" style="fill:var(--muted-foreground)">${W < 420 ? "untuned" : "pretrained model, untuned"}</text>`;
    g += `<path d="${path(run.train)}" style="fill:none;stroke:var(--primary);stroke-width:2"/>`;
    g += `<path d="${path(run.val)}" style="fill:none;stroke:var(--warn-solid);stroke-width:2.5;stroke-dasharray:7 4"/>`;
    g += `<circle cx="${x(bi)}" cy="${y(run.val[bi])}" r="5" style="fill:var(--card);stroke:var(--warn-solid);stroke-width:2.5"/>`;
    const lab = W < 420 ? `best: epoch ${run.best_epoch}` : `lowest new-example error, epoch ${run.best_epoch}`;
    g += `<text x="${Math.min(x(bi) + 8, W - R - lab.length * 6)}" y="${y(run.val[bi]) - 8}" style="fill:var(--foreground);font-weight:600">${lab}</text>`;
    return g + "</svg>";
  }

  function summary(b, approach, rate) {
    const r = b.runs[`${approach}@${rate}`];
    const trainEnd = r.train[r.train.length - 1];
    const rising = r.final_val > r.best_val * 1.15;
    const gap = r.final_val / Math.max(trainEnd, 1e-4);
    let s = `Training error ends at ${fmt(trainEnd)}; error on new examples ends at ${fmt(r.final_val)}`;
    s += rising ? ` after bottoming out at ${fmt(r.best_val)} (epoch ${r.best_epoch}). It's memorising the 12 examples: stop at the low point.` : ".";
    if (gap > 20) s += " The huge gap between the two lines means it learned the 12 points, not the task.";
    return s;
  }

  function mount(el, b, opts = {}) {
    let approach = opts.approach || "finetune", rate = opts.rate || b.rates[b.rates.length - 1];
    const seg = (items, cur, attr) => `<div class="flex flex-wrap gap-1 rounded-lg p-1" style="background:var(--muted)">${items.map(([v, l]) =>
      `<button type="button" data-${attr}="${v}" class="btn" data-size="sm" ${String(v) === String(cur) ? "" : `data-variant="ghost"`}>${esc(l)}</button>`).join("")}</div>`;
    const render = () => {
      W = Math.max(300, Math.min(640, Math.round(el.clientWidth || 560)));
      H = W < 420 ? 210 : 230;
      el.innerHTML = `<div class="grid gap-2">
        ${b.caption && opts.caption !== false ? `<div class="text-sm">${esc(b.caption)}</div>` : ""}
        ${seg(Object.entries(b.approaches), approach, "approach")}
        <div class="flex flex-wrap items-center gap-2"><span class="text-xs text-muted-foreground">Learning rate</span>${seg(b.rates.map((r) => [r, String(r)]), rate, "rate")}</div>
        ${svg(b, approach, rate)}
        <div class="flex flex-wrap gap-x-4 text-xs text-muted-foreground"><span><span style="display:inline-block;width:18px;border-top:2px solid var(--primary);vertical-align:middle"></span> error on the 12 training examples</span><span><span style="display:inline-block;width:18px;border-top:2.5px dashed var(--warn-solid);vertical-align:middle"></span> error on 200 new examples</span></div>
        <p class="text-sm">${esc(summary(b, approach, rate))}</p>
      </div>`;
      el.querySelectorAll("[data-approach]").forEach((x) => x.addEventListener("click", (e) => { e.preventDefault(); approach = x.dataset.approach; render(); }));
      el.querySelectorAll("[data-rate]").forEach((x) => x.addEventListener("click", (e) => { e.preventDefault(); rate = Number(x.dataset.rate); render(); }));
    };
    render();
  }
  return { mount, svg, summary };
})();
