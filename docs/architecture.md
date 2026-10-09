# Assembly Architecture

Assembly orchestrates a dynamic, temporary team of AI agents to answer complex user questions within a fixed time budget.

## Component Diagram

```mermaid
graph TD
    %% Core Components
    User((User)) --> |Question + Time Budget| Backend[FastAPI Backend]
    
    subgraph "Clients"
        Web[Vanilla JS / Next.js]
        Desktop[Tauri 2 App]
    end
    
    Web --> Backend
    Desktop --> |Local Sidecar| Backend

    subgraph "Orchestration Engine"
        Backend --> Orchestrator
        Orchestrator --> Planner[Planner]
        Planner --> AgentManager[Agent Manager]
        AgentManager --> Agents[Temporary Team of Agents]
        Agents --> IndependentSolve[Independent Solving]
        IndependentSolve --> Debate[Debate Manager]
        Debate <--> Consensus[Consensus Engine]
        Consensus --> Synthesizer[Synthesizer]
        Synthesizer --> Composer[Final Composer]
    end
    
    subgraph "Support Services"
        Router[Model Router]
        WebResearch[Web Search]
        KeyStore[Request Key Store]
    end

    Planner -.-> Router
    AgentManager -.-> Router
    Agents -.-> WebResearch
    Router -.-> KeyStore
```

## Execution State Machine

The core `Orchestrator` relies on a strict state machine to manage the execution lifecycle. 

```mermaid
stateDiagram-v2
    [*] --> CREATED: User submits question
    CREATED --> CAPACITY_CHECK: Evaluate budget & tokens
    CAPACITY_CHECK --> PLANNING: Allocate roles & strategy
    PLANNING --> TEAM_READY: Instantiate Agent instances
    TEAM_READY --> SOLVING: Agents solve independently
    SOLVING --> EVALUATING: Score consensus
    
    EVALUATING --> DEBATING: Consensus < Threshold (or Adversarial round triggered)
    DEBATING --> EVALUATING: Re-score after debate round
    
    EVALUATING --> SYNTHESIZING: Consensus reached or time up
    SYNTHESIZING --> COMPLETED: Final Answer compiled
    
    CREATED --> CANCELLED: User aborted
    CAPACITY_CHECK --> CANCELLED
    PLANNING --> CANCELLED
    TEAM_READY --> CANCELLED
    SOLVING --> CANCELLED
    EVALUATING --> CANCELLED
    DEBATING --> CANCELLED
    SYNTHESIZING --> CANCELLED

    COMPLETED --> [*]
    CANCELLED --> [*]
```

## Overview of Phases

1. **Capacity Check**: A heuristic evaluation of available rate limits and time. 
2. **Planning**: A planner agent classifies the problem complexity, determines if research is needed, and outputs a required team composition.
3. **Team Ready**: The Agent Manager instantiates diverse agents based on the plan. Diversity is strictly enforced by model family.
4. **Independent Solving**: Agents solve the question entirely independently to avoid groupthink.
5. **Evaluating / Debating**: The Consensus Engine evaluates answers based on agreement, confidence, evidence, contradiction, and stability. If consensus isn't reached (or if an adversarial strike is triggered to challenge premature consensus), a Debate Round runs where agents cross-examine each other.
6. **Synthesizing**: A synthesizer takes all arguments, debate history, and source references to compose a final output with an uncertainty note.
