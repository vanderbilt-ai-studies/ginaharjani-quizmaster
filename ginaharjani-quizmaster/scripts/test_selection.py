#!/usr/bin/env python3
"""Regression test: weak concepts must not be crowded out by untried ones.

Run with: python3 scripts/test_selection.py
Uses a synthetic bank, so it needs no network and never reads real answers.
"""

import random
import unittest

import quiz

WEAK = ["tokenization", "attention", "token-embedding", "model-selection",
        "github-issues", "sampling-and-temperature"]
UNTRIED = ["untried-%02d" % i for i in range(55)]


def make_bank():
    questions = {}
    for c in WEAK + UNTRIED:
        for n in range(6):
            qid = "%s-%d" % (c, n)
            questions[qid] = {"id": qid, "type": "MC", "concepts": [c]}
    return questions


def make_progress(questions):
    """One miss on the first question of each weak concept."""
    prog = {"version": 1, "questions": {}}
    for c in WEAK:
        qid = "%s-0" % c
        prog["questions"][qid] = {"concepts": [c], "attempts": [
            {"at": "2026-10-06T10:00:00", "correct": False, "chose": "x", "session": "t"}]}
    return prog


class WeakConceptPriority(unittest.TestCase):
    def setUp(self):
        self.questions = make_bank()
        self.progress = make_progress(self.questions)

    def test_most_of_each_session_is_weak_concepts(self):
        for seed in range(200):
            picked, _ = quiz.choose_questions(self.questions, self.progress, 10,
                                              rng=random.Random(seed))
            n_weak = sum(1 for q in picked if set(WEAK) & set(q["concepts"]))
            self.assertGreaterEqual(n_weak, 7, "seed %d: only %d weak" % (seed, n_weak))

    def test_every_weak_concept_appears_every_session(self):
        for seed in range(200):
            picked, _ = quiz.choose_questions(self.questions, self.progress, 10,
                                              rng=random.Random(seed))
            seen = {c for q in picked for c in q["concepts"]}
            for c in ("tokenization", "attention"):
                self.assertIn(c, seen, "seed %d: %s crowded out" % (seed, c))

    def test_exploration_slots_remain(self):
        picked, _ = quiz.choose_questions(self.questions, self.progress, 10,
                                          rng=random.Random(0))
        n_untried = sum(1 for q in picked if q["concepts"][0] in UNTRIED)
        self.assertGreaterEqual(n_untried, quiz.MIN_EXPLORE)

    def test_no_history_still_fills_session(self):
        empty = {"version": 1, "questions": {}}
        picked, _ = quiz.choose_questions(self.questions, empty, 10,
                                          rng=random.Random(0))
        self.assertEqual(len(picked), 10)


if __name__ == "__main__":
    unittest.main()
