# Interview Guide

Use this file during the staged interview to extract the core argument,
audience context, and constraints before writing `talk_plan.md`.

## Interview Rounds

### Round 1: Talk Context

Ask one to three of these questions. Pick the most relevant first.

- What is the single most important thing you want the audience to
  remember after your talk?
- What type of talk is this: group meeting, conference, thesis defense,
  classroom lecture, invited seminar, or progress update?
- How much time do you have, and how much of that is Q&A?
- Who is the audience? Are they specialists in your sub-field, a broader
  materials-science group, or a mixed audience?

### Round 2: Core Argument and Evidence

After the user answers Round 1, ask:

- What evidence supports your main claim? Is it from your own
  calculations, experiments, published papers, or a combination?
- What is the strongest single result or figure that proves your point?
- What limitations or caveats should the audience know about?
- Is there a competing explanation or method that the audience might
  compare against?

### Round 3: Constraints and Preferences

Ask only what remains unresolved:

- Do you have a reference folder or specific papers you want to cite?
- Are there figures you already have that must be included?
- What language should the talk be in? (Default: Chinese unless the user
  explicitly requests English.)
- Are there slides from a previous version that should be revised rather
  than rebuilt?

## Rules

- Do not ask all questions at once. Ask in rounds of one to three.
- If the user provides a prior talk plan or project context, read it
  before interviewing and skip questions that are already answered.
- Mark any answer that is vague or unsupported as `pending` in the talk
  plan. Do not fabricate evidence or assume claims.
- If the user cannot articulate the core argument, help them by
  rephrasing their description into a declarative statement and asking
  for confirmation.
- Do not ask about slide layout, colors, fonts, or PPTX details. Those
  belong to `simple-sci-ppt`.

## Assumption Challenge

After the interview, challenge unsupported assumptions:

- If the user claims a result is `confirmed` but provides no source or
  completed calculation, downgrade to `preliminary` and flag it.
- If the user plans to include a figure that has not been generated yet,
  mark it `pending` in the material priority list.
- If the time budget does not fit the planned content, flag the
  overflow and ask the user to cut or compress.
