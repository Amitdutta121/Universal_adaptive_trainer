const { start } = require('./lib');
(async () => {
  const v = await start('existing', { width: 1440, height: 900 });
  const { page } = v;
  await v.go('email-digest.html', 600);
  await v.card('A professor\'s Monday', 'Dr. Maya Chen · CS 135 Intro to Python · week 5 of 15 · 28 students in 2 sections', 3400);
  await v.caption('7:00 AM: the weekly digest arrives. It says what the class got wrong and what is waiting for her.', 1200);
  await v.scrollTo('text=What the class got wrong most', 3600);
  await v.scroll(420, 2600);

  await v.go('course.html?course=python', 600);
  await v.caption('She opens the course. During term, the overview starts with this week, not the setup checklist.', 3600);
  await v.point('text=Most common mistake this week'); await v.wait(1800);
  await v.caption('38% of the class thinks y = x copies a list. She opens this week\'s insights.', 800);
  await v.click('a:has-text("This week\'s insights")', 1800);

  await v.caption('Insights ranks the five weakest subtopics, each with the wrong answer most students picked.', 3200);
  await v.caption('"Show in lecture" puts the question on the projector with the answer spread and no student names.', 800);
  await v.click('button:has-text("Show in lecture")', 2200);
  await v.click('button:has-text("Reveal answer")', 2600);
  await v.click('[aria-label="Close lecture view"]', 1000);
  await v.caption("She'd rather the class practise this more next week, so she turns up its weight.", 600);
  await v.click('button:has-text("Practice more on this")', 2200);

  await v.go('reports.html?course=python', 600);
  await v.caption('Three student reports are waiting. Jamal\'s answer was right; only a trailing space made it wrong.', 3600);
  await v.caption('One click accepts it, trims whitespace for this question, and regrades 9 attempts.', 800);
  await v.click('button:has-text("Accept")', 2600);

  await v.go('gradebook.html?course=python', 600);
  await v.caption('The gradebook: every student against every practice assignment, sent to Canvas after each due date.', 3400);
  await v.caption('Dev Patel hasn\'t started Week 5. He emailed about an illness, so she extends his due date to Monday.', 800);
  await v.click('button:has-text("Not started")', 1400);
  await v.type('#ext-reason', 'Illness, emailed Sep 30', 500);
  await v.click('dialog[open] button:has-text("Grant extension")', 2200);

  await v.go('assignments.html?course=python', 600);
  await v.caption('Next week\'s assignment is still a draft. She opens it to publish.', 2200);
  await v.click('a:has-text("Week 6: Tuples and sets")', 1800);
  await v.caption('Scope comes from the schedule. The goal is "reach 70% on each topic", due Friday, 10 points.', 2600);
  await v.caption('Publish is blocked, and the reason is right under the button: no approved question on Tuples and sets yet.', 800);
  await v.point('text=Can\'t publish'); await v.wait(2400);
  await v.point('a:has-text("Generate for these topics")');
  await v.caption("So the draft waits: she'll generate and review Tuples and sets questions before publishing it.", 3200);

  await v.go('review.html?course=python', 600);
  await v.caption('Ten minutes left: she reviews generated questions. Each shows how its answer was checked.', 1200);
  await v.point('text=Answer key check'); await v.wait(1800);
  await v.caption('Each wrong option carries the mistake it was built from. The judges advise; she decides.', 2200);
  await v.click('button:has-text("Approve")', 2000);
  await v.click('button:has-text("Approve")', 2000);

  await v.go('exam-export.html?course=python', 600);
  await v.caption('Later in the week she builds the midterm makeup from approved questions.', 2600);
  await v.caption('Exported questions are held out of practice until the day after the exam.', 800);
  await v.scrollTo('text=Hold these questions', 2200);
  await v.click('button:has-text("Export 9 questions")', 2400);
  await v.caption('', 0);
  await v.card('About 30 minutes a week', 'Read the digest · reteach from Insights · handle reports · keep the gradebook fair · publish next week', 3600);
  console.log(await v.end());
})();
