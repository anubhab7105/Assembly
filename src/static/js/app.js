/**
 * Assembly — Frontend Application
 * 
 * Handles auth, chat, WebSocket progress, and the full user experience.
 */

// ═══════════════════════════════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════════════════════════════

const state = {
    token: localStorage.getItem('assembly_token') || null,
    user: JSON.parse(localStorage.getItem('assembly_user') || 'null'),
    conversations: [],
    currentConversationId: null,
    currentExecutionId: null,
    selectedTimeBudget: 5,
    ws: null,
    isExecuting: false,
};

const API = '';  // Same origin

// ═══════════════════════════════════════════════════════════════════
// INITIALIZATION
// ═══════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    if (state.token && state.user) {
        showApp();
    } else {
        showAuth();
    }
    setupEventListeners();
});

function setupEventListeners() {
    // Auth
    document.getElementById('login-form').addEventListener('submit', handleLogin);
    document.getElementById('signup-form').addEventListener('submit', handleSignup);
    document.getElementById('show-signup').addEventListener('click', (e) => {
        e.preventDefault();
        toggleAuthForm('signup');
    });
    document.getElementById('show-login').addEventListener('click', (e) => {
        e.preventDefault();
        toggleAuthForm('login');
    });

    // Chat
    document.getElementById('send-btn').addEventListener('click', submitQuestion);
    document.getElementById('question-input').addEventListener('input', handleInputChange);
    document.getElementById('question-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submitQuestion();
        }
    });

    // Time selector
    document.querySelectorAll('.time-option').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.time-option').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.selectedTimeBudget = parseInt(btn.dataset.minutes);
        });
    });

    // New chat
    document.getElementById('new-chat-btn').addEventListener('click', startNewChat);

    // Logout
    document.getElementById('logout-btn').addEventListener('click', handleLogout);

    // Welcome tags
    document.querySelectorAll('.tag').forEach(tag => {
        tag.addEventListener('click', () => {
            document.getElementById('question-input').value = tag.dataset.question;
            handleInputChange();
            document.getElementById('question-input').focus();
        });
    });
}

// ═══════════════════════════════════════════════════════════════════
// AUTH
// ═══════════════════════════════════════════════════════════════════

function toggleAuthForm(form) {
    document.getElementById('login-form').classList.toggle('active', form === 'login');
    document.getElementById('signup-form').classList.toggle('active', form === 'signup');
}

async function handleLogin(e) {
    e.preventDefault();
    const btn = document.getElementById('login-btn');
    const errorEl = document.getElementById('login-error');
    errorEl.textContent = '';
    btn.classList.add('loading');

    try {
        const res = await fetch(`${API}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                email: document.getElementById('login-email').value,
                password: document.getElementById('login-password').value,
            }),
        });

        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.detail || 'Login failed');
        }

        const data = await res.json();
        setAuth(data.access_token, data.user);
        showApp();
    } catch (err) {
        errorEl.textContent = err.message;
    } finally {
        btn.classList.remove('loading');
    }
}

async function handleSignup(e) {
    e.preventDefault();
    const btn = document.getElementById('signup-btn');
    const errorEl = document.getElementById('signup-error');
    errorEl.textContent = '';
    btn.classList.add('loading');

    try {
        const res = await fetch(`${API}/api/auth/signup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: document.getElementById('signup-name').value,
                email: document.getElementById('signup-email').value,
                password: document.getElementById('signup-password').value,
            }),
        });

        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.detail || 'Signup failed');
        }

        const data = await res.json();
        setAuth(data.access_token, data.user);
        showApp();
    } catch (err) {
        errorEl.textContent = err.message;
    } finally {
        btn.classList.remove('loading');
    }
}

function setAuth(token, user) {
    state.token = token;
    state.user = user;
    localStorage.setItem('assembly_token', token);
    localStorage.setItem('assembly_user', JSON.stringify(user));
}

function handleLogout() {
    state.token = null;
    state.user = null;
    localStorage.removeItem('assembly_token');
    localStorage.removeItem('assembly_user');
    showAuth();
}

// ═══════════════════════════════════════════════════════════════════
// VIEW MANAGEMENT
// ═══════════════════════════════════════════════════════════════════

function showAuth() {
    document.getElementById('auth-view').style.display = 'flex';
    document.getElementById('app-view').style.display = 'none';
}

function showApp() {
    document.getElementById('auth-view').style.display = 'none';
    document.getElementById('app-view').style.display = 'flex';

    // Set user info
    if (state.user) {
        document.getElementById('user-name').textContent = state.user.name;
        document.getElementById('user-avatar').textContent = state.user.name.charAt(0).toUpperCase();
    }

    loadConversations();
    startNewChat();
}

function showWelcome() {
    document.getElementById('welcome-state').style.display = 'flex';
    document.getElementById('chat-messages').style.display = 'none';
    document.getElementById('execution-workspace').style.display = 'none';
}

function showChat() {
    document.getElementById('welcome-state').style.display = 'none';
    document.getElementById('chat-messages').style.display = 'block';
    document.getElementById('execution-workspace').style.display = 'none';
}

function showWorkspace() {
    document.getElementById('execution-workspace').style.display = 'block';
}

function hideWorkspace() {
    document.getElementById('execution-workspace').style.display = 'none';
}

// ═══════════════════════════════════════════════════════════════════
// CONVERSATIONS
// ═══════════════════════════════════════════════════════════════════

async function loadConversations() {
    try {
        const res = await fetch(`${API}/api/conversations/`, {
            headers: { 'Authorization': `Bearer ${state.token}` },
        });
        if (res.ok) {
            state.conversations = await res.json();
            renderConversationList();
        }
    } catch (err) {
        console.error('Failed to load conversations:', err);
    }
}

function renderConversationList() {
    const list = document.getElementById('conversation-list');
    list.innerHTML = '';

    state.conversations.forEach(conv => {
        const item = document.createElement('div');
        item.className = `conv-item${conv.id === state.currentConversationId ? ' active' : ''}`;
        item.innerHTML = `
            <div class="conv-item-icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
                </svg>
            </div>
            <div class="conv-item-text">${escapeHtml(conv.title)}</div>
        `;
        item.addEventListener('click', () => loadConversation(conv.id));
        list.appendChild(item);
    });
}

async function loadConversation(conversationId) {
    state.currentConversationId = conversationId;
    renderConversationList();

    try {
        const res = await fetch(`${API}/api/conversations/${conversationId}`, {
            headers: { 'Authorization': `Bearer ${state.token}` },
        });

        if (res.ok) {
            const conv = await res.json();
            showChat();
            renderMessages(conv.messages);
        }
    } catch (err) {
        console.error('Failed to load conversation:', err);
    }
}

function renderMessages(messages) {
    const container = document.getElementById('chat-messages');
    container.innerHTML = '';

    messages.forEach(msg => {
        appendMessage(msg.role, msg.content, msg.sources);
    });

    scrollToBottom();
}

function appendMessage(role, content, sources = null) {
    const container = document.getElementById('chat-messages');

    const messageEl = document.createElement('div');
    messageEl.className = `message message-${role}`;

    if (role === 'user') {
        messageEl.innerHTML = `
            <div class="message-content">${escapeHtml(content)}</div>
        `;
    } else {
        let sourcesHtml = '';
        if (sources && sources.length > 0) {
            sourcesHtml = `
                <div class="message-sources">
                    <div class="message-sources-title">Sources</div>
                    ${sources.map((s, i) => `
                        <div class="source-item">
                            <span class="source-number">[${i + 1}]</span>
                            <div>
                                <a class="source-link" href="${escapeHtml(s.url || '#')}" target="_blank" rel="noopener">${escapeHtml(s.title || 'Source')}</a>
                                ${s.snippet ? `<div class="source-snippet">${escapeHtml(s.snippet)}</div>` : ''}
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        messageEl.innerHTML = `
            <div class="message-avatar">
                <svg width="18" height="18" viewBox="0 0 48 48" fill="none">
                    <circle cx="24" cy="16" r="4" fill="white" opacity="0.9"/>
                    <circle cx="14" cy="30" r="4" fill="white" opacity="0.7"/>
                    <circle cx="34" cy="30" r="4" fill="white" opacity="0.7"/>
                    <line x1="24" y1="16" x2="14" y2="30" stroke="white" stroke-width="1.5" opacity="0.5"/>
                    <line x1="24" y1="16" x2="34" y2="30" stroke="white" stroke-width="1.5" opacity="0.5"/>
                    <line x1="14" y1="30" x2="34" y2="30" stroke="white" stroke-width="1.5" opacity="0.5"/>
                </svg>
            </div>
            <div class="message-content">
                ${formatAnswer(content)}
                ${sourcesHtml}
            </div>
        `;
    }

    container.appendChild(messageEl);
    scrollToBottom();
}

// ═══════════════════════════════════════════════════════════════════
// QUESTION SUBMISSION
// ═══════════════════════════════════════════════════════════════════

function handleInputChange() {
    const input = document.getElementById('question-input');
    const btn = document.getElementById('send-btn');
    btn.disabled = !input.value.trim() || state.isExecuting;

    // Auto-resize textarea
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 150) + 'px';
}

async function submitQuestion() {
    const input = document.getElementById('question-input');
    const question = input.value.trim();
    if (!question || state.isExecuting) return;

    state.isExecuting = true;
    input.value = '';
    handleInputChange();

    // Show chat and add user message
    showChat();
    appendMessage('user', question);
    showWorkspace();
    resetWorkspace();

    try {
        const res = await fetch(`${API}/api/executions/`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${state.token}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                question,
                time_budget_minutes: state.selectedTimeBudget,
                conversation_id: state.currentConversationId,
            }),
        });

        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.detail || 'Failed to submit question');
        }

        const execution = await res.json();
        state.currentExecutionId = execution.id;
        state.currentConversationId = execution.conversation_id;

        // Connect WebSocket for real-time progress
        connectWebSocket(execution.id);

        // Start timer
        startTimer(state.selectedTimeBudget * 60);

        // Refresh conversation list
        loadConversations();

    } catch (err) {
        console.error('Submission error:', err);
        appendMessage('assistant', `Error: ${err.message}`);
        hideWorkspace();
        state.isExecuting = false;
    }
}

function startNewChat() {
    state.currentConversationId = null;
    state.currentExecutionId = null;
    renderConversationList();
    showWelcome();
    document.getElementById('question-input').focus();
}

// ═══════════════════════════════════════════════════════════════════
// WEBSOCKET — Real-Time Progress
// ═══════════════════════════════════════════════════════════════════

function connectWebSocket(executionId) {
    if (state.ws) {
        state.ws.close();
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/executions/ws/${executionId}?token=${state.token}`;

    state.ws = new WebSocket(wsUrl);

    state.ws.onopen = () => {
        console.log('WebSocket connected');
        // Send periodic pings
        state.wsPingInterval = setInterval(() => {
            if (state.ws && state.ws.readyState === WebSocket.OPEN) {
                state.ws.send('ping');
            }
        }, 30000);
    };

    state.ws.onmessage = (event) => {
        if (event.data === 'pong') return;
        try {
            const data = JSON.parse(event.data);
            handleProgressEvent(data);
        } catch (err) {
            console.error('WS parse error:', err);
        }
    };

    state.ws.onclose = () => {
        console.log('WebSocket disconnected');
        clearInterval(state.wsPingInterval);
    };

    state.ws.onerror = (err) => {
        console.error('WebSocket error:', err);
    };
}

function handleProgressEvent(event) {
    const { event_type, data } = event;

    switch (event_type) {
        case 'status_update':
            updateWorkspaceStatus(data);
            addFeedItem(data.status || 'working', data.message);
            break;

        case 'agent_update':
            updateAgentCards(data.agents);
            if (data.message) addFeedItem('solving', data.message);
            break;

        case 'consensus_update':
            updateConsensus(data.consensus_score);
            if (data.time_remaining_formatted) {
                document.getElementById('workspace-timer').textContent = data.time_remaining_formatted;
            }
            addFeedItem('debating', `Consensus: ${Math.round((data.consensus_score || 0) * 100)}% — ${data.decision || ''}`);
            break;

        case 'answer_ready':
            handleAnswerReady(data);
            break;

        case 'error':
            addFeedItem('error', data.message || 'An error occurred');
            // Check if this is a provider availability error
            const errMsg = data.message || 'An error occurred during execution.';
            const isProviderError = errMsg.includes('providers to be live') || errMsg.includes('providers');
            handleAnswerReady({
                answer: isProviderError
                    ? '⚠️ ' + errMsg + '\n\nPlease ensure at least 3 AI provider API keys (Gemini, Groq, Cerebras, OpenRouter, Hugging Face) are configured in the server\'s .env file.'
                    : errMsg,
                sources: [],
                status: 'failed',
                agent_count: 0,
                providers_used: [],
            });
            break;
    }
}

// ═══════════════════════════════════════════════════════════════════
// WORKSPACE UI UPDATES
// ═══════════════════════════════════════════════════════════════════

function resetWorkspace() {
    document.getElementById('workspace-status-text').textContent = 'AI Team Working';
    document.getElementById('workspace-timer').textContent = '--:--';
    document.getElementById('workspace-agents').innerHTML = '';
    document.getElementById('consensus-bar').style.width = '0%';
    document.getElementById('consensus-value').textContent = '0%';
    document.getElementById('workspace-feed').innerHTML = '<div class="feed-title">Activity</div>';
}

function updateWorkspaceStatus(data) {
    const statusMap = {
        planning: 'Analyzing Question',
        forming_team: 'Forming Expert Team',
        researching: 'Searching for Evidence',
        solving: 'Agents Solving',
        debating: 'Cross-Agent Debate',
        synthesizing: 'Synthesizing Answer',
    };

    const statusText = statusMap[data.status] || data.message || 'Working';
    document.getElementById('workspace-status-text').textContent = statusText;

    if (data.time_remaining_formatted) {
        document.getElementById('workspace-timer').textContent = data.time_remaining_formatted;
    }
}

function updateAgentCards(agents) {
    const container = document.getElementById('workspace-agents');
    container.innerHTML = '';

    if (!agents) return;

    const roleEmoji = {
        solver: '🧠',
        researcher: '🔍',
        critic: '⚡',
        synthesizer: '✨',
    };

    agents.forEach(agent => {
        const card = document.createElement('div');
        card.className = 'agent-card active';
        card.innerHTML = `
            <div class="agent-card-header">
                <div class="agent-status-dot"></div>
                <span class="agent-role">${roleEmoji[agent.agent_type] || '🤖'} ${capitalize(agent.agent_type)}</span>
            </div>
            <div class="agent-model">${agent.model}</div>
            <div class="agent-provider" style="font-size:0.7rem;opacity:0.6;margin-top:2px;">via ${capitalize(agent.provider_name || 'unknown')}</div>
            <div class="agent-activity">${agent.role_description || 'Working...'}</div>
        `;
        container.appendChild(card);
    });
}

function updateConsensus(score) {
    const pct = Math.round((score || 0) * 100);
    document.getElementById('consensus-bar').style.width = pct + '%';
    document.getElementById('consensus-value').textContent = pct + '%';
}

function addFeedItem(type, message) {
    const feed = document.getElementById('workspace-feed');
    const now = new Date();
    const time = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });

    const item = document.createElement('div');
    item.className = 'feed-item';
    item.innerHTML = `
        <span class="feed-time">${time}</span>
        <div class="feed-dot ${type}"></div>
        <span>${escapeHtml(message)}</span>
    `;

    feed.appendChild(item);
    feed.scrollTop = feed.scrollHeight;
}

function handleAnswerReady(data) {
    state.isExecuting = false;
    clearInterval(state.timerInterval);

    if (state.ws) {
        state.ws.close();
        state.ws = null;
    }

    // Mark agents as completed
    document.querySelectorAll('.agent-card').forEach(card => {
        card.classList.remove('active');
        card.classList.add('completed');
    });

    // Update status
    document.getElementById('workspace-status-text').textContent = 
        data.status === 'failed' ? 'Execution Failed' : 'Answer Ready';
    document.querySelector('.pulse-dot').style.background = 
        data.status === 'failed' ? 'var(--error)' : 'var(--success)';

    // Build agent/provider info badge
    let answerContent = data.answer || '';
    const agentCount = data.agent_count || 0;
    const providersUsed = data.providers_used || [];

    // If answer doesn't already contain the footer (from synthesizer), add one
    if (agentCount > 0 && !answerContent.includes('AI agents powered by')) {
        const providerNames = {
            gemini: 'Gemini', groq: 'Groq', cerebras: 'Cerebras',
            openrouter: 'OpenRouter', huggingface: 'Hugging Face',
        };
        const displayNames = providersUsed.map(p => providerNames[p] || p).join(', ');
        answerContent += `\n\n---\n\uD83E\uDD16 This answer was assembled by ${agentCount} AI agents powered by ${displayNames || 'multiple providers'}.`;
    }

    // Small delay then show answer
    setTimeout(() => {
        hideWorkspace();
        appendMessage('assistant', answerContent, data.sources);
        handleInputChange();
        loadConversations();
    }, 1500);
}

// ═══════════════════════════════════════════════════════════════════
// TIMER
// ═══════════════════════════════════════════════════════════════════

function startTimer(totalSeconds) {
    let remaining = totalSeconds;
    const timerEl = document.getElementById('workspace-timer');

    state.timerInterval = setInterval(() => {
        remaining = Math.max(0, remaining - 1);
        const mins = Math.floor(remaining / 60);
        const secs = remaining % 60;
        timerEl.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;

        if (remaining <= 0) {
            clearInterval(state.timerInterval);
        }
    }, 1000);
}

// ═══════════════════════════════════════════════════════════════════
// UTILITIES
// ═══════════════════════════════════════════════════════════════════

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function capitalize(str) {
    return str ? str.charAt(0).toUpperCase() + str.slice(1) : '';
}

function formatAnswer(text) {
    if (!text) return '';
    // Convert line breaks to paragraphs
    const escaped = escapeHtml(text);
    const paragraphs = escaped.split(/\n\n+/).filter(p => p.trim());
    if (paragraphs.length <= 1) {
        return escaped.replace(/\n/g, '<br>');
    }
    return paragraphs.map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`).join('');
}

function scrollToBottom() {
    const container = document.getElementById('chat-messages');
    if (container) {
        setTimeout(() => {
            container.scrollTop = container.scrollHeight;
        }, 50);
    }
}
