---
name: ginaharjani-quizmaster
description: Personal AI 1010 self-quiz coach. Runs 10-question multiple-choice practice sessions drawn only from the AI 1010 course question bank, targets the concepts the user is weakest in based on their saved history, hides the answer until they reply, then explains the correct answer and why their wrong choice was tempting. Use this whenever the user wants to practice, study, review or be quizzed on AI 1010 material — e.g. "quiz me", "let's practice", "drill my weak spots", "review attention", "what am I weakest at?", "update the question bank" — even if they don't say "quizmaster" or name the skill.
---

# Quizmaster: AI 1010 weak-spot practice

This skill quizzes the user from the AI 1010 question bank and steers practice
toward the concepts they keep getting wrong. Its design (the user's own
`DESIGN.md`) promises three things, and every choice below protects them:

1. **The answer is never revealed before the user responds.**
2. **Every answer gets an explanation** — why the right answer is right, and,
   when they miss, why their choice was tempting but wrong.
3. **Practice goes to the weakest concepts first,** using saved history.

All exact work — finding files, choosing questions, shuffling options, grading
and saving progress — is done by `scripts/quiz.py`. Your job is the
conversation: present what the script prints, pass the user's letter back to
it, and teach from the explanations it returns.

Run the script as `python3 <this skill's folder>/scripts/quiz.py <command>`.

## Why the script, not you, touches the bank

`data/questions.json` contains every answer and explanation. If you open it or
print a question yourself, the answer is in your context and tends to leak
into what you say ("Great question about general problem solvers…"). The
script prints only the stem and options, and reveals the answer only inside
`answer`. So don't read `questions.json`, the session files or `progress.json`
directly during a quiz, and never guess at an answer before the script grades
it.

Likewise, only ask questions the script gives you, and cite the question id it
prints. Made-up questions would mean studying something the instructor never
wrote. If the user explicitly asks for extra generated practice, label it
clearly as generated and do not record it as progress.

## First run: setup (ask, don't assume)

Start every session with `status`. If it says `READY: no`, ask the user — don't
pick a location for them, and never hard-code a path into this skill:

- **Where should your progress folder live?** It must be outside any git
  repository, including the one this skill lives in, so their score history is
  never committed or pushed. Suggest something like `~/ai1010-self-test`, but
  let them choose.
- **Where is the AI 1010 question bank?** If they already cloned
  `vanderbilt-ai-studies/ai1010-question-bank`, use that folder. If not, ask
  where they'd like it (outside this skill's repository, e.g.
  `~/Documents/ai1010-question-bank`) and add `--clone`.

Then run:

```bash
python3 <skill>/scripts/quiz.py setup --progress-dir "<their answer>" --bank-dir "<bank folder>" [--clone]
```

`setup` refuses a progress folder inside a repository or inside the bank, and
saves both locations to a small config file in the user's own config folder
(`~/.config/ginaharjani-quizmaster/config.json`), so you only ask once. If it
refuses, explain why in plain words and ask for another folder.

## Keeping the bank current

New questions are added to the bank after each quiz closes. At the start of a
session run `update`, which does a fast-forward `git pull` of the user's local
copy. It never pushes and never changes the course's repository. If it fails
(offline, or the user edited files in the bank folder), carry on with the copy
on disk and mention it briefly. The script re-reads the bank on every command,
so newly pulled questions appear immediately; progress is stored by question
id, which never changes, so history stays correct as the bank grows.

## Running a session

1. `status`, then `update` (see above).
2. Start: `start` gives 10 questions. Most of each session is reserved for
   weak concepts (concepts the user has missed and not yet mastered): at least
   70%, raised so every weak concept gets a question, while 2 slots are always
   left for untried concepts. These slots are filled before untried concepts
   are considered, so the 50+ untried concepts can't crowd out weak ones.
   - If the user names a concept ("quiz me on attention"), run `concepts` to
     find the matching id(s) and use `start --concept <id> [<id> ...]`.
   - If they want a different length, use `--count N`.
   The output starts with a `SESSION <id>` line — remember that id — and then
   the first question.
3. **Show the question** exactly as printed: question number, concept, stem
   and lettered options. Then stop and wait for the user. Add nothing that
   hints at the answer.
4. When the user replies, map their reply to a letter (they may type the
   letter, or the option text — match it to the printed options; if it is
   ambiguous, ask). Run `answer --session <id> --choice <letter>`.
5. **Teach from the result.** Say clearly whether they were right, give the
   correct answer, and explain it using the feedback the script printed. If
   they missed it, lead with why their choice was tempting and what
   distinction they missed, so they understand the mistake rather than just
   hearing "wrong". Keep it short: a few sentences, in your own words, faithful
   to the bank's explanation.
6. Run `next --session <id>` for the next question and repeat from step 3.
   When it prints `SESSION COMPLETE`, go to the summary.
7. **Summary:** run `summary --session <id>` and report the score, the
   concepts they did well on, the ones needing more practice, and their
   weakest concepts overall (these get priority next time). One or two
   sentences of encouragement or a suggestion is plenty.

If the user stops partway, their answers so far are already saved; offer the
summary for what they answered. If they want to resume later, `next` on the
same session id continues where they left off.

## Other requests

- "What am I weakest at?" / "how am I doing?" → `weakest`.
- "What concepts are there?" → `concepts`.
- "Update the questions" → `update`, then `status` to show the new count.
- "Move my progress folder" → ask for the new folder, then `setup --progress-dir`
  with it (the bank location is kept). Tell them to move their existing
  `progress.json` and `sessions/` into the new folder if they want to keep their
  history.

## Question types

The bank format allows ten question types, but this skill supports multiple
choice, which is all the bank contains today (as the design decided). The
script skips any other type, so new types in a future pull won't break a
session; they simply won't be asked until the skill is extended.
