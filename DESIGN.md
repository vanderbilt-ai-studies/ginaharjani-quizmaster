# Design

The goal of my skill is to help me practice the topics and concepts that I am weakest in. The skill will keep track of my performance over time and use that information to decide which questions I should see next. This will make the practice more personalized because I will spend more time on concepts that I consistently get wrong.

I will practice questions from the AI1010 question bank. The main focus will be on my weakest concepts. Each question will be connected to a specific concept or topic in the question bank. After I answer a question, the skill will record whether I answered it correctly or incorrectly. Questions that I get wrong will receive a higher priority for future practice.

A practice session will consist of 10 multiple-choice questions. At the beginning of a session, the skill will look at my saved progress and identify the concepts where I have performed the weakest. It will then select questions that target those concepts. At the end of the session, the skill will give me a short summary of how I performed, including which concepts I did well on and which concepts still need more practice.

The answer will not be shown in the question itself. I should be able to read the question and answer choices without seeing the correct answer first. After I submit my answer, the skill will reveal whether my answer was correct and then show the correct answer. It will also provide a short explanation of why the correct answer is correct. If I chose the wrong answer, the explanation should help me understand my mistake instead of simply telling me that I was wrong.

The AI1010 question format supports ten different question types. For this lab, I will specifically support multiple-choice questions, since those are the questions currently available in the question bank.

I will use the following acceptance criteria to test the skill:

- The answer is never revealed before I respond.
- Correct answers receive explanations.
- The skill prioritizes my weakest concepts.
