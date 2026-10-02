# Walkthrough videos

Scripted Playwright recordings of the mockup, with captions and a visible cursor.

    cd <scratch dir> && npm i playwright-core@1.63.0   # matches the installed Chromium 1243
    cp <this folder>/*.js . && node student.js         # also existing.js, newprof.js
    ffmpeg -i out/student/<id>.webm -c:v libx264 -pix_fmt yuv420p -crf 20 -movflags +faststart student.mp4

`lib.js` hides the "Mockup · mock data" banner in recordings. Output: `../../videos/`.
