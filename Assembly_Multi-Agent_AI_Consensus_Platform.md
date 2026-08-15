# Assembly — Multi-Agent AI Consensus Platform

## 1. Product Concept

### Name
**Assembly**

### Core idea

Assembly is a multi-agent AI platform where a user's question is given to a temporary team of AI agents. The agents independently solve the problem, research evidence, challenge each other's conclusions, verify claims, and continue collaborating until they reach a sufficiently strong consensus or the user's time limit is reached.

The user receives only:

- The final synthesized answer
- The sources used

The internal agent discussion remains hidden.

### Core promise

> **Ask once. Let Assembly build a temporary expert team that researches, solves, challenges, and verifies the problem until it reaches the strongest answer possible within your chosen time.**

---

# 2. Target Users

Primary users:

- Developers
- Students
- Researchers

Primary problem categories:

- Math and science
- General questions
- Coding
- Research
- Complex multi-step problems

The system should eventually support additional domains, but these categories should drive the initial product design.

---

# 3. Core Product Experience

The user submits a question and selects a thinking-time budget from:

- 3 minutes
- 5 minutes
- 10 minutes
- 15 minutes

Assembly automatically determines:

- The problem type
- The required capabilities
- The number of agents
- The models to use
- The specialist roles
- Whether web research is needed
- How many debate/verification rounds are necessary
- When the team has reached sufficient consensus

The user does **not** manually configure the team.

---

# 4. Core Workflow

```text
                           USER
                            │
                            ▼
                     Submit Question
                            │
                            ▼
                 Problem Understanding
                         / Planner
                            │
                            ▼
                    Team Orchestrator
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
           Agent A       Agent B       Agent C
            GPT          Gemini         Groq
              │             │             │
              └─────────────┼─────────────┘
                            ▼
                    Shared Workspace
                            │
                            ▼
                     Agent Debate
                            │
                 ┌──────────┼──────────┐
                 ▼          ▼          ▼
              Critique   Research   Verification
                 │          │          │
                 └──────────┼──────────┘
                            ▼
                     Consensus Check
                            │
                 ┌──────────┴──────────┐
                 │                     │
             Consensus?                No
                 │                     │
                Yes                    ▼
                 │               Another Round
                 │                     │
                 └──────────┬──────────┘
                            ▼
                    Final Synthesizer
                            │
                            ▼
                    Final Answer + Sources
```

The critical distinction is that Assembly should **not** simply ask several models the same question and average their answers.

The agents become a temporary collaborative team.

---

# 5. Dynamic AI Team Formation

Users should not have to select specialist roles manually.

Assembly should determine the team automatically based on the problem.

### Example

User asks:

> "Why does this algorithm have O(n log n) complexity, and how can I optimize it?"

Assembly could automatically create:

| Agent | Role | Model |
|---|---|---|
| Agent 1 | Algorithm Solver | GPT |
| Agent 2 | Complexity Analyst | Gemini |
| Agent 3 | Code Analyst | Groq |
| Agent 4 | Alternative Approach Researcher | Open-source model |
| Agent 5 | Critic / Verifier | GPT or Gemini |

The user sees only the progress and final result, not the internal agent conversation.

---

# 6. Agent Lifecycle

## Stage 1 — Independent Solving

Each agent initially works independently.

This reduces early groupthink.

```text
Question
   │
   ├── Agent A → Solution A
   ├── Agent B → Solution B
   ├── Agent C → Solution C
   └── Agent D → Solution D
```

The agents should not immediately see one another's answers.

---

## Stage 2 — Share Conclusions

After independent work, agents publish structured findings to a shared workspace.

Example:

```text
Agent A
Conclusion: ...
Evidence: ...
Confidence: 82%

Agent B
Conclusion: ...
Evidence: ...
Confidence: 64%

Agent C
Conclusion: ...
Evidence: ...
Confidence: 91%
```

---

## Stage 3 — Cross-Agent Debate

Agents review the other conclusions and identify:

- Incorrect assumptions
- Missing evidence
- Contradictions
- Weak reasoning
- Unsupported claims
- Better alternative approaches

Examples:

> Agent B's assumption about X is incorrect because...

> Agent A and Agent C independently reached the same conclusion, but the evidence still needs verification.

The goal is not conversational filler. Every round should either:

- resolve a disagreement,
- add evidence,
- improve a solution,
- remove an error,
- or increase confidence.

---

# 7. Debate Rounds

A typical high-complexity execution could look like:

```text
ROUND 1
Independent solutions

        ↓

ROUND 2
Cross-examination

        ↓

ROUND 3
Research / evidence verification

        ↓

ROUND 4
Resolve disagreements

        ↓

ROUND 5
Consensus evaluation

        ↓

FINAL SYNTHESIS
```

The number of rounds should not be fixed.

Assembly continues while more work is useful and time remains.

---

# 8. Time Budget System

The user's selected time limit is one of the core product features.

Suggested UI:

```text
AI Team Thinking Time

○ 3 min
○ 5 min
○ 10 min
○ 15 min
```

or:

```text
3 min ───────────────●──────── 15 min
```

The time budget should function as a hard orchestration constraint.

### 3-minute execution

Possible strategy:

```text
2–3 agents
1 debate/verification round
Fast synthesis
```

### 5-minute execution

Possible strategy:

```text
3–4 agents
2 debate rounds
Basic verification
```

### 10-minute execution

Possible strategy:

```text
4–6 agents
Multiple debate rounds
Web research
Cross-verification
```

### 15-minute execution

Possible strategy:

```text
5–8 agents
Deep research
Multiple critique rounds
Source verification
Final consensus
```

These are examples, not hard-coded rules.

Assembly should dynamically decide whether additional time is better spent on:

- Another agent
- Another research cycle
- Deeper verification
- Another debate round
- Code execution/testing
- Source checking

---

# 9. Consensus Engine

The consensus engine is one of the most important components.

Assembly needs an actual **Consensus Controller**, not just a final LLM.

Each agent should return structured information.

Example:

```json
{
  "agent": "agent_03",
  "position": "...",
  "confidence": 0.87,
  "supports": ["agent_01"],
  "disagrees_with": ["agent_02"],
  "evidence": [],
  "remaining_uncertainty": []
}
```

The consensus engine can evaluate factors such as:

- Agreement across independent agents
- Evidence quality
- Independent verification
- Contradictions
- Confidence
- Remaining uncertainty
- New information produced per round

Example:

```text
Consensus Score: 0.91
Remaining disagreement: Low
New information per round: Very Low

→ STOP DEBATE
```

---

# 10. Preventing AI Echo Chambers

A major risk in multi-agent systems is:

```text
Model A makes a wrong claim
        ↓
Model B trusts A
        ↓
Model C trusts B
        ↓
Everyone agrees
        ↓
The wrong answer looks like consensus
```

Assembly should intentionally prevent this.

## Independent first-pass reasoning

Agents should initially solve the problem separately.

## Evidence requirements

Claims should include supporting evidence where possible.

```text
Claim
 ↓
Evidence
 ↓
Verification
 ↓
Confidence
```

## Dedicated critic

At least one agent should actively search for flaws.

Its role is essentially:

> "What could everyone here be wrong about?"

## Adversarial verification

The orchestrator can deliberately assign an agent to challenge the current consensus:

> "Assume the current consensus is wrong. Find the strongest counterargument."

This makes agreement harder to achieve unless the evidence supports it.

---

# 11. Research Engine

Web research should be a core feature because research is one of Assembly's target use cases.

For research-heavy questions:

```text
User
  │
  ▼
Research Agents
  ├── Source group A
  ├── Source group B
  ├── Source group C
  └── Source group D
          │
          ▼
    Source Collector
          │
          ▼
 Source Credibility Analysis
          │
          ▼
   Cross Verification
          │
          ▼
       Consensus
```

The final answer should include only the sources actually used.

Example:

```text
Sources

[1] NASA — ...
[2] IEEE — ...
[3] Nature — ...
```

---

# 12. Coding Mode

Coding problems should use a specialized orchestration strategy.

Example team:

```text
User
 │
 ├── Problem Analyzer
 ├── Solution Architect
 ├── Implementation Agent
 ├── Security Reviewer
 ├── Performance Reviewer
 └── Debugging Agent
```

Agents should collaborate around a shared implementation artifact.

Example:

```text
/code
/tests
/requirements
/analysis
```

Workflow:

```text
Implementation Agent
        ↓
Code Review Agent
        ↓
Edge-Case Agent
        ↓
Security Agent
        ↓
Performance Agent
        ↓
Final Synthesis
```

This is more powerful than simply asking several models to write separate implementations.

---

# 13. General-Question Mode

Assembly should not automatically use a large multi-agent team for simple questions.

The first step should be **problem classification**.

Example:

```text
"What is photosynthesis?"

Complexity → LOW

→ 2 agents
→ Minimal debate
→ Fast answer
```

More complex question:

```text
"Compare CRISPR, RNAi and gene therapy for treating..."

Complexity → HIGH

→ 5–6 agents
→ Research
→ Multiple verification rounds
→ Consensus
```

This improves:

- Speed
- Cost
- User experience
- Resource utilization

---

# 14. Final Answer Behavior

The user should see only:

1. Final synthesized answer
2. Sources used

Do **not** expose detailed internal reasoning or agent-by-agent chain-of-thought.

A useful progress UI can show high-level system state without exposing internal deliberation.

For example:

```text
5 agents researching
3 disagreements identified
2 sources being verified
Consensus: 84%
Time remaining: 03:21
```

This gives the user confidence that the system is actively working without exposing private internal reasoning.

---

# 15. Main Application UX

Assembly should have two major experiences.

## A. Chat Interface

Similar to modern AI chat applications.

```text
┌────────────────────────────────────────────┐
│ Assembly                                   │
│                                            │
│ Ask your question...                       │
│                                            │
│                                            │
│                         [ Send → ]         │
└────────────────────────────────────────────┘

Thinking time: [ 3m  5m  10m  15m ]

Mode: Auto
```

---

## B. Team Progress Workspace

While Assembly is working:

```text
┌───────────────────────────────────────────────┐
│ AI TEAM WORKING                               │
│                                               │
│ ● Researcher       Searching sources          │
│ ● Analyst          Comparing approaches       │
│ ● Coder            Testing solution           │
│ ● Critic           Reviewing claims           │
│                                               │
│ Consensus: 72%                                │
│ Time remaining: 04:31                         │
│                                               │
│ Team activity                                 │
└───────────────────────────────────────────────┘
```

The workspace should display high-level activity, not internal chain-of-thought.

---

# 16. Technical Stack

Recommended stack:

```text
Frontend
Next.js
TypeScript
Tailwind CSS

Backend
FastAPI
Python

AI Orchestration
Custom orchestration layer

Models
OpenAI / GPT
Google Gemini
Groq
Selected Open-source models

Database
PostgreSQL

Cache / Queue / Event Bus
Redis

Authentication
Supabase Auth or equivalent

Deployment
Vercel (frontend)
Cloud infrastructure for FastAPI / workers
```

The model layer should be provider-agnostic.

---

# 17. System Architecture

```text
                         ┌──────────────┐
                         │   Next.js    │
                         │     UI       │
                         └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │   FastAPI    │
                         │ API Gateway  │
                         └──────┬───────┘
                                │
                ┌───────────────┴────────────────┐
                ▼                                ▼
        ┌───────────────┐                ┌──────────────┐
        │ Authentication│                │ PostgreSQL   │
        └───────────────┘                └──────────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │ AI ORCHESTRATOR     │
                     │                     │
                     │ Planner             │
                     │ Agent Manager       │
                     │ Time Controller     │
                     │ Consensus Engine    │
                     │ Cost Controller     │
                     └──────────┬──────────┘
                                │
                         ┌──────┴──────┐
                         ▼             ▼
                  ┌────────────┐  ┌─────────────┐
                  │ Agent Pool │  │ Research    │
                  └─────┬──────┘  │ Engine      │
                        │         └──────┬──────┘
        ┌───────────────┼───────────────┼──────────────┐
        ▼               ▼               ▼              ▼
      GPT            Gemini           Groq          Open Source
        │               │               │              │
        └───────────────┴───────┬───────┴──────────────┘
                                ▼
                       ┌─────────────────┐
                       │ Shared Workspace│
                       │ / Event Bus     │
                       └────────┬────────┘
                                ▼
                       ┌─────────────────┐
                       │ Final Synthesis │
                       └────────┬────────┘
                                ▼
                       ┌─────────────────┐
                       │ Answer + Sources│
                       └─────────────────┘
```

---

# 18. Backend Structure

Recommended FastAPI project structure:

```text
backend/
│
├── api/
│   ├── auth.py
│   ├── conversations.py
│   ├── teams.py
│   └── executions.py
│
├── orchestration/
│   ├── planner.py
│   ├── orchestrator.py
│   ├── agent_manager.py
│   ├── consensus.py
│   ├── debate.py
│   └── scheduler.py
│
├── agents/
│   ├── base_agent.py
│   ├── researcher.py
│   ├── coder.py
│   ├── analyst.py
│   ├── critic.py
│   └── synthesizer.py
│
├── providers/
│   ├── openai.py
│   ├── gemini.py
│   ├── groq.py
│   └── open_source.py
│
├── research/
│   ├── search.py
│   ├── scraper.py
│   ├── source_ranker.py
│   └── citation_manager.py
│
├── memory/
│   ├── conversation.py
│   ├── team_memory.py
│   └── vector_store.py
│
└── core/
    ├── config.py
    ├── security.py
    └── logging.py
```

---

# 19. Provider Abstraction

The orchestrator should never depend directly on one provider.

Create a common interface:

```python
class AIProvider:
    async def generate(
        self,
        messages,
        model,
        temperature=0.2,
        **kwargs
    ):
        ...
```

Then implement:

```text
OpenAIProvider
GeminiProvider
GroqProvider
OpenSourceProvider
```

This lets the system add or replace models without rewriting the orchestration layer.

---

# 20. Database Design

PostgreSQL should store users, conversations, executions, agents, debate rounds, sources, and usage.

Suggested tables:

```text
users
sessions
conversations
messages
executions
agents
agent_runs
agent_messages
debate_rounds
consensus_events
sources
citations
usage
saved_teams
```

Example `agent_runs` record:

```text
id
execution_id
agent_id
model
role
input_tokens
output_tokens
status
confidence
started_at
completed_at
```

Example `agent_messages`:

```text
id
round_id
agent_id
message_type
content
claim
evidence
confidence
created_at
```

Structured storage will make debugging, analytics, and evaluation much easier than storing only raw conversation text.

---

# 21. Temporary Team Model

A team should exist for one task execution.

```text
Question
   ↓
Create Temporary Team
   ↓
Agents Collaborate
   ↓
Consensus
   ↓
Final Answer
   ↓
Team Lifecycle Ends
```

Example:

```text
Execution #9283

Temporary Team
├── Researcher
├── Scientist
├── Data Analyst
├── Critic
└── Synthesizer
```

The execution history can still be stored for the user.

The team itself does not need to remain active permanently.

---

# 22. Model Routing

Do not hard-code a fixed mapping like:

```text
Agent 1 → GPT
Agent 2 → Gemini
Agent 3 → Groq
```

Instead create a **Model Router**.

The router evaluates:

- Task type
- Complexity
- Cost
- Latency
- Required capability
- Context size
- Availability
- User time budget

Then selects the appropriate model.

Examples:

```text
Mathematics
→ strong reasoning model

Coding
→ strong coding model

Research
→ model + web search

Fast verification
→ low-latency model

Parallel exploration
→ fast/low-cost model
```

---

# 23. Cost Control

A naïve multi-agent architecture can become extremely expensive.

Example:

```text
8 agents
×
10 rounds
×
large context
=
very large API bill
```

Assembly needs a **Token & Budget Controller**.

Each execution should have:

```text
Time Budget
Token Budget
Agent Budget
Search Budget
```

Example:

```text
5-minute execution

Maximum:
4 agents
6 debate rounds
60 web searches
X tokens
```

The controller continuously monitors usage and stops or scales back unnecessary work.

---

# 24. Stopping Algorithm

Assembly should never allow agents to debate indefinitely.

A stopping decision can use:

```text
Consensus Score
+
Evidence Confidence
+
Agreement Stability
+
New Information Rate
+
Remaining Time
```

Example:

```text
Consensus > 90%
AND
New information < threshold
AND
No major unresolved contradiction

→ FINALIZE
```

Otherwise:

```text
Continue Debate
```

Near the deadline:

```text
Remaining Time < Safety Threshold
        ↓
Stop launching new work
        ↓
Final Synthesis
```

If consensus is weak, the final answer should state uncertainty rather than pretending complete confidence.

---

# 25. Failure Handling

The orchestration layer should assume that failures will happen.

### Provider failure

```text
Gemini unavailable
     ↓
Router detects failure
     ↓
Fallback model selected
```

### Malformed agent response

```text
Agent produces invalid schema
        ↓
Schema validation
        ↓
Retry once
        ↓
Fallback
```

### Strong disagreement

```text
Two agents disagree strongly
        ↓
Verification task created
        ↓
Research / testing
        ↓
Re-evaluation
```

### Timeout

```text
Agent exceeds time allocation
        ↓
Cancel or replace
        ↓
Continue with remaining team
```

---

# 26. Authentication and User Accounts

The application should support:

- Sign up
- Login
- Google OAuth
- Password reset

User dashboard:

```text
Recent Questions
Saved Conversations
Usage
Saved Teams
Account
```

Each execution is associated with the authenticated user.

---

# 27. Monetization

The system naturally supports usage-based tiers.

## Free

```text
3-minute execution
Limited executions/day
Fewer agents
Basic models
```

## Pro

```text
15-minute execution
More agents
Advanced models
Deeper research
Higher limits
```

## Researcher / Developer

Potential features:

```text
Higher execution limits
API access
Export results
Custom workflows
Project memory
Advanced research capabilities
```

Pricing should be finalized only after actual model and infrastructure costs are measured.

---

# 28. MVP Scope

The first version should prove one central hypothesis:

> **Does a temporary multi-agent team produce better answers than a single AI model?**

Do not attempt to build every feature initially.

## MVP Frontend

- Chat interface
- Login / signup
- Time selector: 3–15 minutes
- Execution progress
- Final answer
- Sources
- Conversation history

## MVP Backend

- FastAPI
- Orchestrator
- Model router
- 3–4 agents
- Agent communication
- Consensus engine
- Final synthesizer
- Web search
- PostgreSQL

## Initial agent types

```text
1. Solver
2. Researcher
3. Critic
4. Synthesizer
```

Do not start with ten specialized roles.

---

# 29. Example MVP Execution

User asks:

> "Is React better than Vue for a large cybersecurity platform?"

Assembly:

```text
User Question
      ↓
Planner
      ↓
Task Type:
Technical Comparison

Complexity:
Medium
      ↓
Temporary Team Created
      ↓
Solver
Architecture analysis

Researcher
Current ecosystem evidence

Analyst
Scalability / performance

Critic
Challenges assumptions
      ↓
Debate
      ↓
Evidence verification
      ↓
Consensus
      ↓
Final Synthesizer
      ↓
Final Answer
+
Sources
```

The user sees only the final result and sources.

---

# 30. Shared Workspace / Event Bus

Agents should not communicate only through direct API-to-API conversations.

Use a shared message/event system.

Concept:

```text
                  ┌──────────────────┐
                  │ Shared Workspace │
                  └────────┬─────────┘
                           │
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
    Agent A             Agent B             Agent C
       │                   │                   │
       └──────── publish/read events ──────────┘
```

Advantages:

- Better observability
- Easier retries
- Better parallel execution
- Easier persistence
- Easier debugging
- Provider independence
- Ability to resume interrupted executions

For the MVP, Redis is sufficient.

At larger scale, consider technologies such as:

- Redis Streams
- NATS
- Kafka

---

# 31. Recommended Development Roadmap

## Phase 1 — Foundation

Build:

```text
Next.js
TypeScript
Tailwind
FastAPI
PostgreSQL
Authentication
Basic chat
```

---

## Phase 2 — Multi-Model Layer

Integrate:

```text
OpenAI
Gemini
Groq
Open-source model provider
```

Create a common provider interface.

---

## Phase 3 — Agent System

Build:

```text
BaseAgent
ResearchAgent
SolverAgent
CriticAgent
SynthesizerAgent
```

---

## Phase 4 — Orchestrator

Implement:

```text
Planner
Dynamic agent allocation
Parallel execution
Debate rounds
Consensus detection
Time budget control
```

---

## Phase 5 — Research

Add:

```text
Web search
Source extraction
Source ranking
Citation tracking
Cross verification
```

---

## Phase 6 — Production Hardening

Add:

```text
Rate limiting
API key security
Retry/fallback
Cost tracking
Observability
Queue management
Execution cancellation
Provider health monitoring
```

---

## Phase 7 — UX Polish

Add:

```text
AI team progress
Time remaining
Consensus indicator
Answer streaming
Source cards
Conversation history
Saved teams
Usage dashboard
```

---

# 32. Key Product Differentiator

The marketing should not focus simply on:

> "We use multiple AI models."

That alone is easy to copy.

The real differentiator is:

> **Assembly creates a temporary expert team, makes the members independently solve the problem, lets them challenge and verify one another, and continues until the team reaches a strong consensus or the user's time budget runs out.**

The core technology is the orchestration layer:

```text
Problem Decomposition
        ↓
Dynamic Team Formation
        ↓
Independent Reasoning
        ↓
Cross-Agent Debate
        ↓
Evidence Verification
        ↓
Consensus Detection
        ↓
Repeat Until Consensus / Time Limit
        ↓
Final Synthesis
        ↓
Answer + Sources
```

---

# 33. Final Product Architecture

```text
                         ┌──────────────┐
                         │   Next.js    │
                         │     UI       │
                         └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │   FastAPI    │
                         │ API Gateway  │
                         └──────┬───────┘
                                │
                ┌───────────────┴────────────────┐
                ▼                                ▼
        ┌───────────────┐                ┌──────────────┐
        │ Authentication│                │ PostgreSQL   │
        └───────────────┘                └──────────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │ AI ORCHESTRATOR     │
                     │                     │
                     │ Planner             │
                     │ Agent Manager       │
                     │ Time Controller     │
                     │ Consensus Engine    │
                     │ Cost Controller     │
                     └──────────┬──────────┘
                                │
                         ┌──────┴──────┐
                         ▼             ▼
                  ┌────────────┐  ┌─────────────┐
                  │ Agent Pool │  │ Research    │
                  └─────┬──────┘  │ Engine      │
                        │         └──────┬──────┘
        ┌───────────────┼───────────────┼──────────────┐
        ▼               ▼               ▼              ▼
      GPT            Gemini           Groq          Open Source
        │               │               │              │
        └───────────────┴───────┬───────┴──────────────┘
                                ▼
                       ┌─────────────────┐
                       │ Shared Workspace│
                       │ / Event Bus     │
                       └────────┬────────┘
                                ▼
                       ┌─────────────────┐
                       │ Final Synthesis │
                       └────────┬────────┘
                                ▼
                       ┌─────────────────┐
                       │ Answer + Sources│
                       └─────────────────┘
```

---

# 34. Core Product Loop

```text
Question
   ↓
Decompose
   ↓
Form Expert Team
   ↓
Independent Solutions
   ↓
Debate
   ↓
Research / Verify
   ↓
Measure Consensus
   ↓
Repeat While Useful
   ↓
Synthesize
   ↓
Final Answer + Sources
```

**Assembly is best positioned as an AI consensus engine rather than a conventional chatbot.**

Its defining feature is not the number of models it calls; it is the system that decides **which AI experts should work together, how they should challenge one another, when more research is necessary, and when the answer is strong enough to finalize.**
