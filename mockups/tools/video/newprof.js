const { start } = require('./lib');
(async () => {
  const v = await start('new', { width: 1440, height: 900 });
  const { page } = v;
  await v.go('landing.html', 600);
  await v.card('A new professor', 'Dr. Maya Chen teaches Intro Statistics (STAT 152) and has never used the product', 3400);
  await v.caption('She finds the product through a colleague. The pitch: practice questions built from her own textbook.', 3000);
  await v.click('main a:has-text("Create a free account")', 1500);
  await v.caption('An instructor account. Students never need one.', 600);
  await v.type('input[placeholder="Maya Chen"]', 'Maya Chen', 200);
  await v.type('input[type="email"]', 'mchen@stat.example.edu', 200);
  await v.type('input[type="password"]', 'correct-horse-9', 200);
  await v.click('input[type="checkbox"]', 500);
  await v.click('button:has-text("Create account")', 1800);
  if (!page.url().includes('verify')) await v.go('verify-email.html', 600);
  await v.caption('She confirms her email.', 1600);

  await v.go('courses.html?new=1', 600);
  await v.caption('A brand-new account shows a finished sample course to explore before building her own.', 2800);
  await v.click('a:has-text("Explore the sample")', 1800);
  await v.caption('The sample is Prof. Example\'s made-up class, five weeks into term. It\'s clearly not hers, and nothing is saved.', 3200);
  await v.click('a:has-text("Create your own course")', 1600);

  await v.caption('Her course: name, code, and subject. The subject decides which question types make sense.', 600);
  await v.type('input[placeholder="e.g. Intro Statistics"]', 'Intro Statistics', 200);
  await v.type('input[placeholder="STAT 152"]', 'STAT 152', 300);
  await v.click('label:has(input[value="statistics"])', 1400);
  await v.caption('Each subject gets the answer formats that can be checked. Numeric answers are Computed: a program works them out.', 1000);
  await v.point('text=Answer formats'); await v.wait(1400);
  await v.scrollTo('text=Put in order', 2400);
  await v.click('button:has-text("Create course")', 2000);

  await v.go('course.html?course=statistics', 600);
  await v.caption('The overview is a six-step checklist. Step 1: add the textbook.', 2800);
  await v.go('materials.html?course=statistics', 600);
  await v.click('button:has-text("Upload book")', 1200);
  await v.click('button:has-text("Use a sample file")', 1400);
  await v.caption('She uploads OpenIntro Statistics. It\'s split into 64 sections and embedded in the background.', 800);
  await v.click('button:has-text("Import book")', 3200);

  await v.go('taxonomy.html?course=statistics', 600);
  await v.caption('Step 2, the taxonomy: the topics students are assessed on. The AI drafted one from the book\'s chapters.', 3200);
  await v.click('a:has-text("Continue review")', 1800);
  await v.caption('The AI only proposes. She accepts, edits or discards every row. First, all the high-confidence ones.', 800);
  await v.click('button:has-text("Accept all high-confidence")', 2000);
  await v.caption('Then the rest, one by one.', 400);
  for (let i = 0; i < 4; i++) await v.click(page.locator('tbody button').filter({ hasText: /^Accept$/ }).first(), 350);
  // The remaining rows are decided off-camera speed: same action, no cursor travel.
  while (await page.locator('tbody button').filter({ hasText: /^Accept$/ }).count()) {
    await page.locator('tbody button').filter({ hasText: /^Accept$/ }).first().click(); await v.wait(60);
  }
  await v.wait(600);
  await v.caption('Every row is decided. She approves it, and it becomes the course\'s active taxonomy.', 600);
  await v.click('button:has-text("Approve taxonomy")', 1200);
  const confirm = page.locator('dialog[open] button').filter({ hasText: /Approve/ }).first();
  if (await confirm.count()) await v.click(confirm, 2400);
  await v.wait(1200);

  await v.go('section.html?course=statistics&book=b3&section=b3-5-2', 600);
  await v.caption('The book was already analysed at import. Section 5.2 has 4 testable items; the figure is skipped, with the reason.', 2800);
  await v.point('text=Margin of error'); await v.wait(1600);
  await v.caption('A formula becomes a numeric question checked by running code; a definition becomes multiple choice backed by a quote.', 3200);
  await v.caption('', 0);
  await v.card('The rest of setup', 'Shown in a finished course (Intro to Python), since the new one has no questions yet', 3000);
  await v.go('coverage.html?course=python', 600);
  await v.caption('Step 3, coverage: every subtopic needs 2 approved questions at each difficulty. The gaps are red.', 2400);
  await v.go('generate.html?course=python', 600);
  await v.caption('She picks what to test in section 9.11, then a format. The pill shows how its answer key will be checked.', 800);
  await v.click(page.locator('label, button').filter({ hasText: 'b = a; b[0] = 42 changes' }).first(), 1600);
  await v.caption('Output prediction is Computed: a program runs the snippet and must reproduce the answer.', 1800);
  await v.click('button:has-text("Generate 3 questions")', 3400);
  await v.go('review.html?course=python', 600);
  await v.caption('Step 4, review. Next to each question: how its key was checked, and the mistake behind each wrong option.', 2000);
  await v.point('text=Answer key check'); await v.wait(1400);
  await v.caption('A computed or quoted answer is evidence; the AI reviewers are opinions. She decides.', 1800);
  await v.click('button:has-text("Approve")', 2000);
  await v.go('schedule.html?course=python', 600);
  await v.caption('Before term, she maps topics to the weeks of her syllabus, so students only practise what has been taught.', 2600);
  await v.go('classes.html?course=python', 600);
  await v.caption('Last step: open a class. She puts the join code on the syllabus. That is all students need.', 2600);
  await v.caption('', 0);
  await v.card('From textbook to first practice', 'Sign up · sample course · upload the book · approve the taxonomy · review questions · share a join code', 3800);
  console.log(await v.end());
})();
