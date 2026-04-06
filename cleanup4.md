# cleanup4.md — Fix Agent Intelligence, Dedup Findings, Chat Actions, Story Narrative

## Problem 1: LLM follow-ups hallucinate column names and re-describe instead of investigate

The LLM reasoning module doesn't know what columns actually exist in the dataframe,
so it invents names like 'dtype:'. Follow-ups just re-summarize the same output
instead of testing new hypotheses.

### Fix:
- [x] Update `src/agent/reasoning.py` `decide_next_step()`:
  - Include ACTUAL column names in the system prompt (from state.columns)
  - Include actual dtypes (from state.dtypes)
  - Add explicit instruction: "Do NOT re-describe the data. Only write code that
    produces NEW analysis not yet done. If nothing new is needed, set follow_up=false."
  - Add: "Use ONLY column names from this list: {columns}. Do NOT invent column names."

- [x] Update `src/agent/eda_agent.py`:
  - Pass state.columns and state.dtypes to decide_next_step via state_summary
  - Cap findings: ONE finding per goal max (overwrite, don't append)
  - Only call interpret_output for the FIRST successful cell per goal, not follow-ups
  - Make follow-ups much rarer: only when the LLM sees something genuinely surprising

## Problem 2: Error recovery doesn't work — agent doesn't read the error

- [x] Update `src/agent/eda_agent.py` backtracking:
  - When a cell errors, pass the FULL error message + traceback to decide_next_step
  - Include the actual column list so the fix code uses real names
  - The backtrack prompt should be: "This code failed with: {error}. Available columns
    are: {columns}. Write corrected code."
  - Max 2 fix attempts per error, then skip the goal

## Problem 3: Findings duplicated in notebook summary, chat completion, and story

- [x] Update `src/agent/eda_agent.py`:
  - Deduplicate findings: use a dict keyed by (phase, goal_name), replacing on update
  - Summary markdown cell: write a concise 5-7 line summary, not every finding
  - The summary should be DIFFERENT from the story (notebook = technical, story = narrative)

- [x] Update `backend/routers/run.py` story generation:
  - Use the LLM to write a NARRATIVE story, not a bullet list of findings
  - Prompt: "Write a 2-3 paragraph data narrative for an analyst. What does the data
    show? What patterns matter? What should they investigate next? Be specific with
    numbers but write in flowing prose, not bullets."
  - Story sections should be narrative paragraphs, not finding dumps

## Problem 4: Chat says "sure, what kind?" instead of executing code

- [x] Update `src/chat/chat_agent.py` system prompt:
  - Much more aggressive about executing code: "When the user asks you to visualize,
    plot, analyze, or investigate ANYTHING, ALWAYS include an ACTION block with the
    code. Never respond with just text when code could answer the question."
  - Include the actual column list so code is correct
  - Include the time column name so plots use the right axis

## Problem 5: Follow-up reasoning quality

- [x] Update `src/agent/reasoning.py`:
  - Better system prompt: "You are investigating data. After each cell, decide if there
    is a specific HYPOTHESIS worth testing with a new cell. Examples of good follow-ups:
    'The distribution is bimodal — let me check if the two modes correspond to different
    time periods.' Bad follow-ups: 'Let me verify the data loaded correctly' (already done)."
  - Reduce temperature to 0.1 for more focused reasoning
  - Add "NEVER write df.head(), df.info(), df.describe() as a follow-up — those are
    already done in the main goals"

## Implementation — all in one shot, no sprints needed
