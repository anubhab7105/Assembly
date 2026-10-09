# Assembly

Assembly turns one user question and a time budget (3, 5, 10, or 15 minutes) into a temporary team of AI agents. These agents solve independently, cross-examine each other through debate, and ultimately synthesize a highly accurate, consensus-driven final answer.

![Screenshot Placeholder 1](assets/screenshot1.png)
*Assembly Dashboard: A temporary team of AI experts debating your question.*

![Screenshot Placeholder 2](assets/screenshot2.png)
*Assembly Analytics: Real-time consensus scoring and execution metrics.*

## Quick Start

### Web Mode (Local Development)

1. Clone the repository and navigate to the directory.
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy the environment template:
   ```bash
   cp .env.example .env.dev
   ```
4. Start the FastAPI backend and vanilla JS SPA:
   ```bash
   uvicorn src.main:app --reload
   ```
5. Open your browser and navigate to `http://localhost:8000` (or the port specified by uvicorn).

### Desktop Mode (Local App)

Assembly is designed as a secure, local-first Desktop app using Tauri v2.

1. Install Node dependencies (if applicable to your Tauri setup) and Rust.
2. Run the desktop application:
   ```bash
   npm run tauri dev
   ```
*(Note: Full Tauri and Next.js migrations are pending, currently runs via local vanilla SPA server).*

## How to Get Free Keys

Assembly enforces a **BYOK (Bring Your Own Keys)** policy. There is no shared operator key and the orchestrator strictly uses free-tier model keys provided by the user.

You need at least **3 distinct model families** (e.g., Google Gemini, Groq/Llama, Mistral, Together AI, Cerebras, etc.) to satisfy Assembly's diversity requirements for effective debate.

1. **Google Gemini**: Get a free API key from Google AI Studio.
2. **Groq**: Get a free API key from the Groq Cloud console.
3. **Together AI / Cerebras**: Get a free API key from their respective developer platforms.

Add these keys to your `.env.dev` file. For the desktop app, keys are stored securely in the OS Keyring via Windows Credential Manager and never written to disk in plain text.

## Known Limits

- **Free-Tier Only**: The system explicitly enforces usage of free-tier models. Paid provider code paths or shared billing features do not exist.
- **Provider Rate Limits**: Due to relying on free-tier APIs, you may occasionally hit Rate Limits or Quota Exhaustion. Assembly has built-in fault tolerance to retry or fallback, but extreme throttling may degrade the consensus process.
- **Family Diversity**: You must provide keys from at least 3 distinct model families. Fewer than 2 distinct families will result in a `RuntimeError` by the `ModelRouter`. Same-family agents count as a single vote.
