/*
 * Lesson editor views (React via htm, no JSX): the names -> objects memory diagram, the
 * step-through stepper, the range explorable, and the student-side players for every block
 * type. lesson.html calls window.LessonViz(React, html) once React has loaded.
 * Colors come only from theme tokens; SVG uses style objects so var(--…) resolves.
 */
window.LessonViz = function (React, html) {
  const { useState, useEffect, useMemo, useId, useRef } = React;
  // "loss_curves" explorable: drawn by the framework-free assets/lesson-curves.js.
  function LossCurvesView({ b }) {
    const ref = useRef(null);
    useEffect(() => { if (ref.current && window.LossCurves) window.LossCurves.mount(ref.current, b); }, [b]);
    return html`<div ref=${ref}></div>`;
  }
  const C = window.LessonCore;
  const MONO = { fontFamily: '"IBM Plex Mono", ui-monospace, monospace', fontSize: "12px" };
  const SANS = { fontFamily: '"IBM Plex Sans", system-ui, sans-serif', fontSize: "11px" };
  const CH = 7.25; // px per mono char at 12px

  // ---- Memory diagram ------------------------------------------------------------------------
  function MemoryDiagram({ names = {}, heap = {}, prev = null }) {
    const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
    const ns = Object.entries(names);
    if (!ns.length) return html`<div class="mem-empty">No names yet: nothing has been assigned.</div>`;
    const ROW = 28, GAP = 10, TOP = 24;
    const nameW = Math.max(36, ...ns.map(([n]) => n.length * CH));
    const boxX = nameW + 10;
    const valW = (v) => Math.max(30, String(v).length * CH + 14);
    const colW = Math.max(30, ...ns.map(([, v]) => (v.ref ? 30 : valW(v.value))));
    const objX = boxX + colW + 76;
    const changedName = (n, v) => prev && JSON.stringify(prev.names?.[n]) !== JSON.stringify(v);
    const order = [];
    ns.forEach(([, v]) => { if (v.ref && heap[v.ref] && !order.includes(v.ref)) order.push(v.ref); });
    let y = TOP;
    const objs = order.map((id) => {
      const o = heap[id], sp = C.splitRepr(o.value);
      const cells = sp && sp.items.length <= 10 ? sp.items : [o.value.length > 44 ? o.value.slice(0, 42) + "…" : o.value];
      const ws = cells.map((c) => Math.max(26, c.length * CH + 12));
      const r = { id, o, cells, ws, indexed: !!sp && ["list", "tuple"].includes(o.type) && sp.items.length <= 10, y, w: Math.max(30, ws.reduce((a, b) => a + b, 0)),
        changed: prev && prev.heap?.[id]?.value !== o.value };
      y += 62;
      return r;
    });
    const rowY = (k) => TOP + 14 + k * (ROW + GAP);
    const W = Math.max(objX + Math.max(0, ...objs.map((o) => o.w)) + 8, boxX + colW + 8);
    const H = Math.max(rowY(ns.length) , y) + 4;
    const at = Object.fromEntries(objs.map((o) => [o.id, o]));
    return html`<svg class="mem-svg" viewBox=${`0 0 ${W} ${H}`} width=${W} height=${H} style=${{ maxWidth: "100%", height: "auto" }} role="img"
        aria-label=${ns.map(([n, v]) => `${n} ${v.ref ? `points at ${heap[v.ref]?.type} ${v.ref}` : `= ${v.value}`}`).join("; ")}>
      <defs><marker id=${`ah${uid}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" style=${{ fill: "var(--primary)" }} /></marker></defs>
      <text x="0" y="12" style=${{ ...SANS, fill: "var(--muted-foreground)" }}>Names</text>
      ${objs.length > 0 && html`<text x=${objX} y="12" style=${{ ...SANS, fill: "var(--muted-foreground)" }}>Objects</text>`}
      ${ns.map(([n, v], k) => {
        const ry = rowY(k), ch = changedName(n, v);
        return html`<g key=${n}>
          <text x=${nameW} y=${ry + 18} textAnchor="end" style=${{ ...MONO, fill: "var(--foreground)", fontWeight: ch ? 600 : 400 }}>${n}</text>
          <rect x=${boxX} y=${ry} width=${v.ref ? 30 : valW(v.value)} height=${ROW} rx="5"
            style=${{ fill: "var(--card)", stroke: ch ? "var(--accent-solid)" : "var(--border)", strokeWidth: ch ? 2 : 1 }} />
          ${v.ref ? html`<circle cx=${boxX + 15} cy=${ry + ROW / 2} r="3.5" style=${{ fill: "var(--primary)" }} />`
            : html`<text x=${boxX + 7} y=${ry + 18} style=${{ ...MONO, fill: "var(--foreground)" }}>${v.value}</text>`}
        </g>`;
      })}
      ${ns.filter(([, v]) => v.ref && at[v.ref]).map(([n, v]) => {
        const k = ns.findIndex(([m]) => m === n), x1 = boxX + 15, y1 = rowY(k) + ROW / 2, o = at[v.ref], x2 = objX - 3, y2 = o.y + 16 + 13;
        return html`<path key=${`a${n}`} d=${`M${x1},${y1} C${x1 + 50},${y1} ${x2 - 50},${y2} ${x2},${y2}`} markerEnd=${`url(#ah${uid})`}
          style=${{ fill: "none", stroke: "var(--primary)", strokeWidth: 1.5 }} />`;
      })}
      ${objs.map((o) => {
        let cx = objX;
        return html`<g key=${o.id}>
          <text x=${objX} y=${o.y + 11} style=${{ ...SANS, fill: o.changed ? "var(--accent-text)" : "var(--muted-foreground)" }}>${o.o.type}${o.changed ? " · changed" : ""}</text>
          ${o.cells.length === 0 || (o.cells.length === 1 && o.cells[0] === "") ? html`<rect x=${objX} y=${o.y + 16} width="30" height="26" rx="4" style=${{ fill: "var(--muted)", stroke: "var(--border)" }} />`
            : o.cells.map((c, j) => {
              const x = cx; cx += o.ws[j];
              return html`<g key=${j}>
                <rect x=${x} y=${o.y + 16} width=${o.ws[j]} height="26" style=${{ fill: "var(--muted)", stroke: o.changed ? "var(--accent-solid)" : "var(--border)", strokeWidth: o.changed ? 1.5 : 1 }} />
                <text x=${x + 6} y=${o.y + 33} style=${{ ...MONO, fill: "var(--foreground)" }}>${c}</text>
                ${o.indexed && html`<text x=${x + 3} y=${o.y + 53} style=${{ ...SANS, fontSize: "10px", fill: "var(--muted-foreground)" }}>${j}</text>`}
              </g>`;
            })}
        </g>`;
      })}
    </svg>`;
  }

  // ---- Code listing with the current line marked ---------------------------------------------
  function CodeView({ code, line }) {
    const lines = String(code || "").split("\n");
    return html`<div class="codearea is-ro">
      <div class="codearea-gutter">${lines.map((_, k) => html`<div key=${k} class=${line === k + 1 ? "cur" : ""}>${k + 1}</div>`)}</div>
      <div class="codearea-main">
        ${line ? html`<div class="codearea-hl" style=${{ top: `${8 + (line - 1) * 20}px` }}></div>` : null}
        <pre class="codearea-pre">${code}</pre>
      </div>
    </div>`;
  }

  // ---- Step-through ----------------------------------------------------------------------------
  const valueText = (v, heap) => (v.ref ? `${heap[v.ref]?.type || "object"} ${heap[v.ref]?.value ?? ""}` : v.value);
  function Stepper({ steps, code, k: kIn, setK: setKIn, renderCode, compact }) {
    const [kLocal, setKLocal] = useState(0);
    const k = kIn ?? kLocal, setK = setKIn || setKLocal;
    const n = steps.length, s = steps[Math.min(k, n - 1)], prev = k > 0 ? steps[k - 1] : null;
    if (!n) return null;
    const hasHeap = Object.keys(s.heap || {}).length > 0 || steps.some((x) => Object.keys(x.heap || {}).length);
    const ran = prev ? prev.line : null;
    return html`<div class=${`stepper ${compact ? "is-compact" : ""}`}>
      <div class="stepper-top">
        <div class="min-w-0">${renderCode ? renderCode(s.line) : html`<${CodeView} code=${code} line=${s.line} />`}</div>
        <div class="stepper-side">
          <div class="stepper-label">Variables</div>
          ${Object.keys(s.names).length === 0 ? html`<div class="text-xs text-muted-foreground">None yet.</div>`
            : html`<table class="vars"><tbody>${Object.entries(s.names).map(([nm, v]) => {
              const ch = !prev || JSON.stringify(prev.names[nm]) !== JSON.stringify(v) || (v.ref && prev.heap[v.ref]?.value !== s.heap[v.ref]?.value);
              return html`<tr key=${nm} class=${ch && k > 0 ? "changed" : ""}><td class="font-mono">${nm}</td><td class="font-mono">${valueText(v, s.heap)}</td></tr>`;
            })}</tbody></table>`}
          <div class="stepper-label mt-2">Output so far</div>
          <div class="out stepper-out">${s.out ? s.out.replace(/\n$/, "") : html`<span class="text-muted-foreground">Nothing printed yet.</span>`}</div>
        </div>
      </div>
      <div class="stepper-ctrl">
        <button type="button" class="btn" data-size="sm" data-variant="outline" disabled=${k === 0} onMouseDown=${(e) => e.preventDefault()} onClick=${() => setK(Math.max(0, k - 1))}>Prev</button>
        <button type="button" class="btn" data-size="sm" data-variant=${k === n - 1 ? "outline" : "secondary"} disabled=${k === n - 1} onMouseDown=${(e) => e.preventDefault()} onClick=${() => setK(Math.min(n - 1, k + 1))}>Next</button>
        <input type="range" class="stepper-scrub" min="0" max=${n - 1} value=${k} aria-label="Step" onInput=${(e) => setK(Number(e.target.value))} onChange=${(e) => setK(Number(e.target.value))} />
        <span class="text-xs text-muted-foreground whitespace-nowrap">${`Step ${k + 1} of ${n}`} · ${s.line === null ? "finished" : ran ? `ran line ${ran}, line ${s.line} next` : `line ${s.line} runs next`}</span>
      </div>
      ${hasHeap && Object.keys(s.names).length > 0 && html`<div class="stepper-mem"><${MemoryDiagram} names=${s.names} heap=${s.heap} prev=${prev} /></div>`}
    </div>`;
  }

  // ---- Range explorable ------------------------------------------------------------------------
  function NumberLine({ start, stop, step }) {
    const vals = C.rangeValues(start, stop, step) || [];
    let lo = Math.min(start, stop, ...vals) - 1, hi = Math.max(start, stop, ...vals) + 1;
    if (hi - lo < 10) { const pad = (10 - (hi - lo)) / 2; lo = Math.floor(lo - pad); hi = Math.ceil(hi + pad); }
    const W = 380, P = 16, AX = 60, x = (v) => P + ((v - lo) / (hi - lo)) * (W - 2 * P);
    const every = hi - lo > 24 ? 5 : hi - lo > 14 ? 2 : 1;
    const ticks = []; for (let v = lo; v <= hi; v++) ticks.push(v);
    return html`<svg viewBox=${`0 0 ${W} 92`} width="100%" style=${{ maxWidth: `${W}px`, height: "auto", display: "block" }} role="img"
        aria-label=${`range(${start}, ${stop}, ${step}) gives ${vals.join(", ") || "nothing"}`}>
      <line x1=${P} x2=${W - P} y1=${AX} y2=${AX} style=${{ stroke: "var(--border)", strokeWidth: 1.5 }} />
      ${ticks.map((v) => html`<g key=${v}><line x1=${x(v)} x2=${x(v)} y1=${AX - 4} y2=${AX + 4} style=${{ stroke: "var(--border)" }} />
        ${v % every === 0 && html`<text x=${x(v)} y=${AX + 20} textAnchor="middle" style=${{ ...MONO, fontSize: "11px", fill: "var(--muted-foreground)" }}>${v}</text>`}</g>`)}
      ${vals.slice(1).map((v, j) => { const a = x(vals[j]), b = x(v); return html`<path key=${`h${j}`} d=${`M${a},${AX - 8} Q${(a + b) / 2},${AX - 30} ${b},${AX - 8}`} style=${{ fill: "none", stroke: "var(--primary)", strokeWidth: 1.2, strokeDasharray: "3 3" }} />`; })}
      <line x1=${x(stop)} x2=${x(stop)} y1=${AX - 34} y2=${AX + 8} style=${{ stroke: "var(--critical-solid)", strokeWidth: 3 }} />
      <text x=${x(stop)} y=${AX - 40} textAnchor="middle" style=${{ ...SANS, fill: "var(--critical-solid)", fontWeight: 600 }}>stop ${stop}</text>
      ${vals.map((v, j) => html`<circle key=${`d${j}`} cx=${x(v)} cy=${AX} r="6" style=${{ fill: "var(--primary)", stroke: "var(--card)", strokeWidth: 2 }} />`)}
      ${vals.length > 0 && vals[0] !== stop && html`<text x=${x(vals[0])} y=${AX + 36} textAnchor="middle" style=${{ ...SANS, fill: "var(--muted-foreground)" }}>start</text>`}
    </svg>`;
  }
  function RangeExplore({ start, stop, step, caption, onChange }) {
    const [st, setSt] = useState({ start, stop, step });
    useEffect(() => setSt({ start, stop, step }), [start, stop, step]);
    const set = (k, v) => { const n = { ...st, [k]: Number(v) }; setSt(n); onChange && onChange(n); };
    const vals = C.rangeValues(st.start, st.stop, st.step);
    const slider = (k, min, max) => html`<label class="explore-row"><span class="font-mono text-xs w-10">${k}</span>
      <input type="range" min=${min} max=${max} value=${st[k]} onInput=${(e) => set(k, e.target.value)} onChange=${(e) => set(k, e.target.value)} />
      <span class="font-mono text-sm w-7 text-right">${st[k]}</span></label>`;
    return html`<div class="grid gap-2">
      ${caption && html`<div class="text-sm">${caption}</div>`}
      <div class="grid gap-1">${slider("start", -5, 15)}${slider("stop", -5, 20)}${slider("step", -5, 5)}</div>
      ${vals ? html`<${NumberLine} start=${st.start} stop=${st.stop} step=${st.step} />` : null}
      <div class="font-mono text-sm">list(range(${st.start}, ${st.stop}, ${st.step})) <span class="text-muted-foreground">→</span> ${vals ? `[${vals.join(", ")}]` : html`<span style=${{ color: "var(--critical-solid)" }}>ValueError: step can't be 0</span>`}</div>
    </div>`;
  }

  // ---- Players ---------------------------------------------------------------------------------
  const qText = (q) => String(q || "").split("\n\n")[0].replace(/`/g, "");
  const qCode = (q) => (String(q || "").includes("\n\n") ? String(q).split("\n\n").slice(1).join("\n\n") : "");

  function PredictPlayer({ b }) {
    const [g, setG] = useState(""); const [shown, setShown] = useState(false);
    const ok = g.trim() === (b.answer || "").trim();
    return html`<div class="grid gap-2 rounded-lg border p-3">
      <div class="text-sm font-medium">${b.question}</div><div class="code">${b.code}</div>
      <input class="input font-mono" placeholder="Your guess" value=${g} onInput=${(e) => setG(e.target.value)} />
      <button type="button" class="btn" data-size="sm" onClick=${() => setShown(true)}>Check my guess</button>
      ${shown && html`<div class="text-sm"><span class=${`pill ${ok ? "tone-ok" : "tone-warn"}`}>${ok ? "Right" : "Not quite"}</span> It prints <span class="font-mono">${b.answer}</span></div>`}
    </div>`;
  }
  function CheckPlayer({ b }) {
    const [sel, setSel] = useState(null);
    return html`<div class="grid gap-1.5 rounded-lg border p-3"><div class="text-sm font-medium">Quick check</div>
      <div class="text-sm">${qText(b.question)}</div>
      ${qCode(b.question) && html`<div class="code">${qCode(b.question)}</div>`}
      ${b.options.map((o, k) => html`<button type="button" key=${k} class="text-left text-sm rounded-md border px-3 py-1.5 font-mono" style=${sel === k ? { borderColor: k === b.answer ? "var(--ok-solid)" : "var(--critical-solid)" } : {}} onClick=${() => setSel(k)}>${o}</button>`)}
      ${sel !== null && html`<div class="text-xs">${sel === b.answer ? "Correct." : `Not quite: it's ${b.options[b.answer]}.`}</div>`}</div>`;
  }
  function Extra({ show, lesson }) {
    const mem = lesson.find((x) => x.type === "memory"), tr = lesson.find((x) => x.type === "trace" && (x.steps || []).length), ex = lesson.find((x) => x.type === "explore");
    if (show === "memory" && (mem || tr)) return html`<div class="mt-1"><${MemoryDiagram} names=${mem ? mem.names : tr.steps[tr.steps.length - 1].names} heap=${mem ? mem.heap : tr.steps[tr.steps.length - 1].heap} /></div>`;
    if (show === "explore" && ex) return html`<div class="mt-1">${ex.kind === "loss_curves" ? html`<${LossCurvesView} b=${ex} />` : html`<${RangeExplore} start=${ex.start} stop=${ex.stop} step=${ex.step} />`}</div>`;
    if (show === "trace" && tr) return html`<div class="mt-1"><${Stepper} steps=${tr.steps} code=${tr.code} compact=${true} /></div>`;
    return null;
  }
  function BranchPlayer({ b, lesson = [] }) {
    const [sel, setSel] = useState(null);
    const rem = sel !== null && sel !== b.answer ? (b.remediation || {})[String(sel)] : null;
    return html`<div class="grid gap-1.5 rounded-lg border p-3">
      <div class="text-sm font-medium">${qText(b.question)}</div>
      ${qCode(b.question) && html`<div class="code">${qCode(b.question)}</div>`}
      ${(b.options || []).map((o, k) => html`<button type="button" key=${k} disabled=${sel !== null} class="text-left text-sm rounded-md border px-3 py-1.5 font-mono"
        style=${sel === k ? { borderColor: k === b.answer ? "var(--ok-solid)" : "var(--critical-solid)", borderWidth: "2px" } : {}} onClick=${() => setSel(k)}>${o}</button>`)}
      ${sel === b.answer && html`<div class="text-sm"><span class="pill tone-ok">Right</span></div>`}
      ${sel !== null && sel !== b.answer && html`<div class="remed">
        <div class="text-sm">${rem?.text || `Not quite: it's ${b.options[b.answer]}.`}</div>
        ${rem?.show && html`<${Extra} show=${rem.show} lesson=${lesson} />`}
        <button type="button" class="btn mt-1" data-size="sm" data-variant="outline" onClick=${() => setSel(null)}>Try again</button>
      </div>`}
    </div>`;
  }
  const norm = (s) => String(s || "").replace(/\s+/g, "");
  function FillPlayer({ b }) {
    const [g, setG] = useState(""); const [res, setRes] = useState(null);
    const parts = String(b.code || "").split("____");
    const ok = (b.answers || []).some((a) => norm(a) === norm(g));
    return html`<div class="grid gap-2 rounded-lg border p-3">
      <div class="text-sm font-medium">Fill in the blank</div>
      <div class="code fill-code">${parts.map((p, k) => html`<span key=${k}>${p}${k < parts.length - 1 && html`<input class="fill-input" size=${Math.max(6, g.length + 1)} value=${g} aria-label="Blank"
        onInput=${(e) => { setG(e.target.value); setRes(null); }} />`}</span>`)}</div>
      <button type="button" class="btn" data-size="sm" onClick=${() => setRes(ok ? "ok" : "no")}>Check</button>
      ${res === "ok" && html`<div class="text-sm"><span class="pill tone-ok">Right</span> ${(b.answers || []).length > 1 ? `Also accepted: ${b.answers.filter((a) => norm(a) !== norm(g)).join(", ")}` : ""}</div>`}
      ${res === "no" && html`<div class="text-sm"><span class="pill tone-warn">Not yet</span> ${b.hint || "Try again."}</div>`}
    </div>`;
  }
  const shuffle = (arr) => { // deterministic, so the preview matches what students see
    const a = arr.slice(); let s = arr.join("|").length || 7;
    for (let i = a.length - 1; i > 0; i--) { s = (s * 9301 + 49297) % 233280; const j = Math.floor((s / 233280) * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
    return a;
  };
  function ParsonsPlayer({ b }) {
    const all = useMemo(() => shuffle([...(b.lines || []).map((t, k) => ({ id: `l${k}`, t })), ...(b.distractors || []).map((t, k) => ({ id: `d${k}`, t }))]), [JSON.stringify([b.lines, b.distractors])]);
    const [picked, setPicked] = useState([]); const [res, setRes] = useState(null);
    useEffect(() => { setPicked([]); setRes(null); }, [all]);
    const pool = all.filter((x) => !picked.includes(x.id)), byId = Object.fromEntries(all.map((x) => [x.id, x]));
    const check = () => {
      const got = picked.map((id) => byId[id].t);
      if (picked.some((id) => id[0] === "d")) return setRes("One of your lines doesn't belong in the program.");
      if (got.length < (b.lines || []).length) return setRes(`Use all ${(b.lines || []).length} lines that belong.`);
      const bad = got.findIndex((t, k) => t !== b.lines[k]);
      setRes(bad < 0 ? "ok" : `Line ${bad + 1} isn't in the right place yet.`);
    };
    const line = (x, onClick) => html`<button type="button" key=${x.id} class="parsons-line" onClick=${onClick}>${x.t}</button>`;
    return html`<div class="grid gap-2 rounded-lg border p-3">
      <div class="text-sm font-medium">${b.prompt}</div>
      ${b.output && html`<div class="text-xs text-muted-foreground">It should print <span class="font-mono text-foreground">${b.output}</span></div>`}
      <div class="parsons-zone">${picked.length ? picked.map((id) => line(byId[id], () => { setPicked(picked.filter((p) => p !== id)); setRes(null); }))
        : html`<div class="text-xs text-muted-foreground p-1">Tap lines below to build the program.</div>`}</div>
      <div class="grid gap-1">${pool.map((x) => line(x, () => { setPicked([...picked, x.id]); setRes(null); }))}</div>
      <div class="flex gap-2"><button type="button" class="btn" data-size="sm" onClick=${check}>Check</button>
        ${picked.length > 0 && html`<button type="button" class="btn" data-size="sm" data-variant="ghost" onClick=${() => { setPicked([]); setRes(null); }}>Start over</button>`}</div>
      ${res && html`<div class="text-sm">${res === "ok" ? html`<span class="pill tone-ok">Right</span> It prints <span class="font-mono">${b.output}</span>` : html`<span class="pill tone-warn">Not yet</span> ${res}`}</div>`}
    </div>`;
  }
  function RecapView({ b }) {
    return html`<div class="recap"><div class="text-sm font-medium mb-1">Recap</div>
      <ul class="grid gap-1">${(b.points || []).filter(Boolean).map((p, k) => html`<li key=${k} class="text-sm">${p}</li>`)}</ul></div>`;
  }

  function PreviewBlock({ b, lesson }) {
    const t = C.textOf(b);
    switch (b.type) {
      case "h2": return html`<h2 class="text-lg font-semibold">${t}</h2>`;
      case "explain": return t ? html`<p class="text-sm leading-6">${t}</p>` : null;
      case "mistake": return html`<div class="mistake text-sm leading-6"><b>Common mistake. </b>${t}</div>`;
      case "example": return html`<div class="grid gap-1"><div class="code">${b.code}</div><div class="out">${b.output}</div></div>`;
      case "predict": return html`<${PredictPlayer} b=${b} />`;
      case "check": return html`<${CheckPlayer} b=${b} />`;
      case "trace": return (b.steps || []).length ? html`<div class="grid gap-2">${b.caption && html`<div class="text-sm">${b.caption}</div>`}<${Stepper} steps=${b.steps} code=${b.code} compact=${true} /></div>`
        : html`<div class="text-xs text-muted-foreground rounded-md border p-3">Step-through not recorded yet.</div>`;
      case "memory": return html`<div class="grid gap-2">${b.caption && html`<div class="text-sm">${b.caption}</div>`}<div class="rounded-lg border p-3"><${MemoryDiagram} names=${b.names} heap=${b.heap} /></div></div>`;
      case "branch": return html`<${BranchPlayer} b=${b} lesson=${lesson} />`;
      case "fill": return html`<${FillPlayer} b=${b} />`;
      case "parsons": return html`<${ParsonsPlayer} b=${b} />`;
      case "explore": return b.kind === "loss_curves" ? html`<div class="rounded-lg border p-3"><${LossCurvesView} b=${b} /></div>`
        : html`<div class="rounded-lg border p-3"><${RangeExplore} start=${b.start} stop=${b.stop} step=${b.step} caption=${b.caption} /></div>`;
      case "recap": return html`<${RecapView} b=${b} />`;
      default: return null;
    }
  }

  return { LossCurvesView, MemoryDiagram, CodeView, Stepper, NumberLine, RangeExplore, PredictPlayer, CheckPlayer, BranchPlayer, FillPlayer, ParsonsPlayer, RecapView, PreviewBlock };
};
