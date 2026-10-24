# Demo Script (3 Minutes)

This script is timed for a fast-paced 3-minute hackathon pitch.

## Timing Outline

- **0:00 - 0:30**: The Problem & Idea (Slide 1 & 2)
- **0:30 - 2:00**: Live Demo (Slide 3 & 4)
- **2:00 - 2:30**: Benchmark Results & Key Security (Slide 5 & 6)
- **2:30 - 3:00**: Roadmap & Ask (Slide 7 & 8)

## Live Demo Workflow

1. **Question to Ask**: 
   > "Is React better than Vue for a large cybersecurity platform? Compare ecosystem, performance, state management at scale, and hiring."
2. **Action**: 
   - Open the app.
   - Enter the question.
   - Select the **3m** thinking time budget.
   - Hit Send.
3. **Talking Points During the Run**:
   - Point out the Planner allocating agents based on complexity.
   - Show the independent solving phase (emphasize avoiding groupthink).
   - Point out the Debate phase where models cross-examine each other.
   - Show the live consensus score.
4. **Fallback**:
   - **If the live run stalls (provider rate limits, network issues)**: Wait 15 seconds. The UI will automatically show a "Play recorded run" button. Click it.
   - **If you need to instantly force a fallback**: Add `?demo=1` to the URL to reveal the hidden "Recorded demo" toggle before clicking Send.

## Pre-demo release gate

Before presenting the deployed R1 website as reliable, complete the [Hosted Web Rehearsal runbook](hosted-rehearsal.md): verify a full 5-minute run on the actual host, measure first-progress latency and final elapsed time, record ten attempts, test safe failure outcomes, and rehearse a recorded replay. CI or a local mocked run is not a substitute for this evidence. If the hosted stream is terminated by the platform, present the rehearsed local or recorded fallback instead of claiming the hosted rung is ready.

## Likely Judge Questions & Concise Answers

1. **What is the cost of running this?**
   - *Answer*: Practically zero. We exclusively use free-tier API models. Since keys are brought by the user, there's no central operator cost.
2. **How is security handled with user API keys?**
   - *Answer*: In the Desktop app, keys are securely stored in the OS Keyring and never touch plain text files. On Web, they are held purely in memory for the duration of the run and immediately wiped.
3. **Why not just use one large, capable model (like GPT-4)?**
   - *Answer*: Our benchmark ablation study (once verified — see `bench/results/demo/README.md`; demo numbers are synthetic) shows [insert verified number] for a team of diverse free-tier models vs [insert verified number] for the best single free model. Diversity catches blind spots.
4. **How exactly is the "consensus" computed?**
   - *Answer*: A deterministic engine scores answers based on five weighted factors: agreement (0.4), confidence (0.2), contradiction (0.175), stability (0.125), and evidence (0.1).
5. **What happens if all models agree immediately, but they are all wrong?**
   - *Answer*: If consensus is reached too early, the orchestrator deliberately triggers an **Adversarial Strike**. A critic from a different model family attacks the consensus to force a re-evaluation and break groupthink.
6. **What if the agents run out of time during debate?**
   - *Answer*: The orchestrator enforces a strict wall-clock deadline. If time runs low, it skips further debate and forces the Synthesizer to compile an answer with the current best arguments.
7. **Can a prompt injection attack the orchestrator?**
   - *Answer*: User inputs are treated strictly as untrusted data, never as system instructions. Web searches are heavily sanitized to strip out execution commands.
8. **Why are you using a Tauri Desktop app?**
   - *Answer*: It provides a highly secure, local-first environment for API keys, ensuring no sensitive credentials ever touch our servers.
