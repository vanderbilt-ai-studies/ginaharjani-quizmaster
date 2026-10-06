# ginaharjani-quizmaster

A personal self-quiz skill for **AI 1010** (Vanderbilt's *Survey of Generative
AI Tools and Applications*). It quizzes you with multiple-choice questions from
the AI 1010 question bank and steers each practice session toward the concepts
you keep getting wrong.

## What it does and why you would use it

Rereading notes does not tell you what you have not learned yet. This skill
does:

- **Runs 10-question practice sessions** using only real questions from the
  AI 1010 question bank. Each question shows its id, so you can look it up.
- **Hides the answer until you reply.** You see the question and the lettered
  options, nothing else. The options are shuffled each time, so the position
  of the right answer is no clue.
- **Explains every answer.** After you reply, it tells you whether you were
  right, shows the correct answer and why it is correct. If you missed it, it
  explains why your choice was tempting but wrong.
- **Remembers how you did.** Every answer is saved to a progress file on your
  computer, so your history carries over from one session to the next.
- **Targets your weakest concepts.** At least 70% of each session goes to
  concepts you have missed and not yet mastered. Two slots are kept for
  concepts you have not tried yet, so new weak spots get discovered. Questions
  you missed come back sooner; questions you keep getting right come back
  less often.
- **Summarizes each session:** your score, the concepts you did well on, the
  ones that need more practice, and your weakest concepts overall.

The skill's design goals are in [`DESIGN.md`](DESIGN.md).

## What is in this repository

| Path | What it is |
|---|---|
| `ginaharjani-quizmaster/SKILL.md` | The skill's instructions for Claude. This folder is the skill you install. |
| `ginaharjani-quizmaster/scripts/quiz.py` | The quiz engine: finds the files, picks questions, grades answers and saves progress. |
| `ginaharjani-quizmaster/scripts/test_selection.py` | Automated tests for how questions are chosen. |
| `DESIGN.md` | The design and acceptance criteria for the skill. |

The question bank and your progress are **not** in this repository (see below).

## Requirements

- **Claude Code**, either the **Code tab in the Claude Desktop app** or the
  `claude` command-line tool.
- **A local session** on your own computer. The skill runs a Python script that
  reads the question bank from your disk, writes your progress to your disk,
  and runs `git`. A cloud session or plain Claude chat cannot reach those
  files.
- **Python 3.** The script uses only Python's standard library, so there is
  nothing extra to install. It has been run with Python 3.9.
- **Git.** The skill uses it to download the question bank and to pull new
  questions.
- **Access to the AI 1010 question bank** on GitHub:
  [`vanderbilt-ai-studies/ai1010-question-bank`](https://github.com/vanderbilt-ai-studies/ai1010-question-bank).
  Access comes through the course.
- **Access to this skill's GitHub repository:**
  [`vanderbilt-ai-studies/ginaharjani-quizmaster`](https://github.com/vanderbilt-ai-studies/ginaharjani-quizmaster).
  This repository is private, so your GitHub account needs to have been given
  access to it.
- **An internet connection** for the first download and for updates. Quizzing
  itself works offline once the bank is on your computer.

## Installation and first use

### Step 1: Get the skill from GitHub

Clone this repository with GitHub Desktop (**File → Clone repository →**
`vanderbilt-ai-studies/ginaharjani-quizmaster`) or on the command line:

```bash
git clone https://github.com/vanderbilt-ai-studies/ginaharjani-quizmaster.git
```

### Step 2: Install the skill folder

The skill is the **`ginaharjani-quizmaster/` folder inside the repository**,
the one that contains `SKILL.md`. Install that folder, not the whole
repository.

For Claude Code, personal skills live in the `.claude/skills` folder in your
home folder. From the folder where you cloned the repository, run:

```bash
mkdir -p ~/.claude/skills
```

```bash
cp -R ginaharjani-quizmaster/ginaharjani-quizmaster ~/.claude/skills/
```

You can also ask Claude Code to do this for you: *"Install the skill folder
`ginaharjani-quizmaster` from the repository I just cloned into my personal
Claude Code skills."*

Start a new Claude Code session afterwards so the skill is picked up.

### Step 3: First run — choose where things live

Ask Claude something like **"quiz me"**. The first time, the skill sees it is
not set up yet and asks you two questions. It never picks these locations for
you.

1. **Where should your progress folder live?** Choose any folder that is
   *outside* every git repository, for example a new folder in your home
   folder such as `~/ai1010-self-test`. (Why: see
   [Where your progress is stored](#where-your-progress-is-stored).)
2. **Where is the AI 1010 question bank?**
   - If you already cloned `ai1010-question-bank`, give that folder.
   - If not, tell Claude where you would like it (somewhere outside this
     skill's repository) and the skill downloads it there with `git clone`.

The skill checks your answers. It refuses a progress folder that is inside a
git repository (including this one or the question bank), and a question
bank folder inside this skill's repository. If it refuses, pick another
folder.

Your two choices are saved in a small settings file,
`~/.config/ginaharjani-quizmaster/config.json`, so you are only asked once. To
move your progress later, ask *"move my progress folder"*. The skill will ask
for the new location; move your existing `progress.json` and `sessions/`
folder into it yourself if you want to keep your history.

### Step 4: Take your first session

Your first session has no history to work from, so it samples across concepts
to find your weak spots. Answer each question with a letter (A, B, C…) or the
option's text. After 10 questions you get a summary. From the second session
on, practice focuses on the concepts you missed.

If you stop partway, the answers you gave are already saved.

## How the question bank gets updates

New questions are added to the AI 1010 question bank after each quiz closes.

- At the start of each session the skill runs a **`git pull`** on your local
  copy of the bank (fast-forward only). It only downloads; it never pushes or
  changes the course's repository.
- If the update fails (for example you are offline, or you edited files inside
  the bank folder), the skill carries on with the copy already on your
  computer and tells you.
- The skill **re-reads the bank every time**, so newly pulled questions show up
  right away.
- Progress is saved by **question id**, and ids never change, so your history
  stays correct as the bank grows.

You can also ask for an update at any time: *"update the question bank"*.

## Example requests

Type any of these in Claude Code:

1. **"Quiz me."** Starts a 10-question session focused on your weakest
   concepts.
2. **"Quiz me on attention."** Starts a session limited to one concept,
   favoring questions you missed before.
3. **"What am I weakest at?"** Shows your concepts ranked from weakest to
   strongest, based on your saved history.

Other things it understands: *"let's practice"*, *"drill my weak spots"*,
*"what concepts are there?"*, *"update the question bank"*, and a different
session length, such as *"give me 5 questions"*.

## Where your progress is stored

Your progress lives in the **progress folder you chose during setup**, not in
this repository. It contains:

- `progress.json`: every question you have answered, when, and whether you
  were right, stored by question id.
- `sessions/`: one file per practice session.

It is kept outside the repository on purpose:

- **Your score history is private.** If it were inside this repository, it
  could be committed and pushed to GitHub by accident. The skill refuses any
  progress folder inside a git repository.
- **It is kept out of the question bank folder too.** `git pull` updates that
  folder, and files you add there can get in the way of updates (the
  question bank's own guide gives the same advice).
- **It survives reinstalling the skill.** You can delete, re-clone or update
  the skill without losing your history.

## How the skill was tested

The tests check the three acceptance criteria in [`DESIGN.md`](DESIGN.md):
the answer is never revealed before you respond, answers get explanations, and
the weakest concepts are prioritized.

**1. Automated tests for question selection.** `scripts/test_selection.py`
builds a made-up question bank (6 "weak" concepts plus 55 untried ones), so it
needs no network and never touches real progress. Each test runs across 200
random seeds where relevant:

- at least 7 of every 10 questions target weak concepts;
- the weakest concepts appear in every session and are not crowded out by the
  many untried concepts;
- at least 2 slots are still left for untried concepts;
- a brand-new user with no history still gets a full 10-question session.

Run them from the `scripts` folder:

```bash
python3 test_selection.py
```

**2. Setup and safety checks.** The `setup` command was run with a separate
test settings folder and confirmed to:

- report "not ready" and ask for locations before first use;
- refuse a progress folder inside the skill's repository;
- refuse a progress folder inside the question bank (or any git repository);
- accept a folder outside any repository and save the settings.

**3. No-answer check.** A session was started and the printed question
checked: it shows only the question, the concept and the shuffled options.
None of the answer explanations appear before an answer is given.

**4. Real practice sessions.** The skill was used for four real practice
sessions against the live question bank. The progress file was opened
afterwards to confirm that all 20 answers were recorded by question id, and
the session files to confirm each session's questions and choices were saved.

## Limitations

- **Multiple choice only (for this lab).** The question-bank format allows ten
  question types (true or false, multi-select, short answer, matching,
  ordering and others), but this version supports only multiple choice, which
  is all the bank contains today. Questions of other types are skipped, so new
  types will not break a session, but they will not be asked until the skill
  is extended.
- **Needs a local Claude Code session.** It does not work in plain Claude chat
  or a cloud session, because it reads and writes files on your computer.
- **Needs Python 3 and Git** installed on your computer.
- **The first session is general.** With no history yet, the first session
  samples across concepts rather than targeting weak spots.
- **Moving your progress folder is partly manual.** The skill updates the
  setting, but you move the existing files yourself.
- **Explanations come from the bank.** Claude rephrases the bank's own
  explanations; it does not make up questions. If you ask for extra generated
  practice, it is labeled as generated and not saved to your progress.
- **This is practice, not the real quiz.** The graded AI 1010 pre-class
  quizzes still have their own rule: no generative AI while taking them.
