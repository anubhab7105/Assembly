# Slides Outline (8 Slides)

## Slide 1: The Problem
- **Title**: The Limits of Single-Model Reasoning
- **Content**:
  - Single AI models suffer from blind spots, hallucinations, and groupthink.
  - Rate limits and costs make chaining large models (like GPT-4) at scale expensive.
  - Relying on one model family creates systemic biases.

## Slide 2: The Idea
- **Title**: Assembly: A Temporary AI Brain Trust
- **Content**:
  - Assembly turns one user question into a temporary team of free-tier AI agents.
  - The models solve independently, cross-examine each other through structured debate, and synthesize a consensus answer.
  - We bring the power of an expert room directly to your desktop, entirely for free.

## Slide 3: How It Works (Architecture)
- **Title**: The Orchestrator Workflow
- **Content**:
  - **Planner**: Classifies complexity and allocates roles.
  - **Independent Solving**: Agents solve in isolation to avoid groupthink.
  - **Consensus & Debate**: An engine calculates agreement. If low, agents debate. If high but suspicious, an adversarial critic attacks the consensus.
  - **Synthesizer**: Compiles the final, source-backed answer.

## Slide 4: Live Demo
- **Title**: Assembly in Action
- **Content**:
  - *(Visual)*: Blank slide or placeholder text pointing to the live application.
  - *(Action)*: Run a 3-minute execution live. Watch the agents independently solve and debate a complex technical question.

## Slide 5: Benchmark Results
- **Title**: Measurably Better Answers
- **Content**:
  - **Full Assembly Accuracy**: **87.5%**
  - **Best Single Model Accuracy**: **57.5%**
  - **Basic Voting Accuracy**: **60.0%**
  - *Ablation Note*: Removing the debate phase entirely drops Assembly's accuracy significantly down to 70.0%. Enforcing diversity is key—using same-family models drops accuracy by 17.5%.

## Slide 6: Security & Cost
- **Title**: Free, Fast, and Secure (BYOK)
- **Content**:
  - **Cost**: $0. Exclusively utilizes free-tier APIs (Gemini, Groq, Cerebras).
  - **Security**: Bring Your Own Keys (BYOK). Keys are securely stored locally via the OS Keyring. They are never logged, stored in plain text, or leaked to providers.
  - **Resilience**: Fault-tolerant router swaps providers instantly if rate limits are hit.

## Slide 7: Roadmap
- **Title**: What's Next?
- **Content**:
  - Full desktop integration with Tauri 2.
  - Enhanced research agents with deeper web scraping tools.
  - Extensible plugin system to allow users to write custom agent roles.
  - Expanded benchmark suites.

## Slide 8: The Ask
- **Title**: Join the Assembly
- **Content**:
  - **Call to Action**: Try the alpha, star the repo, and build your own local expert team today.
  - **Links**: GitHub Repo Link, Demo Video Link.
  - **Q&A**: Open the floor for questions.
