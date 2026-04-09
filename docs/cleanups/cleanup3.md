# cleanup3.md — Intelligence, Story UI, Chat Actions, Agent Reasoning

## 1. Story Tab: Notion-Style Narrative View

The story should tell the DATA'S story, not regurgitate findings text.

- [x] Rewrite `backend/routers/run.py` story generation:
  - Use the LLM to synthesize a NARRATIVE from findings, not a bullet list
  - LLM prompt: "Given these EDA findings, write a data story that tells the analyst what the data is saying. Include: what the data looks like, what patterns exist, what anomalies stand out, what relationships matter, and what the analyst should investigate next."
  - Include plot references (cell IDs that contain matplotlib outputs)
  - Structure: narrative prose sections, not "Phase: finding" format

- [x] Rewrite `frontend/src/components/story/StoryPane.tsx`:
  - Notion-style clean typography: large title, serif body text, generous whitespace
  - Inline plot images pulled from notebook cell outputs (match cell_id to base64 images)
  - Insight callout boxes (colored sidebar accent, not cards)
  - Smooth section transitions, no collapsible accordions — this is a DOCUMENT, not a dashboard
  - Export should produce a clean PDF that looks like a professional report

- [x] Rewrite `frontend/src/components/story/StorySectionCard.tsx`:
  - Replace accordion with flowing prose sections
  - Section headers as elegant h2 with subtle dividers
  - Inline images rendered at full width with captions
  - Key metrics highlighted in colored callout boxes

## 2. Agent Reasoning Loop (Reactive, Hypothesis-Driven)

Current agent runs a fixed checklist. It should REACT to outputs and branch.

- [x] Rewrite `src/agent/eda_agent.py`:
  - After each cell execution, the LLM READS the output and DECIDES what to do next
  - The agent should form HYPOTHESES from what it sees:
    - "I see high skewness in revenue — let me test a log transform"
    - "The correlation between X and Y is 0.95 — let me check if this is spurious via lag analysis"
    - "There's a spike in March — let me zoom in and check for regime change"
  - Recursive curiosity: if a finding is surprising, spawn a sub-investigation (2-3 cells) before moving on
  - The LLM decides when each EDA GOAL is truly met, not just "ran the code"

- [x] Create `src/agent/reasoning.py`:
  - `decide_next_step(state, last_output, goals_remaining) -> (code, thinking, goal_update)`
  - LLM call with system prompt containing: EDA rules, current state, last output, remaining goals
  - Returns: next code to write, thinking explanation for user, which goal this serves
  - Can return "investigate further" to branch into sub-analysis

- [x] Update `src/agent/goals.py`:
  - Goals become SOFT targets, not a rigid checklist
  - Agent can insert ad-hoc goals based on discoveries
  - Each goal has a `satisfied(state, outputs)` check that the LLM evaluates

## 3. Chat Frontend: Modern Agentic UI

- [x] Rewrite `frontend/src/components/chat/ChatSidebar.tsx`:
  - During agent run: show a COMPACT activity feed, not individual message bubbles
  - Thinking messages: animated typing indicator with collapsible reasoning (like Claude/ChatGPT thinking)
  - Phase transitions: subtle section dividers, not full message bubbles
  - Cell write notifications: compact single-line with icon, not multi-line bubbles
  - After agent completes: switch to conversational mode with full message bubbles

- [x] Rewrite `frontend/src/components/chat/ChatMessage.tsx`:
  - Agent thinking: collapsible with animated "..." while in progress, then shows summary
  - "View Cell" button: scrolls notebook to that cell AND highlights it briefly
  - Agent actions: show as compact status updates with icons, not text walls
  - Markdown rendering in agent messages (bold, code, lists)

- [x] Update `frontend/src/hooks/useAgentStream.ts`:
  - Reduce chat noise: batch thinking events (don't push every single one as a separate message)
  - Phase transitions: one compact status message per phase, not verbose

## 4. Chat-Driven Actions (Agent Writes Code on Request)

When user asks "plot X vs Y" or "check for stationarity", the agent should:
1. Write a new code cell in the notebook
2. Execute it via the kernel
3. Stream the result back to chat AND notebook
4. Respond in chat with a summary of what it found

- [x] Update `backend/routers/chat.py`:
  - When the LLM response contains a code action (detected by the LLM itself), execute it:
    1. Write cell to notebook via stream events
    2. Execute via kernel_manager
    3. Push output to stream
    4. Return chat response summarizing the result

- [x] Update `src/chat/chat_agent.py`:
  - LLM system prompt includes: "If the user asks you to analyze, plot, or investigate something, respond with a JSON block containing the Python code to execute. Format: ```action\n{code}\n```"
  - Parse the response for action blocks
  - If action found: execute code, capture output, respond with summary

- [x] Update `frontend/src/hooks/useChat.ts`:
  - After sending a message, listen for new cells appearing in notebookStore (the backend will push them via stream)
  - Show "Running analysis..." indicator while code executes

## 5. Implementation Order

### Sprint 1: Agent reasoning (backend, no frontend changes)
- [x] Create `src/agent/reasoning.py` with LLM-powered next-step decisions
- [x] Update `src/agent/eda_agent.py` to use LLM for output interpretation and branching
- [x] Test: agent should produce more varied, data-reactive notebooks

### Sprint 2: Chat actions (backend + minimal frontend)
- [x] Update `backend/routers/chat.py` to execute code from chat
- [x] Update `src/chat/chat_agent.py` to emit action blocks
- [x] Test: "plot revenue over time" → cell appears in notebook with plot

### Sprint 3: Story UI (frontend)
- [x] Rewrite StoryPane with Notion-style layout
- [x] LLM-generated narrative in story generation
- [x] Inline plots from notebook outputs

### Sprint 4: Chat UI polish (frontend)
- [x] Compact activity feed during agent run
- [x] Animated thinking, View Cell scroll-to
- [x] Markdown rendering in chat messages
