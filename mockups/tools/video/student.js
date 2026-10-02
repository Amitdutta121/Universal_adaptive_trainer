const { start } = require('./lib');
(async () => {
  const v = await start('student', { width: 390, height: 844, scale: 2 });
  const { page } = v;
  await v.go('student-join.html', 600);
  await v.card('A student\'s week', 'Elena Kowalski, CS 135 Section 001, practising on her phone', 3200);
  await v.caption('Week 1: Elena types the join code her professor put on the syllabus.', 1500);
  await v.type('input[placeholder="ABC-123"]', 'PY7-K4Q');
  await v.click('button:has-text("Find class")', 1500);
  await v.caption('No account and no password: just her name and school email.', 1200);
  await v.type('input[type="email"]', 'elena.kowalski@example.edu', 800);
  await v.caption('', 0);
  await v.card('Five weeks later', 'Week 5 of 15 · Dictionaries is due on Friday', 2600);

  await v.go('student-home.html', 800);
  await v.caption('Her home page leads with what\'s due: reach 70% on Dictionaries by Friday. She\'s at 43%.', 3200);
  await v.caption('She can only practise what has been taught so far. Tuples and sets opens on Monday.', 1000);
  await v.scrollTo('text=Tuples and sets', 2600);
  await v.scroll(-2000, 1000);
  await v.caption('Continue practising.', 600);
  await v.click('a:has-text("Continue practising"), button:has-text("Continue practising")', 1800);

  await v.caption('Each session opens with a warm-up on a topic she knows. She gets it.', 800);
  await v.click(page.locator('label').filter({ has: page.locator('input[type=radio]') }).nth(1), 500);
  await v.click('button:has-text("Submit answer")', 1600);
  await v.click('button:has-text("Next question")', 1500);
  await v.caption('Then her weakest subtopic: Aliasing, at 31%.', 2400);
  await v.caption('She thinks b = a makes a copy, and picks [1, 2, 3].', 800);
  await v.click('label:has-text("[1, 2, 3]")', 600);
  await v.click('button:has-text("Submit answer")', 1500);
  await v.caption('Wrong. She sees why, a gentle "needs more practice" for Lists, and a refresher on this exact mistake.', 2400);
  await v.scrollTo('text=Quick refresher', 3200);
  await v.click('button:has-text("Next question")', 1500);

  await v.caption('Next: an output-prediction question on range(). She types the output.', 1200);
  await v.type('textarea', '1 4 7', 600);
  await v.click('button:has-text("Submit answer")', 1500);
  await v.caption('Correct. Loops mastery goes from 41% to 48%.', 2600);
  await v.click('button:has-text("Next question")', 1600);

  await v.caption('Something about this question looks off to her, so she reports it to her instructor.', 1000);
  await v.click('button:has-text("Report this question")', 1300);
  const reason = page.locator('dialog[open] label').filter({ hasText: /unclear/i }).first();
  if (await reason.count()) await v.click(reason, 600);
  const note = page.locator('dialog[open] textarea').first();
  if (await note.count()) await v.type(note, 'Line 4 could go in two places and both work?', 600);
  await v.click('dialog[open] button:has-text("Send report")', 1800);
  await v.caption('The report goes to the professor\'s Student reports inbox, along with her answer.', 2200);

  await v.caption('She has to leave for class, so she ends the session.', 800);
  await v.click('button:has-text("End session")', 2000);
  await v.caption('The summary shows what moved and which subtopics her next session starts with.', 3200);
  await v.scroll(420, 2600);
  await v.caption('', 0);
  await v.wait(500);
  await v.card('That\'s the student side', 'Join with a code · practise what has been taught · see what\'s due · report bad questions', 3400);
  console.log(await v.end());
})();
