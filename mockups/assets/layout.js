/*
 * Shared chrome for every mockup page. Load it as a plain (non-deferred) script at the
 * END of <body>, after mock-data.js, so it rebuilds the DOM before Alpine (deferred) starts.
 *
 * A page declares itself with attributes on <body>:
 *   data-scope = "public" | "workspace" | "course" | "student"
 *   data-nav   = key of the active sidebar item (see NAV below)
 *   data-title = text for the top bar (optional; defaults to the nav label)
 * and puts its content in a single <main>. layout.js moves that <main> into the shell.
 *
 * Course pages read the course from ?course=<id> (default "python"). Always build links
 * with Mock.link("page.html") so the course param carries over.
 */
(function () {
  const M = window.MOCK;
  const params = new URLSearchParams(location.search);
  const courseId = params.get("course") || "python";
  const course = M.course(courseId);
  const body = document.body;
  const scope = body.dataset.scope || "public";
  const navKey = body.dataset.nav || "";
  // ?sample=1: a new professor exploring the read-only sample course (G0). Kept on every course link.
  const sample = params.get("sample") === "1";

  const link = (href, extra) => {
    const [path, q] = href.split("?");
    const p = new URLSearchParams(q || "");
    if (!p.has("course")) p.set("course", courseId);
    if (sample && !p.has("sample")) p.set("sample", "1");
    Object.entries(extra || {}).forEach(([k, v]) => p.set(k, v));
    return `${path}?${p.toString()}`;
  };

  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  // key, label, file, lucide icon, setup step (drives the done/next badge)
  const COURSE_NAV = [
    ["Set up", [
      ["course", "Overview", "course.html", "layout-dashboard"],
      ["materials", "Materials", "materials.html", "book-open", "materials"],
      ["taxonomy", "Taxonomy", "taxonomy.html", "network", "taxonomy"],
      ["coverage", "Coverage", "coverage.html", "grid-3x3", "coverage"],
    ]],
    ["Questions", [
      ["generate", "Generate", "generate.html", "wand-sparkles"],
      ["questions", "Question bank", "questions.html", "list-checks"],
      ["import", "Import questions", "import-questions.html", "file-up"],
      ["review", "Review queue", "review.html", "clipboard-check", "review"],
      ["alignment", "Alignment", "alignment.html", "scale"],
      ["exams", "Exam export", "exam-export.html", "file-output"],
    ]],
    ["Teach", [
      ["schedule", "Schedule", "schedule.html", "calendar-days"],
      ["lessons", "Lessons", "lessons.html", "book-open-check"],
      ["assignments", "Assignments", "assignments.html", "calendar-check"],
      ["question-sets", "Question sets", "question-sets.html", "lock", "question_set"],
      ["classes", "Classes", "classes.html", "school", "classes"],
    ]],
    ["Class", [
      ["insights", "Insights", "insights.html", "lightbulb"],
      ["gradebook", "Gradebook", "gradebook.html", "table-2"],
      ["students", "Students", "students.html", "users"],
      ["reports", "Student reports", "reports.html", "flag"],
      ["term-report", "Term report", "term-report.html", "file-text"],
    ]],
    ["Course", [["settings", "Settings", "settings.html", "settings"]]],
  ];
  const WORKSPACE_NAV = [
    ["Workspace", [
      ["courses", "My courses", "courses.html", "library"],
      ["jobs", "Jobs", "jobs.html", "loader"],
      ["usage", "Usage and limits", "usage.html", "gauge"],
      ["account", "Account", "account.html", "user"],
    ]],
  ];

  const STEP_BADGE = {
    done: ["tone-ok", "Done"],
    in_progress: ["tone-warn", "In progress"],
    todo: ["tone-muted", "To do"],
  };

  function navLabel() {
    for (const [, items] of [...COURSE_NAV, ...WORKSPACE_NAV])
      for (const it of items) if (it[0] === navKey) return it[1];
    return "";
  }

  // Once students can practise (a set is frozen and a class is open), the professor's week runs
  // through a handful of pages. Lead with those; fold setup and rarer pages into "More".
  const inTerm = scope === "course" && !!M.schedule?.[courseId] && course.setup.question_set === "done" && course.setup.classes === "done";
  const TERM_KEYS = ["course", "insights", "lessons", "review", "assignments", "gradebook", "students", "reports"];
  function termNav() {
    const all = COURSE_NAV.flatMap(([, items]) => items);
    const lead = TERM_KEYS.map((k) => all.find((it) => it[0] === k)).filter(Boolean);
    const more = all.filter((it) => !TERM_KEYS.includes(it[0]));
    return { lead, more };
  }

  function sidebarHtml(groups, isCourse) {
    const running = M.jobs.filter((j) => j.status === "running").length;
    const item = ([key, label, file, icon, step]) => {
      const href = isCourse ? link(file) : file;
      const badge = isCourse && step ? STEP_BADGE[course.setup[step]] : null;
      const jobBadge = key === "jobs" && running ? `<span class="mock-step tone-accent">${running} running</span>` : "";
      const openReports = key === "reports" ? (M.reports || []).filter((r) => r.status === "open" && M.question(r.question_id)?.course === courseId).length : 0;
      const reportBadge = openReports ? `<span class="mock-step tone-warn">${openReports} open</span>` : "";
      const review = key === "review" && course?.numbers?.awaiting_review ? `<span class="mock-step tone-warn">${course.numbers.awaiting_review}</span>` : "";
      return `<li><a href="${href}" ${key === navKey ? 'aria-current="page"' : ""}>
        <i data-lucide="${icon}"></i><span>${esc(label)}</span>
        ${inTerm ? review : badge ? `<span class="mock-step ${badge[0]}">${badge[1]}</span>` : ""}${jobBadge}${reportBadge}</a></li>`;
    };
    if (isCourse && inTerm) {
      const { lead, more } = termNav();
      const openMore = more.some((it) => it[0] === navKey);
      const groupsHtml = `
      <div role="group" aria-labelledby="nav-term"><h3 id="nav-term">This term</h3><ul>${lead.map(item).join("")}</ul></div>
      <div role="group"><details class="mock-more" ${openMore ? "open" : ""}><summary><span>More</span><span class="text-xs text-muted-foreground">${more.length} pages · setup, questions, settings</span></summary>
        <ul>${more.map(item).join("")}</ul></details></div>`;
      return sidebarFrame(groupsHtml, isCourse);
    }
    const groupsHtml = groups.map(([title, items], gi) => `
      <div role="group" aria-labelledby="nav-g${gi}">
        <h3 id="nav-g${gi}">${esc(title)}</h3>
        <ul>${items.map(([key, label, file, icon, step]) => {
          const href = isCourse ? link(file) : file;
          const badge = isCourse && step ? STEP_BADGE[course.setup[step]] : null;
          const jobBadge = key === "jobs" && running ? `<span class="mock-step tone-accent">${running} running</span>` : "";
          const openReports = key === "reports" ? (M.reports || []).filter((r) => r.status === "open" && M.question(r.question_id)?.course === courseId).length : 0;
          const reportBadge = openReports ? `<span class="mock-step tone-warn">${openReports} open</span>` : "";
          return `<li><a href="${href}" ${key === navKey ? 'aria-current="page"' : ""}>
            <i data-lucide="${icon}"></i><span>${esc(label)}</span>
            ${badge ? `<span class="mock-step ${badge[0]}">${badge[1]}</span>` : ""}${jobBadge}${reportBadge}</a></li>`;
        }).join("")}</ul>
      </div>`).join("");
    return sidebarFrame(groupsHtml, isCourse);
  }

  function sidebarFrame(groupsHtml, isCourse) {
    const header = isCourse
      ? `<header class="mock-course-head px-3 pt-3 pb-1">
          <a href="courses.html" class="text-xs text-muted-foreground inline-flex items-center gap-1 hover:underline"><i data-lucide="chevron-left" class="size-3"></i>All courses</a>
          ${sample ? `<div class="mt-2 font-display font-semibold leading-tight"><span class="mock-step tone-accent mr-1">Sample</span>${esc(course.name)}</div>` : `
          <details class="mock-switch mt-2"><summary class="font-display font-semibold leading-tight">${esc(course.name)}</summary>
            <ul>${M.courses.map((c) => `<li><a href="${(() => { const q = new URLSearchParams(); q.set("course", c.id); return `course.html?${q}`; })()}" ${c.id === courseId ? 'aria-current="page"' : ""}><span>${esc(c.name)}</span><span class="text-xs text-muted-foreground">${esc(c.code)}</span></a></li>`).join("")}
              <li><a href="courses.html"><span class="text-muted-foreground">All courses</span></a></li></ul>
          </details>`}
          <div class="text-xs text-muted-foreground">${sample ? "Prof. Example · made-up class · read-only" : `${esc(course.code)} · ${esc(course.term)} · ${esc(M.subject(course.subject).label)}`}</div>
        </header>`
      : "";

    return `<aside id="sidebar" class="sidebar" data-side="left" aria-hidden="false">
      <nav aria-label="Sidebar navigation">
        <header class="mock-brand flex items-center gap-2 px-3 pt-3">
          <span class="grid size-8 place-items-center rounded-lg" style="background:var(--primary);color:var(--primary-foreground)"><i data-lucide="graduation-cap" class="size-4"></i></span>
          <span class="leading-tight"><span class="block text-sm font-semibold font-display">Adaptive Trainer</span><span class="block text-xs text-muted-foreground">Instructor Studio</span></span>
        </header>
        ${header}
        <section class="scrollbar-sm">${groupsHtml}</section>
        <footer class="mock-user px-3 pb-3 text-xs text-muted-foreground flex items-center gap-2">
          <span class="grid size-7 place-items-center rounded-full tone-accent font-medium">${esc(M.me.initials)}</span>
          <span class="leading-tight"><span class="block text-foreground">${esc(M.me.name)}</span>${esc(M.me.email)}</span>
        </footer>
      </nav>
    </aside>`;
  }

  function topbarHtml() {
    const title = body.dataset.title || navLabel();
    const running = M.jobs.filter((j) => j.status === "running").length;
    return `<div class="mock-topbar">
      <button type="button" class="btn" data-variant="ghost" data-size="icon" aria-label="Toggle sidebar" onclick="document.getElementById('sidebar')?.toggle?.()"><i data-lucide="panel-left"></i></button>
      <div class="text-sm font-medium truncate">${esc(title)}</div>
      <div class="ml-auto flex items-center gap-2">
        <a href="jobs.html" class="btn" data-variant="ghost" data-size="sm" title="Background jobs" style="white-space:nowrap"><i data-lucide="loader" class="${running ? "animate-spin" : ""}"></i>${running} running</a>
        <button type="button" class="btn" data-variant="ghost" data-size="icon" aria-label="Toggle dark mode" onclick="Mock.toggleTheme()"><i data-lucide="moon"></i></button>
      </div>
    </div>`;
  }

  function publicHeader() {
    return `<header class="flex items-center gap-3 px-5 h-14 border-b" style="border-color:var(--border)">
      <a href="landing.html" class="flex items-center gap-2 font-display font-semibold">
        <span class="grid size-8 place-items-center rounded-lg" style="background:var(--primary);color:var(--primary-foreground)"><i data-lucide="graduation-cap" class="size-4"></i></span>Adaptive Trainer</a>
      <nav class="ml-auto flex items-center gap-2">
        <a class="btn" data-variant="ghost" data-size="sm" href="login.html">Log in</a>
        <a class="btn" data-size="sm" href="signup.html">Create a free account</a>
      </nav>
    </header>`;
  }

  function studentHeader() {
    const s = M.student_session.student;
    return `<header class="flex items-center gap-3 px-4 h-14 border-b" style="border-color:var(--border);background:var(--card)">
      <a href="student-home.html" class="flex items-center gap-2 font-display font-semibold text-sm">
        <span class="grid size-7 place-items-center rounded-lg" style="background:var(--primary);color:var(--primary-foreground)"><i data-lucide="graduation-cap" class="size-4"></i></span>Adaptive Trainer</a>
      <span class="ml-auto text-sm text-muted-foreground">${esc(s.name)}</span>
    </header>`;
  }

  // ---- Build the shell -----------------------------------------------------------
  const main = document.querySelector("main");
  const banner = document.createElement("div");
  banner.className = "mock-banner";
  banner.innerHTML = `Mockup · mock data, nothing is saved · <a class="underline" href="index.html">All pages</a>`;

  if (scope === "course" || scope === "workspace") {
    const shell = document.createElement("div");
    shell.className = "mock-shell";
    shell.innerHTML = sidebarHtml(scope === "course" ? COURSE_NAV : WORKSPACE_NAV, scope === "course");
    const col = document.createElement("div");
    col.className = "mock-main";
    col.innerHTML = topbarHtml();
    const content = document.createElement("div");
    content.className = "mock-content";
    if (scope === "course" && sample) {
      const bar = document.createElement("div");
      bar.className = "mock-sample-bar";
      bar.innerHTML = `<span><b>Sample course.</b> Prof. Example's class with made-up students. Look around; nothing you change here is kept.</span><a class="btn" data-size="sm" href="new-course.html">Create your own course</a>`;
      content.appendChild(bar);
    }
    content.appendChild(main); // move, don't copy: keeps Alpine attributes intact
    col.appendChild(content);
    shell.appendChild(col);
    body.prepend(banner, shell);
  } else {
    const wrap = document.createElement("div");
    wrap.innerHTML = scope === "student" ? studentHeader() : publicHeader();
    body.prepend(banner, wrap.firstElementChild);
  }

  const layoutCss = document.createElement("style");
  layoutCss.textContent = `
    .mock-more > summary { list-style: none; cursor: pointer; display: grid; gap: 2px; padding: 6px 8px; border-radius: 8px; font-size: 12px; font-weight: 500; color: var(--muted-foreground); }
    .mock-more > summary::-webkit-details-marker { display: none; }
    .mock-more > summary:hover { background: var(--sidebar-accent); }
    .mock-more > summary > span:first-child::after { content: " ▸"; }
    .mock-more[open] > summary > span:first-child::after { content: " ▾"; }
    .mock-switch > summary { list-style: none; cursor: pointer; }
    .mock-switch > summary::-webkit-details-marker { display: none; }
    .mock-switch > summary::after { content: " ▾"; font-size: 11px; color: var(--muted-foreground); }
    .mock-switch ul { margin-top: 6px; display: grid; gap: 2px; border: 1px solid var(--border); border-radius: 8px; padding: 4px; background: var(--card); }
    .mock-switch a { display: flex; justify-content: space-between; gap: 8px; padding: 6px 8px; border-radius: 6px; font-size: 13px; }
    .mock-switch a:hover, .mock-switch a[aria-current] { background: var(--sidebar-accent); }
    .mock-sample-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; padding: 10px 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--accent); font-size: 14px; }
    .mock-sample-bar .btn { margin-left: auto; }`;
  document.head.appendChild(layoutCss);

  const toastHost = document.createElement("div");
  toastHost.className = "mock-toast-host";
  body.appendChild(toastHost);

  // ---- Public helpers for pages --------------------------------------------------
  let iconTimer = null;
  const refreshIcons = () => {
    clearTimeout(iconTimer);
    iconTimer = setTimeout(() => window.lucide && window.lucide.createIcons(), 0);
  };

  window.Mock = {
    courseId, course, link, esc, refreshIcons,
    param: (name) => params.get(name),
    pct: (x) => (x == null ? "—" : `${Math.round(x * 100)}%`),
    usd: (x) => `$${x.toFixed(2)}`,
    toast(msg) {
      const el = document.createElement("div");
      el.className = "mock-toast";
      el.textContent = msg;
      toastHost.appendChild(el);
      setTimeout(() => el.remove(), 2600);
    },
    // Tone class for a question/book/job status string.
    tone(status) {
      return ({
        approved: "tone-ok", done: "tone-ok", imported: "tone-ok", pass: "tone-ok", published: "tone-ok", accepted: "tone-ok",
        validation_passed: "tone-accent", running: "tone-accent", generated: "tone-muted", proposed: "tone-muted", archived: "tone-muted",
        partial: "tone-warn", in_progress: "tone-warn", flag: "tone-warn", under_review: "tone-warn", flagged: "tone-warn",
        rejected: "tone-critical", validation_failed: "tone-critical", failed: "tone-critical", fail: "tone-critical",
      })[status] || "tone-muted";
    },
    label(status) {
      return ({
        validation_passed: "Awaiting review", validation_failed: "Failed checks", generated: "Generated",
        approved: "Approved", rejected: "Rejected", in_progress: "In progress", todo: "To do", under_review: "Under review",
      })[status] || String(status).replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
    },
    toggleTheme() {
      document.documentElement.classList.toggle("dark");
      try { localStorage.setItem("mock-theme", document.documentElement.classList.contains("dark") ? "dark" : "light"); } catch (e) {}
    },
  };

  try { if (localStorage.getItem("mock-theme") === "dark") document.documentElement.classList.add("dark"); } catch (e) {}

  // Lucide replaces <i data-lucide> with <svg>; re-run when Alpine renders new nodes.
  // Never bind Alpine attributes on the <i> itself — wrap it in a <span>.
  new MutationObserver(refreshIcons).observe(body, { childList: true, subtree: true });
  document.addEventListener("DOMContentLoaded", refreshIcons);
})();
