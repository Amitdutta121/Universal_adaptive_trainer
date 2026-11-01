/*
 * Lesson editor core (no React): Python in the browser (Pyodide), the step recorder, answer
 * verification, the block catalog, new-block defaults, the time estimate and the mocked
 * "Ask AI" proposals. Used by lesson.html. Block shapes follow assets/lesson-schema.js.
 *
 * Editor-only fields it may put on a block (ignored by the student player):
 *   stale (code edited since it last ran / was recorded), error, verified { ok, note, outputs }.
 */
(function () {
  const L = (window.LessonCore = {});

  // ---- Pyodide: loaded on first use, one run at a time ------------------------------------
  let pyReady = null, queue = Promise.resolve();
  const loadPy = () => {
    if (!pyReady) pyReady = new Promise((res, rej) => {
      const s = document.createElement("script");
      s.src = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide.js";
      s.onload = () => window.loadPyodide().then(res, rej); s.onerror = rej;
      document.head.appendChild(s);
    });
    return pyReady;
  };
  L.pyLoaded = () => !!pyReady;
  const serial = (fn) => { const p = queue.then(fn, fn); queue = p.catch(() => {}); return p; };

  L.runPython = (code) => serial(async () => {
    const py = await loadPy();
    const out = [];
    py.setStdout({ batched: (t) => out.push(t) });
    try { await py.runPythonAsync(code); }
    catch (e) { out.push(String(e.message || e).trim().split("\n").pop()); return { output: out.join("\n"), error: true }; }
    return { output: out.join("\n"), error: false };
  });

  // Port of tools/trace_lesson.py: sys.settrace on the lesson's code, a snapshot before each
  // line (names -> values or refs to heap objects), then the final state (line = null).
  const TRACER = String.raw`
import sys, io, json, contextlib
def __lesson_trace(code, limit=300):
    steps, out = [], io.StringIO()
    g = {"__name__": "__main__"}
    def snap(loc, line):
        heap, names, ren = {}, {}, {}
        def oid(v):
            k = id(v)
            if k not in ren:
                ren[k] = "o" + str(len(ren) + 1)
                heap[ren[k]] = {"type": type(v).__name__, "value": repr(v)}
            return ren[k]
        for n, v in list(loc.items()):
            if n.startswith("__") or callable(v) or type(v).__name__ == "module":
                continue
            names[n] = {"ref": oid(v)} if isinstance(v, (list, dict, tuple, set)) else {"value": repr(v)}
        steps.append({"line": line, "names": names, "heap": heap, "out": out.getvalue()})
    class Stop(Exception):
        pass
    def tr(frame, event, arg):
        if frame.f_code.co_filename != "<lesson>":
            return None
        if event == "line":
            loc = dict(frame.f_globals)
            if frame.f_code.co_name != "<module>":
                loc.update(frame.f_locals)
            snap(loc, frame.f_lineno)
            if len(steps) > limit:
                raise Stop()
        return tr
    err = None
    with contextlib.redirect_stdout(out):
        sys.settrace(tr)
        try:
            exec(compile(code, "<lesson>", "exec"), g)
        except Stop:
            err = "Stopped after %d steps. Does it loop forever?" % limit
        except Exception as e:
            err = type(e).__name__ + ": " + str(e)
        finally:
            sys.settrace(None)
    snap(g, None)
    return json.dumps({"steps": steps, "error": err})
`;
  L.recordTrace = (code) => serial(async () => {
    const py = await loadPy();
    py.setStdout({ batched: () => {} });
    py.globals.set("__src", code);
    const r = JSON.parse(await py.runPythonAsync(TRACER + "\n__lesson_trace(__src)"));
    L.traceCache[code] = r.steps;
    return r;
  });
  L.traceCache = {}; // code -> steps, so a memory block can pick a snapshot without re-running

  // Fill: every accepted answer must run and print the same thing.
  L.verifyFill = async (b) => {
    const outs = [];
    for (const a of b.answers || []) outs.push(await L.runPython((b.code || "").split("____").join(a)));
    const bad = outs.findIndex((o) => o.error);
    if (!outs.length) return { ok: false, note: "Add at least one accepted answer." };
    if (bad >= 0) return { ok: false, note: `"${b.answers[bad]}" raises ${outs[bad].output.split(":")[0]}.`, outputs: outs.map((o) => o.output) };
    const same = outs.every((o) => o.output === outs[0].output);
    return same ? { ok: true, note: `All ${outs.length} answers run and print ${JSON.stringify(outs[0].output.trim())}.`, outputs: outs.map((o) => o.output) }
      : { ok: false, note: "The accepted answers print different things.", outputs: outs.map((o) => o.output) };
  };
  // Parsons: run the lines in order and compare with the expected output.
  L.verifyParsons = async (b) => {
    const r = await L.runPython((b.lines || []).join("\n"));
    if (r.error) return { ok: false, note: `The lines in order raise ${r.output}.`, actual: r.output };
    const ok = r.output.trim() === String(b.output || "").trim();
    return { ok, note: ok ? `Ran the lines in order: prints ${JSON.stringify(r.output.trim())}.` : `In order it prints ${JSON.stringify(r.output.trim())}, not ${JSON.stringify(String(b.output || "").trim())}.`, actual: r.output };
  };

  // ---- Helpers ----------------------------------------------------------------------------
  L.textOf = (b) => (b.children || []).map((c) => c.text || "").join("");
  L.words = (s) => String(s || "").split(/\s+/).filter(Boolean).length;
  L.rangeValues = (start, stop, step) => {
    if (!step) return null;
    const v = [];
    for (let x = start; step > 0 ? x < stop : x > stop; x += step) { v.push(x); if (v.length > 60) break; }
    return v;
  };
  // "['eggs', 'milk']" -> { open: "[", close: "]", items: ["'eggs'", "'milk'"] }; null if not a flat container.
  L.splitRepr = (s) => {
    s = String(s || "");
    const open = s[0], close = { "[": "]", "(": ")", "{": "}" }[open];
    if (!close || s[s.length - 1] !== close) return null;
    const body = s.slice(1, -1), items = [];
    let depth = 0, q = null, cur = "";
    for (let i = 0; i < body.length; i++) {
      const c = body[i];
      if (q) { cur += c; if (c === "\\") { cur += body[++i] || ""; } else if (c === q) q = null; continue; }
      if (c === "'" || c === '"') { q = c; cur += c; continue; }
      if ("[({".includes(c)) depth++;
      if ("])}".includes(c)) depth--;
      if (c === "," && depth === 0) { items.push(cur.trim()); cur = ""; continue; }
      cur += c;
    }
    if (cur.trim()) items.push(cur.trim());
    return { open, close, items };
  };
  // Which step of a trace a memory snapshot equals (or -1).
  L.stepIndexOf = (steps, names, heap) => {
    const key = JSON.stringify([names, heap]);
    for (let k = steps.length - 1; k >= 0; k--) if (JSON.stringify([steps[k].names, steps[k].heap]) === key) return k;
    return -1;
  };
  // "After line 3", "After line 3 (2nd time)", "At the end", for steps 1..n-1.
  L.snapshotLabels = (steps) => {
    const seen = {};
    return steps.map((s, k) => {
      if (k === 0) return "Before line 1";
      if (s.line === null) return "At the end";
      const ln = steps[k - 1].line; seen[ln] = (seen[ln] || 0) + 1;
      const n = seen[ln];
      return `After line ${ln}${n > 1 ? ` (${n}${n === 2 ? "nd" : n === 3 ? "rd" : "th"} time)` : ""}`;
    });
  };

  // ---- Block catalog ----------------------------------------------------------------------
  L.BLOCKS = [
    ["explain", "Explanation", "Two or three sentences of the idea, in your words.", "Text"],
    ["mistake", "Common mistake", "The mistake students make most, worded as they'd think it.", "Text"],
    ["recap", "Recap", "Three short lines students leave with.", "Text"],
    ["h2", "Title", "A heading for a part of the lesson.", "Text"],
    ["example", "Worked example", "Code that runs here; students see what it prints.", "Code"],
    ["trace", "Step-through", "Students step line by line and watch the variables change.", "Code"],
    ["memory", "Memory diagram", "Names and the objects they point at, at one moment.", "Code"],
    ["explore", "Explorable", "Sliders and a number line students can play with.", "Code"],
    ["predict", "Predict the output", "Students guess what code prints before seeing it.", "Practice"],
    ["branch", "Misconception check", "A question where each wrong answer gets its own fix.", "Practice"],
    ["fill", "Fill the blank", "Students complete one line; accepted answers are run.", "Practice"],
    ["parsons", "Order the lines", "Students put shuffled lines in order, with decoys.", "Practice"],
    ["check", "Check question", "One multiple-choice question from the approved bank.", "Practice"],
  ];
  L.label = (t) => (L.BLOCKS.find((b) => b[0] === t) || [t, t])[1];

  // ---- New blocks, seeded from the subtopic -----------------------------------------------
  const node = (type, extra, text = "") => ({ type, ...extra, children: [{ text }] });
  const blankLine = (code) => {
    const lines = String(code || "").split("\n");
    for (let i = 0; i < lines.length; i++) {
      const m = lines[i].match(/^(\s*\w+\s*=\s*)(.+)$/);
      if (m) { lines[i] = m[1] + "____"; return { code: lines.join("\n"), answer: m[2].trim() }; }
    }
    for (let i = 0; i < lines.length; i++) {
      const m = lines[i].match(/^(\s*print\()(.+)(\))\s*$/);
      if (m) { lines[i] = m[1] + "____" + m[3]; return { code: lines.join("\n"), answer: m[2].trim() }; }
    }
    return { code: (code || "x = ____") , answer: "" };
  };
  L.newBlock = (type, ctx) => {
    const { sub, seed, M, value } = ctx;
    const traceCode = (value || []).find((b) => b.type === "trace")?.code;
    const exCode = traceCode || seed?.example || "total = 0\nfor n in [3, 5, 2]:\n    total += n\nprint(total)";
    const mistake = M.lessonMistake[sub.name];
    switch (type) {
      case "h2": return node("h2", {}, "New section");
      case "explain": return node("explain", {}, "");
      case "mistake": return node("mistake", {}, mistake || "Describe the mistake students make most often.");
      case "example": return node("example", { code: seed?.example || "", output: seed?.example_out || "", source: "" });
      case "predict": return node("predict", { code: seed?.predict || "", question: "What does this print?", answer: seed?.predict_ans || "" });
      case "check": return M.lessonBankCheck(sub.name);
      case "trace": return node("trace", { code: exCode, steps: [], caption: "Step through it and watch the variables change.", stale: true });
      case "memory": {
        const steps = L.traceCache[exCode] || (value || []).find((b) => b.type === "trace" && b.code === exCode)?.steps;
        const last = steps && steps[steps.length - 1];
        return node("memory", { code: exCode, names: last ? last.names : {}, heap: last ? last.heap : {}, caption: "What the names point at once the code has run.", stale: !last });
      }
      case "branch": {
        const ins = (M.insights?.python?.misconceptions || []).find((x) => x.subtopic === sub.name);
        return node("branch", {
          question: seed ? `What does this print?\n\n${seed.predict}` : "Which is true?",
          options: [String(seed?.predict_ans || "").trim() || "The right answer", ins?.top_wrong || "An error"],
          answer: 0,
          remediation: { "1": { text: mistake || "Explain why this answer is wrong.", misconception: ins?.reading || "" } },
          misconception: ins?.reading || "",
        });
      }
      case "fill": { const f = blankLine(seed?.example); return node("fill", { code: f.code, answers: f.answer ? [f.answer] : [], hint: "" }); }
      case "parsons": return node("parsons", { prompt: "Put the lines in order so it prints the output below.", lines: String(seed?.example || "").split("\n").filter(Boolean), distractors: [], output: seed?.example_out || "" });
      case "explore": return node("explore", { kind: "range", start: 0, stop: 5, step: 1, caption: "Drag the sliders. The fence at stop is never included." });
      case "recap": return node("recap", { points: (seed?.idea || "").split(/(?<=[.!?])\s+/).filter(Boolean).slice(0, 3) });
      default: return null;
    }
  };

  // ---- Time estimate: reading at ~180 words a minute plus a fixed time to do each block ------
  const DOING = { predict: 25, example: 15, trace: 0, memory: 15, branch: 25, fill: 30, parsons: 45, explore: 25, check: 25 };
  L.estimate = (value) => {
    let words = 0, doing = 0;
    for (const b of value) {
      words += L.words(L.textOf(b)) + L.words(b.caption) + L.words(b.question) + L.words(b.prompt) + L.words((b.points || []).join(" "));
      if (b.type === "trace") doing += Math.max(20, 4 * (b.steps || []).length);
      else doing += DOING[b.type] || 0;
    }
    const reading = Math.round((words / 180) * 60), total = reading + doing;
    return { reading, doing, total, label: `about ${Math.max(1, Math.round(total / 60))} min` };
  };

  // ---- "Ask AI": proposals mocked by keyword ------------------------------------------------
  // TODO(real): the instruction, the lesson and the style rules go to the lesson generator,
  // which returns a new block list; traces in it are recorded in the sandbox before it's shown.
  const same = (value) => value.map((block) => ({ kind: "same", block }));
  const insertRows = (value, at, blocks) => { const r = same(value); r.splice(at, 0, ...blocks.map((block) => ({ kind: "add", block }))); return r; };
  const lastIndex = (value, types) => { let k = -1; value.forEach((b, i) => { if (types.includes(b.type)) k = i; }); return k; };
  const where = (value, types, fallback) => { const k = lastIndex(value, types); return k >= 0 ? k + 1 : fallback; };
  const beforeEnd = (value) => { const k = value.findIndex((b) => ["mistake", "check", "recap"].includes(b.type)); return k >= 0 ? k : value.length; };

  L.suggestions = (sub) => sub.name === "Aliasing"
    ? ["Add a step-through of the copy", "Make a misconception check for b = a", "Turn this into a 2-minute version"]
    : sub.name === "range() and counted loops"
      ? ["Make a misconception check for range(3) starting at 1", "Add an order-the-lines task", "Turn this into a 2-minute version"]
      : ["Add a step-through of the example", "Add a recap", "Use simpler words"];

  L.propose = (instruction, value, ctx) => {
    const q = instruction.toLowerCase();
    const { sub, seed, M } = ctx;
    const isAlias = sub.name === "Aliasing", isRange = sub.name === "range() and counted loops";

    if (/\b(2|two)[- ]?min|shorter|short version|trim|cut it/.test(q)) {
      // Drop practice first, extra step-throughs next; the opening predict question goes last (her style).
      const target = 120, drop = ["parsons", "fill", "memory", "explore", "example", "trace+", "check", "predict"];
      const keep = value.slice(), removed = new Set();
      const firstTrace = value.findIndex((b) => b.type === "trace");
      for (const t of drop) {
        if (L.estimate(keep.filter((_, i) => !removed.has(i))).total <= target) break;
        keep.forEach((b, i) => { if ((t === "trace+" ? b.type === "trace" && i !== firstTrace : b.type === t) && !removed.has(i)) removed.add(i); });
      }
      const rows = [];
      value.forEach((b, i) => {
        if (removed.has(i)) rows.push({ kind: "del", block: b });
        else rows.push({ kind: "same", block: b });
      });
      if (!removed.size) return { none: true, message: `This lesson is already ${L.estimate(value).label}.` };
      const dropped = [...new Set([...removed].sort((x, y) => x - y).map((i) => L.label(value[i].type).toLowerCase()))];
      return { title: "A 2-minute version", why: `Drops the ${dropped.join(", ")} (${removed.size} block${removed.size === 1 ? "" : "s"}); they can go into a practice set instead.`, rows };
    }

    if (/step|trace|walk ?through/.test(q)) {
      const code = isAlias && /cop/.test(q)
        ? "groceries = ['eggs', 'milk']\ncopy = groceries[:]\ncopy.append('jam')\nprint(groceries)\nprint(copy)"
        : (value.find((b) => b.type === "example") || value.find((b) => b.type === "predict"))?.code || seed?.example || "";
      if (!code) return { none: true, message: "There's no code in this lesson to step through yet. Add a worked example first." };
      const b = node("trace", { code, steps: [], caption: isAlias && /cop/.test(q) ? "Step through the copy. groceries[:] makes a second list, so jam only goes into copy." : "Step through it and watch the variables change.", stale: true });
      return { title: isAlias && /cop/.test(q) ? "Step-through of the copy" : "Step-through of the example", why: "Recorded by running the code, so every step is what Python actually does.", rows: insertRows(value, where(value, ["trace", "memory", "example"], 3), [b]), record: true };
    }

    if (/misconception|wrong answer|branch|check for|starting at/.test(q)) {
      let b;
      if (isAlias || /b\s*=\s*a|alias|copy/.test(q)) b = node("branch", {
        question: "a = [1, 2]\nb = a\n\nWhich is true now?",
        options: ["b is a copy of a", "a and b name the same list", "b is an empty list"],
        answer: 1,
        remediation: {
          "0": { text: "b = a never copies. It gives the list a second name, so a change through b shows up in a too. Look at the diagram: both arrows go to one list.", show: "memory", misconception: "Treats b = a as a copy" },
          "2": { text: "Assignment doesn't create anything new. b names exactly the list a already names, items and all.", misconception: "Thinks assignment makes a new, empty object" },
        },
        misconception: "Treats b = a as a copy",
      });
      else if (isRange || /range/.test(q)) b = node("branch", {
        question: "What does this print?\n\nfor i in range(3):\n    print(i, end=' ')",
        options: ["0 1 2", "1 2 3", "0 1 2 3"],
        answer: 0,
        remediation: {
          "1": { text: "range(3) starts at 0, not 1. With one number, range counts 0, 1, 2: three numbers, starting from zero.", show: "explore", misconception: "Starts range(3) at 1" },
          "2": { text: "3 is the stop value, and range stops before it. Drag stop on the number line: the fence is never included.", show: "explore", misconception: "Includes the stop value" },
        },
        misconception: "Starts range(3) at 1",
      });
      else b = L.newBlock("branch", ctx);
      return { title: "Misconception check", why: M.insights?.python?.misconceptions?.find((x) => x.subtopic === sub.name)
        ? `Built from Insights: ${Math.round(M.insights.python.misconceptions.find((x) => x.subtopic === sub.name).top_wrong_share * 100)}% of students pick the same wrong answer.` : "Each wrong option gets its own short fix.",
        rows: insertRows(value, beforeEnd(value), [b]) };
    }

    if (/order|parsons|reorder|lines/.test(q)) {
      const b = isRange
        ? node("parsons", { prompt: "Put the lines in order so it prints the total of 2, 4 and 6.", lines: ["total = 0", "for price in range(2, 8, 2):", "    total += price", "print(total)"], distractors: ["for price in range(2, 6, 2):", "    total = price"], output: "12" })
        : L.newBlock("parsons", ctx);
      return { title: "Order-the-lines task", why: "The expected output is checked by running the lines in order.", rows: insertRows(value, beforeEnd(value), [b]) };
    }
    if (/recap|summar/.test(q)) {
      const exists = value.findIndex((b) => b.type === "recap");
      const b = L.newBlock("recap", ctx);
      if (exists >= 0) { const r = same(value); r.splice(exists, 1, { kind: "del", block: value[exists] }, { kind: "add", block: b }); return { title: "New recap", why: "Rewritten from the explanation.", rows: r }; }
      return { title: "Recap", why: "Three lines from the explanation.", rows: insertRows(value, value.length, [b]) };
    }
    if (/simpl|plain|easier|shorter words/.test(q)) {
      const rows = [];
      let n = 0;
      value.forEach((b) => {
        if (b.type === "explain" && seed && L.textOf(b) !== seed.idea && L.words(L.textOf(b)) > L.words(seed.idea)) { rows.push({ kind: "del", block: b }, { kind: "add", block: node("explain", {}, seed.idea) }); n++; }
        else rows.push({ kind: "same", block: b });
      });
      if (!n) return { none: true, message: "The explanations are already as short as the book's core idea." };
      return { title: "Simpler explanation", why: "Quoted from the book's core idea for this subtopic.", rows };
    }
    if (/memory|diagram|picture|box/.test(q)) return { title: "Memory diagram", why: "A snapshot from running the code.", rows: insertRows(value, where(value, ["trace"], 3), [L.newBlock("memory", ctx)]) };
    if (/explor|slider|number line/.test(q)) return { title: "Explorable", why: "Students drag start, stop and step.", rows: insertRows(value, where(value, ["explain"], 2), [L.newBlock("explore", ctx)]) };
    if (/fill|blank/.test(q)) return { title: "Fill the blank", why: "Accepted answers are checked by running them.", rows: insertRows(value, beforeEnd(value), [L.newBlock("fill", ctx)]) };
    return { none: true, message: "In this mockup, Ask AI understands: step-through, misconception check, 2-minute version, order the lines, recap, simpler words, memory diagram, explorable, fill the blank." };
  };
})();
