#!/usr/bin/env python3
"""Self-quiz engine for the AI 1010 question bank.

Handles the parts that must be exact: where things live, which questions to
ask, grading, and recording progress. The model handles the conversation.

Questions are printed WITHOUT their answers. The answer and explanations are
only printed by `answer`, after the user has replied.

Commands:
  status                         Show configuration and whether it is ready.
  setup --progress-dir DIR [--bank-dir DIR] [--clone]
                                 Save where progress lives and where the bank is.
  update                         git pull the local question bank (fast-forward only).
  start [--count N] [--concept ID ...]
                                 Start a session targeting the weakest concepts.
  next --session ID              Print the next unanswered question (no answer).
  answer --session ID --choice LETTER
                                 Grade the current question, record it, explain.
  summary --session ID           Session score, concepts done well / needing work.
  weakest [--top N]              Overall concept mastery from saved history.
  concepts                       List concept ids and labels.

Locations are never hard-coded. They come from (highest priority first):
  environment variables QUIZMASTER_PROGRESS_DIR / QUIZMASTER_BANK_DIR,
  then the config file written by `setup`, at
  $XDG_CONFIG_HOME/ginaharjani-quizmaster/config.json
  (default ~/.config/ginaharjani-quizmaster/config.json).
"""

import argparse
import datetime as dt
import json
import os
import random
import subprocess
import sys
import uuid
from pathlib import Path

BANK_REPO_URL = "https://github.com/vanderbilt-ai-studies/ai1010-question-bank.git"
SKILL_DIR = Path(__file__).resolve().parent.parent
SUPPORTED_TYPES = {"MC"}  # DESIGN.md: this skill supports multiple choice
DEFAULT_COUNT = 10
MAX_PER_CONCEPT = 4  # keep a session from becoming one concept over and over
FOCUS_SHARE = 0.7    # minimum share of a session reserved for weak concepts
MIN_EXPLORE = 2      # slots always left for untried concepts (when count allows)
FOCUS_CONCEPTS = 3   # how many of the weakest concepts to name in messages
WEAK_MASTERY = 0.6   # below this smoothed accuracy, a missed concept counts as weak
RECENT_WINDOW = 10   # mastery uses each concept's last N answers
LETTERS = "ABCDEFGHIJ"


# ---------------------------------------------------------------- config

def config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "ginaharjani-quizmaster" / "config.json"


def load_config():
    cfg = {}
    p = config_path()
    if p.exists():
        try:
            cfg = json.loads(p.read_text())
        except ValueError:
            cfg = {}
    if os.environ.get("QUIZMASTER_PROGRESS_DIR"):
        cfg["progress_dir"] = os.environ["QUIZMASTER_PROGRESS_DIR"]
    if os.environ.get("QUIZMASTER_BANK_DIR"):
        cfg["bank_dir"] = os.environ["QUIZMASTER_BANK_DIR"]
    return cfg


def expand(path_str):
    return Path(os.path.expandvars(path_str)).expanduser().resolve()


def git_toplevel(path):
    """Return the git repository root containing `path`, or None."""
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        out = subprocess.run(
            ["git", "-C", str(probe), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        return Path(out.stdout.strip()).resolve()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def is_within(child, parent):
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def die(msg, code=1):
    print("ERROR: " + msg)
    sys.exit(code)


def require_config():
    cfg = load_config()
    missing = [k for k in ("progress_dir", "bank_dir") if not cfg.get(k)]
    if missing:
        die("not set up yet (missing %s). Ask the user where they want their "
            "progress folder and where the question bank is (or should be "
            "cloned), then run `setup`." % ", ".join(missing), code=2)
    return expand(cfg["progress_dir"]), expand(cfg["bank_dir"])


# ---------------------------------------------------------------- data

def load_bank(bank_dir):
    """Re-read the bank every time so newly pulled questions appear."""
    f = bank_dir / "data" / "questions.json"
    if not f.exists():
        die("question bank not found at %s (expected data/questions.json). "
            "Run `setup --bank-dir ... --clone` or fix the path." % bank_dir)
    data = json.loads(f.read_text())
    concepts = {c["id"]: c for c in data.get("concepts", [])}
    questions = {q["id"]: q for q in data.get("questions", [])}
    return questions, concepts


def progress_file(progress_dir):
    return progress_dir / "progress.json"


def load_progress(progress_dir):
    f = progress_file(progress_dir)
    if f.exists():
        return json.loads(f.read_text())
    return {"version": 1, "questions": {}}


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    tmp.replace(path)


def session_path(progress_dir, sid):
    return progress_dir / "sessions" / ("%s.json" % sid)


def load_session(progress_dir, sid):
    p = session_path(progress_dir, sid)
    if not p.exists():
        die("no session %s" % sid)
    return json.loads(p.read_text())


def now_iso():
    return dt.datetime.now().astimezone().isoformat(timespec="milliseconds")


# ---------------------------------------------------------------- stats

def concept_stats(progress, questions):
    """Per concept: all-time attempts/correct, plus the most recent answers.

    Every concept a question tests gets credit (or blame) for it.
    """
    history = {}
    for qid, rec in progress["questions"].items():
        q = questions.get(qid)
        tags = q["concepts"] if q else rec.get("concepts", [])
        for a in rec.get("attempts", []):
            for c in tags:
                history.setdefault(c, []).append((a["at"], a["correct"]))
    stats = {}
    for c, h in history.items():
        h.sort(key=lambda t: t[0])
        recent = [ok for _, ok in h[-RECENT_WINDOW:]]
        stats[c] = {"attempts": len(h), "correct": sum(1 for _, ok in h if ok),
                    "recent": recent}
    return stats


def describe(stat):
    r = stat["recent"]
    text = "%d/%d right recently" % (sum(r), len(r))
    if stat["attempts"] > len(r):
        text += ", %d/%d all-time" % (stat["correct"], stat["attempts"])
    return text


def mastery(stat):
    """Smoothed accuracy over the recent answers, so improvement counts fast.

    An unseen concept sits at 0.5, not 0 or 1.
    """
    if not stat:
        return 0.5
    recent = stat["recent"]
    return (sum(recent) + 1.0) / (len(recent) + 2.0)


def question_weight(q, stats, progress):
    """Higher weight = more likely to be picked."""
    tags = q["concepts"] or []
    # The first tag is the most central one; let it count double.
    weights = [2.0] + [1.0] * (len(tags) - 1)
    weakness = sum(w * (1.0 - mastery(stats.get(c))) for w, c in zip(weights, tags))
    weakness /= max(sum(weights), 1.0)
    w = weakness ** 2 + 0.01  # sharpen toward the weakest concepts

    attempts = progress["questions"].get(q["id"], {}).get("attempts", [])
    if attempts:
        if not attempts[-1]["correct"]:
            w *= 4.0  # missed last time: bring it back soon
        else:
            streak = 0
            for a in reversed(attempts):
                if not a["correct"]:
                    break
                streak += 1
            w *= 0.4 ** streak  # each correct answer in a row makes it rarer
    return w


def weak_concepts(stats, rng=None):
    """Concepts the user has missed and not yet mastered, weakest first.

    With `rng`, exact ties are broken randomly so tied concepts take turns
    across sessions instead of the same one always winning.
    """
    weak = [c for c, s in stats.items()
            if not all(s["recent"]) and mastery(s) < WEAK_MASTERY]
    tiebreak = {c: (rng.random() if rng else 0.0) for c in weak}
    return sorted(weak, key=lambda c: (mastery(stats[c]), -stats[c]["attempts"],
                                       tiebreak[c], c))


def weighted_pick(weighted, rng):
    """Pop one (question, weight) pair, chosen in proportion to weight."""
    total = sum(w for _, w in weighted)
    r = rng.uniform(0, total)
    acc = 0.0
    for i, (_, w) in enumerate(weighted):
        acc += w
        if acc >= r:
            return weighted.pop(i)[0]
    return weighted.pop()[0]


def focus_slot_count(count, n_weak):
    """How many slots to reserve for weak concepts.

    At least FOCUS_SHARE of the session, raised so each weak concept can get a
    question, but never so high that untried concepts lose their last
    MIN_EXPLORE slots. Untried concepts are many (50+), so if weak concepts
    had to compete with them in the open pool they would rarely be drawn.
    """
    if n_weak == 0:
        return 0
    base = int(round(count * FOCUS_SHARE))
    ceiling = max(base, count - MIN_EXPLORE)
    return min(count, max(base, min(n_weak, ceiling)))


def choose_questions(questions, progress, count, only_concepts=None, rng=None):
    """Most of the session is reserved for the weakest concepts; the rest explores.

    Focus slots go to every weak concept (not just the top few), round-robin,
    weakest first, and are filled before untried concepts are considered. A
    question counts toward each weak concept it tests. The remaining slots
    are sampled across the whole bank so untried concepts get discovered.
    """
    rng = rng or random.Random()
    stats = concept_stats(progress, questions)
    pool = [q for q in questions.values() if q["type"] in SUPPORTED_TYPES]
    if only_concepts:
        wanted = set(only_concepts)
        pool = [q for q in pool if wanted.intersection(q["concepts"])]
    weight = {q["id"]: question_weight(q, stats, progress) for q in pool}

    picked, used = [], set()

    def take(q):
        picked.append(q)
        used.add(q["id"])

    # 1. Focus slots, reserved up front: all weak concepts, round-robin,
    #    weakest first. Each pass gives a question to every weak concept that
    #    has had the fewest so far, so the weakest are covered before any
    #    concept gets a second question.
    weak = [c for c in weak_concepts(stats, rng)
            if not only_concepts or c in only_concepts]
    focus_slots = focus_slot_count(count, len(weak))
    covered = {c: 0 for c in weak}
    active = list(weak)
    while focus_slots and active:
        for c in list(active):
            if focus_slots == 0:
                break
            if covered[c] >= MAX_PER_CONCEPT:
                active.remove(c)
                continue
            if covered[c] > min(covered[a] for a in active):
                continue  # already covered by an earlier pick this pass
            cands = [(q, weight[q["id"]]) for q in pool
                     if c in q["concepts"] and q["id"] not in used]
            if not cands:
                active.remove(c)
                continue
            q = weighted_pick(cands, rng)
            take(q)
            for t in q["concepts"]:
                if t in covered:
                    covered[t] += 1
            focus_slots -= 1

    # 2. Remaining slots: weighted sample of everything else, capped per
    #    primary concept so one topic doesn't swallow the session.
    rest = [(q, weight[q["id"]]) for q in pool if q["id"] not in used]
    per_concept = {}
    for q in picked:
        p = q["concepts"][0] if q["concepts"] else None
        per_concept[p] = per_concept.get(p, 0) + 1
    cap = count if only_concepts else MAX_PER_CONCEPT
    while rest and len(picked) < count:
        q = weighted_pick(rest, rng)
        primary = q["concepts"][0] if q["concepts"] else None
        if per_concept.get(primary, 0) >= cap:
            continue
        per_concept[primary] = per_concept.get(primary, 0) + 1
        take(q)

    rng.shuffle(picked)  # don't front-load the hard ones
    return picked, stats


# ---------------------------------------------------------------- output

def label(concepts, cid):
    c = concepts.get(cid)
    return c["label"] if c else cid


def print_question(sess, idx, questions, concepts):
    item = sess["items"][idx]
    q = questions.get(item["id"])
    if q is None:
        die("question %s is no longer in the bank" % item["id"])
    print("QUESTION %d of %d   [id: %s]" % (idx + 1, len(sess["items"]), q["id"]))
    print("Concept: " + ", ".join(label(concepts, c) for c in q["concepts"]))
    print()
    print(q["question"])
    print()
    for letter, opt_i in zip(LETTERS, item["order"]):
        print("  %s) %s" % (letter, q["options"][opt_i]["text"]))
    print()
    print("(Answer with a letter %s-%s. The answer is not shown until you reply.)"
          % (LETTERS[0], LETTERS[len(item["order"]) - 1]))


# ---------------------------------------------------------------- commands

def cmd_status(args):
    cfg = load_config()
    print("Config file: %s (%s)" % (config_path(),
                                     "exists" if config_path().exists() else "not created"))
    ok = True
    for key in ("progress_dir", "bank_dir"):
        val = cfg.get(key)
        print("%s: %s" % (key, val or "NOT SET"))
        ok = ok and bool(val)
    if not ok:
        print("READY: no -- ask the user where to keep progress (outside any "
              "repository) and where the question bank is, then run setup.")
        return
    progress_dir, bank_dir = expand(cfg["progress_dir"]), expand(cfg["bank_dir"])
    bank_ok = (bank_dir / "data" / "questions.json").exists()
    print("bank found: %s" % ("yes" if bank_ok else "NO"))
    if bank_ok:
        questions, concepts = load_bank(bank_dir)
        mc = sum(1 for q in questions.values() if q["type"] in SUPPORTED_TYPES)
        newest = max((q["date"] for q in questions.values()), default="-")
        print("questions: %d (%d multiple choice), newest dated %s"
              % (len(questions), mc, newest))
    prog = load_progress(progress_dir)
    answered = sum(len(r.get("attempts", [])) for r in prog["questions"].values())
    print("answers recorded: %d" % answered)
    print("READY: %s" % ("yes" if bank_ok else "no -- bank missing"))


def cmd_setup(args):
    cfg = {}
    if config_path().exists():
        try:
            cfg = json.loads(config_path().read_text())
        except ValueError:
            cfg = {}

    progress_dir = expand(args.progress_dir)
    skill_repo = git_toplevel(SKILL_DIR)
    if skill_repo and is_within(progress_dir, skill_repo):
        die("%s is inside the skill's repository (%s). Progress must live "
            "outside it so your history never gets committed. Choose another "
            "folder." % (progress_dir, skill_repo))
    target_repo = git_toplevel(progress_dir)
    if target_repo:
        die("%s is inside a git repository (%s). Choose a folder outside any "
            "repository, such as one in your home folder." % (progress_dir, target_repo))

    if args.bank_dir:
        bank_dir = expand(args.bank_dir)
    elif cfg.get("bank_dir"):
        bank_dir = expand(cfg["bank_dir"])
    else:
        die("--bank-dir is required the first time.")
    if is_within(progress_dir, bank_dir):
        die("progress must not be inside the question bank folder: git pulls "
            "update that folder and your files could get in the way.")
    if skill_repo and is_within(bank_dir, skill_repo):
        die("put the question bank outside this skill's repository (%s), not "
            "inside it." % skill_repo)

    if not (bank_dir / "data" / "questions.json").exists():
        if args.clone:
            if bank_dir.exists() and any(bank_dir.iterdir()):
                die("%s exists and is not empty; cannot clone into it." % bank_dir)
            bank_dir.parent.mkdir(parents=True, exist_ok=True)
            r = subprocess.run(["git", "clone", BANK_REPO_URL, str(bank_dir)])
            if r.returncode != 0:
                die("git clone failed.")
        else:
            die("no question bank at %s. Re-run with --clone to download it "
                "there, or give the folder where you already cloned it." % bank_dir)

    progress_dir.mkdir(parents=True, exist_ok=True)
    cfg.update({"progress_dir": str(progress_dir), "bank_dir": str(bank_dir)})
    save_json(config_path(), cfg)
    print("Saved config to %s" % config_path())
    print("progress_dir: %s" % progress_dir)
    print("bank_dir: %s" % bank_dir)


def cmd_update(args):
    _, bank_dir = require_config()
    r = subprocess.run(["git", "-C", str(bank_dir), "pull", "--ff-only"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("Could not update the question bank (offline, or local changes "
              "in the bank folder). Continuing with the copy on disk.")
        print(r.stderr.strip())
        return
    print(r.stdout.strip() or "Question bank is up to date.")


def cmd_start(args):
    progress_dir, bank_dir = require_config()
    questions, concepts = load_bank(bank_dir)
    progress = load_progress(progress_dir)
    if args.concept:
        unknown = [c for c in args.concept if c not in concepts]
        if unknown:
            die("unknown concept id(s): %s. Run `concepts` to list them."
                % ", ".join(unknown))
    picked, stats = choose_questions(questions, progress, args.count, args.concept)
    if not picked:
        die("no multiple-choice questions match that request.")

    rng = random.Random()
    items = []
    for q in picked:
        order = list(range(len(q["options"])))
        rng.shuffle(order)  # so the right answer's position is no clue
        items.append({"id": q["id"], "order": order, "choice": None, "correct": None})
    sid = dt.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    sess = {"id": sid, "started": now_iso(), "concept_filter": args.concept or [],
            "items": items}
    save_json(session_path(progress_dir, sid), sess)

    print("SESSION %s  (%d questions)" % (sid, len(items)))
    ranked = weak_concepts(stats)[:FOCUS_CONCEPTS]
    if args.concept:
        print("Concept(s): " + ", ".join(label(concepts, c) for c in args.concept)
              + " (favoring questions you missed before).")
    elif ranked:
        print("Targeting weakest concepts: " + "; ".join(
            "%s (%s)" % (label(concepts, c), describe(stats[c])) for c in ranked))
    elif any(s["attempts"] for s in stats.values()):
        print("No weak concepts right now: sampling across concepts to find "
              "new weak spots.")
    else:
        print("No history yet: this first session samples across concepts to "
              "find your weak spots.")
    print()
    print_question(sess, 0, questions, concepts)


def current_index(sess):
    for i, item in enumerate(sess["items"]):
        if item["choice"] is None:
            return i
    return None


def cmd_next(args):
    progress_dir, bank_dir = require_config()
    questions, concepts = load_bank(bank_dir)
    sess = load_session(progress_dir, args.session)
    i = current_index(sess)
    if i is None:
        print("SESSION COMPLETE -- run `summary --session %s`." % sess["id"])
        return
    print_question(sess, i, questions, concepts)


def cmd_answer(args):
    progress_dir, bank_dir = require_config()
    questions, concepts = load_bank(bank_dir)
    sess = load_session(progress_dir, args.session)
    i = current_index(sess)
    if i is None:
        die("this session is already complete.")
    item = sess["items"][i]
    q = questions[item["id"]]
    letters = LETTERS[:len(item["order"])]
    choice = args.choice.strip().upper().rstrip(").")
    if len(choice) != 1 or choice not in letters:
        die("answer must be one of %s; nothing was recorded." % ", ".join(letters))

    chosen_opt = q["options"][item["order"][letters.index(choice)]]
    correct_pos = next(k for k, oi in enumerate(item["order"])
                       if q["options"][oi].get("correct") or q["options"][oi].get("weight") == 100)
    correct_letter = letters[correct_pos]
    correct_opt = q["options"][item["order"][correct_pos]]
    is_right = choice == correct_letter

    item["choice"], item["correct"] = choice, is_right
    save_json(session_path(progress_dir, sess["id"]), sess)

    progress = load_progress(progress_dir)
    rec = progress["questions"].setdefault(q["id"], {"concepts": q["concepts"], "attempts": []})
    rec["concepts"] = q["concepts"]
    rec["attempts"].append({"at": now_iso(), "correct": is_right,
                            "chose": chosen_opt["text"], "session": sess["id"]})
    save_json(progress_file(progress_dir), progress)

    print("RESULT: %s" % ("CORRECT" if is_right else "INCORRECT"))
    print("You chose: %s) %s" % (choice, chosen_opt["text"]))
    if not is_right:
        print("Why that is tempting but wrong: %s" % chosen_opt["feedback"])
        print()
    print("Correct answer: %s) %s" % (correct_letter, correct_opt["text"]))
    print("Why it is correct: %s" % correct_opt["feedback"])
    print("[question id: %s]" % q["id"])
    remaining = sum(1 for it in sess["items"] if it["choice"] is None)
    print()
    print("Progress saved. %d question(s) left in this session." % remaining)


def cmd_summary(args):
    progress_dir, bank_dir = require_config()
    questions, concepts = load_bank(bank_dir)
    sess = load_session(progress_dir, args.session)
    done = [it for it in sess["items"] if it["choice"] is not None]
    right = sum(1 for it in done if it["correct"])
    print("SESSION %s: %d / %d correct" % (sess["id"], right, len(done)))
    if len(done) < len(sess["items"]):
        print("(%d question(s) not answered)" % (len(sess["items"]) - len(done)))

    per = {}
    for it in done:
        q = questions.get(it["id"])
        for c in (q["concepts"] if q else []):
            s = per.setdefault(c, {"attempts": 0, "correct": 0})
            s["attempts"] += 1
            s["correct"] += 1 if it["correct"] else 0
    good = sorted([c for c, s in per.items() if s["correct"] == s["attempts"]],
                  key=lambda c: -per[c]["attempts"])
    work = sorted([c for c, s in per.items() if s["correct"] < s["attempts"]],
                  key=lambda c: per[c]["correct"] / per[c]["attempts"])
    print()
    print("Did well on:")
    for c in good or []:
        print("  - %s (%d/%d)" % (label(concepts, c), per[c]["correct"], per[c]["attempts"]))
    if not good:
        print("  (none this session)")
    print("Needs more practice:")
    for c in work:
        print("  - %s (%d/%d)" % (label(concepts, c), per[c]["correct"], per[c]["attempts"]))
    if not work:
        print("  (none this session)")

    stats = concept_stats(load_progress(progress_dir), questions)
    ranked = weak_concepts(stats)[:FOCUS_CONCEPTS]
    print()
    if ranked:
        print("Weakest concepts overall (these get priority next session):")
        for c in ranked:
            print("  - %s (%s)" % (label(concepts, c), describe(stats[c])))
    else:
        print("No weak concepts right now: next session explores new material.")


def cmd_weakest(args):
    progress_dir, bank_dir = require_config()
    questions, concepts = load_bank(bank_dir)
    stats = concept_stats(load_progress(progress_dir), questions)
    seen = sorted([c for c in stats if stats[c]["attempts"]], key=lambda c: mastery(stats[c]))
    if not seen:
        print("No answers recorded yet.")
        return
    weak = set(weak_concepts(stats))
    for c in seen[:args.top]:
        print("%-40s %s%s" % (label(concepts, c), describe(stats[c]),
                              "  <- weak" if c in weak else ""))
    untouched = len(concepts) - len(seen)
    if untouched > 0:
        print("%d concept(s) not practiced yet." % untouched)


def cmd_concepts(args):
    _, bank_dir = require_config()
    questions, concepts = load_bank(bank_dir)
    counts = {}
    for q in questions.values():
        if q["type"] in SUPPORTED_TYPES:
            for c in q["concepts"]:
                counts[c] = counts.get(c, 0) + 1
    for cid, c in concepts.items():
        print("%-32s %-40s %3d questions" % (cid, c["label"], counts.get(cid, 0)))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    s = sub.add_parser("setup")
    s.add_argument("--progress-dir", required=True)
    s.add_argument("--bank-dir")
    s.add_argument("--clone", action="store_true")
    sub.add_parser("update")
    s = sub.add_parser("start")
    s.add_argument("--count", type=int, default=DEFAULT_COUNT)
    s.add_argument("--concept", nargs="+")
    s = sub.add_parser("next")
    s.add_argument("--session", required=True)
    s = sub.add_parser("answer")
    s.add_argument("--session", required=True)
    s.add_argument("--choice", required=True)
    s = sub.add_parser("summary")
    s.add_argument("--session", required=True)
    s = sub.add_parser("weakest")
    s.add_argument("--top", type=int, default=10)
    sub.add_parser("concepts")
    args = p.parse_args(argv)
    {"status": cmd_status, "setup": cmd_setup, "update": cmd_update,
     "start": cmd_start, "next": cmd_next, "answer": cmd_answer,
     "summary": cmd_summary, "weakest": cmd_weakest,
     "concepts": cmd_concepts}[args.cmd](args)


if __name__ == "__main__":
    main()
