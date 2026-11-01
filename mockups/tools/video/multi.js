const { start } = require('./lib');
(async () => {
  const v = await start('multi', { width: 1440, height: 900 });
  const { page } = v;
  await v.go('courses.html', 600);
  await v.card('Three courses, one place', 'Dr. Maya Chen teaches Intro to Python, Intro Biology and Intro Statistics this fall', 3400);

  // ---- Part 1: a new course in a new subject -------------------------------------------
  await v.card('Part 1 · Setting up a new course', 'STAT 152 Intro Statistics, from nothing to a checked question bank', 2600);
  await v.caption('My courses is her home. Two courses are running; she adds a third.', 1200);
  await v.click('a:has-text("New course")', 1400);
  await v.caption('Name, code, subject. The subject decides which answer formats she gets, and how each is checked.', 600);
  await v.type('input[placeholder="e.g. Intro Statistics"]', 'Intro Statistics', 150);
  await v.type('input[placeholder="STAT 152"]', 'STAT 152', 300);
  await v.click('label:has(input[value="statistics"])', 1200);
  await v.point('text=Answer formats'); await v.wait(1800);
  await v.click('button:has-text("Create course")', 1800);

  await v.go('course.html?course=statistics', 600);
  await v.caption('Six steps, in order. Step 1: the textbook.', 1600);
  await v.go('materials.html?course=statistics', 500);
  await v.click('button:has-text("Upload book")', 900);
  await v.click('button:has-text("Use a sample file")', 900);
  await v.caption('She uploads OpenIntro Statistics. Splitting it into sections runs in the background.', 400);
  await v.click('button:has-text("Import book")', 2600);

  await v.go('taxonomy-draft.html?course=statistics', 600);
  await v.caption('Step 2: the AI drafted the topics from the book\'s chapters. It only proposes; she decides.', 1000);
  await v.click('button:has-text("Accept all high-confidence")', 1400);
  await v.caption('She accepts the rest, edits what she wants, and approves.', 300);
  while (await page.locator('tbody button').filter({ hasText: /^Accept$/ }).count()) {
    await page.locator('tbody button').filter({ hasText: /^Accept$/ }).first().click(); await v.wait(50);
  }
  await v.wait(500);
  await v.click('button:has-text("Approve taxonomy")', 1000);
  const confirm = page.locator('dialog[open] button').filter({ hasText: /Approve/ }).first();
  if (await confirm.count()) await v.click(confirm, 2000);

  await v.go('section.html?course=statistics&book=b3&section=b3-5-2', 600);
  await v.caption('Every section was analysed at import: what can be tested, and how each answer will be checked.', 2800);
  await v.point('text=Margin of error'); await v.wait(1400);
  await v.caption('Generating, reviewing and opening a class are the same steps as in her other two courses.', 2400);

  // ---- Part 2: running three courses ---------------------------------------------------
  await v.caption('', 0);
  await v.card('Part 2 · Running three courses', 'Python and Biology are in week 5; Statistics is getting ready', 2600);
  await v.go('courses.html', 600);
  await v.caption('Totals across all three: questions waiting for her, students, AI spend against the monthly cap.', 3000);
  await v.caption('Each running course shows this week: the assignment due, who\'s done, and the mistake most students made.', 1000);
  await v.point('text=Most missed: 44% on Glycolysis'); await v.wait(2600);
  await v.caption('Biology has three sections. Each has its own join code and practice set.', 800);
  await v.click(page.locator('a').filter({ hasText: '3 sections' }).first(), 1800);
  await v.caption('The honors section practises a larger set with extension questions; the others share one set.', 1000);
  await v.scrollTo('text=Honors section', 2800);

  await v.caption('The course switcher jumps straight to another course.', 800);
  await v.scroll(-3000, 600);
  await v.click('.mock-switch > summary', 2200);
  await v.click('.mock-switch a:has-text("Intro to Python")', 1800);
  await v.caption('Intro to Python opens on this week. During term the menu shows only the pages she uses weekly.', 3400);

  await v.go('email-digest.html', 600);
  await v.caption('Every Monday one email covers all three courses: what each class got wrong and what\'s waiting.', 1200);
  await v.scrollTo('strong:has-text("BIOL 190 · Intro Biology")', 3200);
  await v.scrollTo('strong:has-text("STAT 152 · Intro Statistics")', 2400);
  await v.caption('', 0);
  await v.card('Set up in steps, run from one page', 'New course: subject → book → approve topics · Running: one home page, a switcher, one Monday email', 3800);
  console.log(await v.end());
})();
