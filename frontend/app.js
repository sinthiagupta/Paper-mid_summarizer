const bg = document.getElementById('bg-container');
const cursor = document.getElementById('cursor');
const logo = document.getElementById('typewriter-logo');

// 1. INSTANT CURSOR
let mouseX = 0, mouseY = 0;
window.addEventListener('mousemove', (e) => {
    mouseX = e.clientX;
    mouseY = e.clientY;
    updateProximity(e.clientX, e.clientY);
});

function updateCursor() {
    cursor.style.transform = `translate3d(${mouseX}px, ${mouseY}px, 0)`;
    requestAnimationFrame(updateCursor);
}
updateCursor();

// 2. ONE-TIME STARTUP TYPEWRITER
const brand = "PAPERMIND";
let charIndex = 0;
function handleTypewriter() {
    if (charIndex <= brand.length) {
        const text = brand.substring(0, charIndex);
        logo.innerHTML = text;
        logo.setAttribute('data-text', text);
        charIndex++;
        setTimeout(handleTypewriter, 120);
    }
}
handleTypewriter();

// 3. GALAXY ENGINE
const COLORS = ['#00F5D4', '#A855F7'];
const stars = [];
for (let i = 0; i < 35; i++) {
    const star = document.createElement('div');
    star.className = 'stardust';
    star.style.color = COLORS[Math.floor(Math.random() * COLORS.length)];
    star.style.top = Math.random() * 100 + '%';
    star.style.left = Math.random() * 100 + '%';
    const size = (Math.random() * 60 + 40) + 'px';
    star.style.width = size; star.style.height = size;
    bg.appendChild(star);
    stars.push({ element: star });
}
function updateProximity(mx, my) {
    stars.forEach(s => {
        const rect = s.element.getBoundingClientRect();
        const sx = rect.left + rect.width / 2;
        const sy = rect.top + rect.height / 2;
        const dist = Math.hypot(mx - sx, my - sy);
        if (dist < 180) s.element.classList.add('glow');
        else s.element.classList.remove('glow');
    });
}

// ==============================================
// CONFIG
// ==============================================
// Automatically detect environment
const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
const API = isLocal ? 'http://localhost:8000' : 'https://papermind-backend.onrender.com'; // We will update this later if Render gives a different URL
let authToken = sessionStorage.getItem('pm_token') || null;
let activePaperId = null;

// ==============================================
// NAVIGATION & MODALS
// ==============================================
document.addEventListener('DOMContentLoaded', () => {
    console.log("[SYSTEM] Papermind Frontend Initialized.");
    
    document.getElementById('nav-about')?.addEventListener('click', () => {
        document.getElementById('about-overlay').classList.add('active');
    });

    document.getElementById('nav-login')?.addEventListener('click', () => {
        if (authToken) { enterWorkspace(); return; }
        document.getElementById('auth-overlay').classList.add('active');
        switchTab('login');
    });

    document.getElementById('btn-get-started')?.addEventListener('click', () => {
        if (authToken) { enterWorkspace(); return; }
        document.getElementById('auth-overlay').classList.add('active');
        switchTab('join');
    });
});

function toggleChat() {
    const panel = document.getElementById('chat-panel');
    if (panel) panel.classList.toggle('open');
}

function toggleHistory() {
    const drawer = document.getElementById('history-drawer');
    if (drawer) {
        drawer.classList.toggle('open');
        if (drawer.classList.contains('open')) {
            loadHistory();
        }
    }
}

async function loadHistory() {
    const list = document.getElementById('history-list');
    if (!list) return;
    try {
        const res = await fetch(`${API}/papers`, { headers: { 'Authorization': `Bearer ${authToken}` } });
        const papers = await res.json();
        if (!papers.length) {
            list.innerHTML = '<p style="color:rgba(255,255,255,0.3);padding:20px;font-size:13px;">No papers uploaded yet.</p>';
            return;
        }
        list.innerHTML = papers.map(p => {
            const safeName = (p.file_name || p.paper_id || 'Paper').replace(/'/g, "\\'");
            return `
                <div class="history-item" style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding-right:8px;">
                    <div style="display:flex;align-items:center;gap:10px;flex:1;min-width:0;cursor:pointer;" onclick="selectPaper('${p.paper_id}','${safeName}')">
                        <span class="h-icon">📄</span>
                        <p class="h-title" style="margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${p.file_name || p.paper_id}</p>
                    </div>
                    <button onclick="deletePaper('${p.paper_id}', event)" title="Delete this paper"
                        style="flex-shrink:0;background:rgba(239,68,68,0.12);color:#f87171;border:1px solid rgba(239,68,68,0.25);padding:5px 9px;border-radius:6px;font-size:13px;cursor:pointer;transition:all 0.2s;"
                        onmouseover="this.style.background='rgba(239,68,68,0.3)'" onmouseout="this.style.background='rgba(239,68,68,0.12)'">🗑</button>
                </div>`;
        }).join('');
    } catch (err) { 
        console.error("History failed:", err); 
        list.innerHTML = '<p class="error">Failed to load history.</p>';
    }
}

async function deletePaper(paperId, event) {
    event.stopPropagation(); // Don't trigger selectPaper
    if (!confirm('Delete this paper and all its data permanently? This cannot be undone.')) return;

    try {
        const res = await fetch(`${API}/papers/${paperId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (!res.ok) throw new Error('Delete failed');

        // If the deleted paper was the active one, reset the workspace
        if (activePaperId === paperId) {
            closeActivePaper();
            activePaperId = null;
        }
        // Refresh the history drawer list
        loadHistory();
    } catch (err) {
        alert('Could not delete paper: ' + err.message);
    }
}

function closeAll() {
    document.querySelectorAll('.overlay').forEach(o => o.classList.remove('active'));
}

function switchTab(tab) {
    // Clear all inputs on switch to prevent "already registered" confusion from ghost data
    document.querySelectorAll('.panel-form input').forEach(input => input.value = '');
    updateStrength(''); // Reset strength bars

    if (tab === 'login') {
        document.getElementById('panel-login').classList.add('active');
        document.getElementById('panel-signup').classList.remove('active');
    } else {
        document.getElementById('panel-signup').classList.add('active');
        document.getElementById('panel-login').classList.remove('active');
    }
}

function updateStrength(val) {
    const bars = [document.getElementById('s1'), document.getElementById('s2'), document.getElementById('s3'), document.getElementById('s4')];
    bars.forEach(b => { if (b) b.className = 'strength-bar'; });
    if (val.length > 0) {
        if (val.length < 5) bars[0]?.classList.add('weak');
        else if (val.length < 8) { bars[0]?.classList.add('fair'); bars[1]?.classList.add('fair'); }
        else { bars.forEach(b => { if (b) b.classList.add('strong'); }); }
    }
}

// ==============================================
// AUTH
// ==============================================
async function handleSignup() {
    const fn = document.getElementById('join-first-name').value;
    const ln = document.getElementById('join-last-name').value;
    const email = document.getElementById('join-email').value;
    const pwd = document.getElementById('join-password').value;
    const phone = document.getElementById('join-phone').value;

    try {
        const res = await fetch(`${API}/auth/signup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password: pwd, first_name: fn, last_name: ln, phone })
        });
        if (!res.ok) {
            const e = await res.json();
            throw new Error(e.detail);
        }
        alert("Account created successfully! Please log in.");
        document.getElementById('join-password').value = '';
        switchTab('login');
    } catch (err) {
        alert(err.message);
    }
}

async function handleLogin() {
    const btn = document.querySelector('#panel-login .btn-submit');
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;
    try {
        const fd = new FormData();
        fd.append('username', email); fd.append('password', password);
        const res = await fetch(`${API}/auth/login`, { method: 'POST', body: fd });
        if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
        const data = await res.json();
        authToken = data.access_token;
        sessionStorage.setItem('pm_token', authToken);
        sessionStorage.setItem('pm_email', email);
        enterWorkspace();
    } catch (err) { alert(`Error: ${err.message}`); }
}

function enterWorkspace() {
    sessionStorage.setItem('current_view', 'workspace');
    document.querySelectorAll('.overlay').forEach(o => o.classList.remove('active'));
    document.querySelector('nav').style.display = 'none';
    document.querySelector('main').style.display = 'none';
    document.getElementById('bg-container').style.display = 'none';
    document.getElementById('workspace-view').style.display = 'block';
    const emailStr = sessionStorage.getItem('pm_email') || '';
    document.getElementById('ws-user-email').innerHTML = '👤&nbsp;&nbsp;' + emailStr;
    setupUploadZone();
    document.getElementById('chat-fab').onclick = () => document.getElementById('chat-panel').classList.toggle('open');
    document.getElementById('btn-history').onclick = toggleHistory;
}

function exitWorkspace() {
    sessionStorage.setItem('current_view', 'dashboard');
    document.querySelector('nav').style.display = '';
    document.querySelector('main').style.display = '';
    document.getElementById('bg-container').style.display = '';
    document.getElementById('workspace-view').style.display = 'none';
}

function logOut() {
    sessionStorage.removeItem('pm_token');
    sessionStorage.removeItem('pm_email');
    sessionStorage.removeItem('current_view');
    authToken = null;
    activePaperId = null;
    exitWorkspace();
}

if (authToken && sessionStorage.getItem('current_view') !== 'dashboard') {
    document.addEventListener('DOMContentLoaded', enterWorkspace);
}

// ==============================================
// UPLOAD
// ==============================================
function setupUploadZone() {
    const input = document.getElementById('file-input');
    if (!input) return;

    // We removed the zone.onclick here!
    // The <label for="file-input"> in your HTML already handles the click for us.

    input.onchange = (e) => {
        const file = e.target.files[0];
        if (file) {
            // Strictly enforce the 50MB max file size in frontend
            if (file.size > 50 * 1024 * 1024) {
                alert("This file is too large. Papers must be under 50MB.");
                e.target.value = '';
                return;
            }
            uploadFile(file);
            // Clear the input so you can upload the same file again if needed
            e.target.value = '';
        }
    };
}


async function uploadFile(file) {
    const zone = document.getElementById('upload-zone');
    zone.innerHTML = `<div class="upload-icon">⏳</div><h2 class="upload-title">Analyzing "${file.name}"…</h2><p class="upload-sub">AI is reading and reporting...</p>`;
    const fd = new FormData();
    fd.append('file', file);
    try {
        const res = await fetch(`${API}/upload`, {
            method: 'POST', headers: { 'Authorization': `Bearer ${authToken}` }, body: fd
        });

        if (!res.ok) {
            if (res.status === 401) {
                throw new Error("Session expired. Please log out and log in again.");
            }
            const e = await res.json();
            throw new Error(e.detail || "Upload failed");
        }

        const data = await res.json();
        activePaperId = data.paper_id;
        zone.innerHTML = `<div class="upload-icon">✅</div><h2 class="upload-title">${file.name.replace('.pdf', '')}</h2><p class="upload-sub">Ready to chat</p>`;
        document.getElementById('results-paper-name').textContent = file.name.replace('.pdf', '');

        // Deep Resilient Markdown Extraction
        let summaryText = data.summary || 'No summary returned.';

        const extractSummary = (raw) => {
            if (!raw) return "No data available.";
            if (typeof raw === 'object') {
                return raw.summary || raw.text || JSON.stringify(raw);
            }
            try {
                // If it looks like a JSON string, try to parse it
                if (raw.trim().startsWith('{') || raw.trim().startsWith('[')) {
                    let parsed = JSON.parse(raw);
                    return extractSummary(parsed); // Recursive check
                }
            } catch (e) { }
            return raw;
        };

        const finalSummary = extractSummary(summaryText);
        document.getElementById('result-summary').innerHTML = marked.parse(finalSummary);

        renderAssets(data.paper_id);
        document.getElementById('results-section').style.display = 'flex';
        document.getElementById('results-section').scrollIntoView({ behavior: 'smooth' });
    } catch (err) {
        zone.innerHTML = `<div class="upload-icon">❌</div><h2 class="upload-title">Upload Failed</h2><p class="upload-sub">${err.message}</p>`;
        alert(err.message);
    }
}

// ==============================================
// CHAT & ASSETS
// ==============================================
async function renderAssets(paperId) {
    const imgGallery = document.getElementById('image-gallery');
    const tableGrid = document.getElementById('tables-grid');
    try {
        const res = await fetch(`${API}/papers/${paperId}/assets`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        const data = await res.json();
        imgGallery.innerHTML = data.images.map(img => `<div class="img-container"><img src="${API}/extracted_images/${img}" onclick="window.open('${API}/extracted_images/${img}')"></div>`).join('');
        document.getElementById('figures-section').style.display = data.images.length ? 'flex' : 'none';
        tableGrid.innerHTML = data.tables.map(t => `<div class="table-card"><div class="markdown-body">${marked.parse(t)}</div></div>`).join('');
        document.getElementById('tables-section').style.display = data.tables.length ? 'flex' : 'none';
    } catch (err) { console.error(err); }
}

async function sendChat() {
    const input = document.getElementById('chat-input');
    const msgs = document.getElementById('chat-messages');
    const q = input.value.trim();
    if (!q) return;

    // Show user message
    msgs.innerHTML += `<div class="msg user-msg">${q}</div>`;
    input.value = '';
    msgs.scrollTop = msgs.scrollHeight;

    // Show loading bubble
    const loadingId = 'loading-' + Date.now();
    msgs.innerHTML += `<div class="msg bot-msg" id="${loadingId}" style="opacity:0.5;font-style:italic;">⏳ Thinking...</div>`;
    msgs.scrollTop = msgs.scrollHeight;

    try {
        const res = await fetch(`${API}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${authToken}` },
            body: JSON.stringify({ question: q, paper_id: activePaperId })
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Server error');
        }

        const data = await res.json();

        // Safely extract string — prevent [object Object]
        let answerText = data.answer;
        if (typeof answerText !== 'string') {
            answerText = answerText?.text || answerText?.content || JSON.stringify(answerText);
        }

        // Remove loading bubble and render Markdown answer
        document.getElementById(loadingId)?.remove();
        const botDiv = document.createElement('div');
        botDiv.className = 'msg bot-msg markdown-body';
        botDiv.innerHTML = marked.parse(answerText);
        msgs.appendChild(botDiv);

    } catch (err) {
        document.getElementById(loadingId)?.remove();
        msgs.innerHTML += `<div class="msg bot-msg" style="color:#f87171;">❌ Error: ${err.message}</div>`;
    }

    msgs.scrollTop = msgs.scrollHeight;
}

// Select a paper from the history drawer
async function selectPaper(paperId, name) {
    activePaperId = paperId;
    document.getElementById('history-drawer').classList.remove('open');
    await fetch(`${API}/papers/${paperId}/select`, { method: 'POST', headers: { 'Authorization': `Bearer ${authToken}` } });
    const sr = await fetch(`${API}/papers/${paperId}/summary`, { headers: { 'Authorization': `Bearer ${authToken}` } });
    const sd = await sr.json();
    document.getElementById('results-paper-name').textContent = name.replace('.pdf', '');

    // Deep Resilient Markdown Extraction code repeated for selectPaper
    const extractSummary = (raw) => {
        if (!raw) return "No data available.";
        if (typeof raw === 'object') { return raw.summary || raw.text || JSON.stringify(raw); }
        try {
            if (raw.trim().startsWith('{') || raw.trim().startsWith('[')) {
                let parsed = JSON.parse(raw);
                return extractSummary(parsed);
            }
        } catch (e) { }
        return raw;
    };

    const finalSummary = extractSummary(sd.summary);
    document.getElementById('result-summary').innerHTML = marked.parse(finalSummary);
    renderAssets(paperId);
    document.getElementById('results-section').style.display = 'flex';
    document.getElementById('chat-panel').classList.add('open');
}

// ==============================================
// CLEAR CHAT + SUMMARY (Start Again)
// ==============================================
async function clearChat() {
    if (!activePaperId) {
        alert("No paper is active. Upload a paper first.");
        return;
    }
    if (!confirm("Clear all chat history and summary for this paper? This cannot be undone.")) return;

    try {
        // 1. Wipe DB history via the API
        await fetch(`${API}/history/${activePaperId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
    } catch (err) {
        console.warn("Could not clear server history:", err);
    }

    // 2. Reset chat messages UI
    const msgs = document.getElementById('chat-messages');
    if (msgs) {
        msgs.innerHTML = '<div class="msg bot-msg">Upload a paper and I\'ll answer your questions about it.</div>';
    }

    // 3. Clear the summary panel
    const summaryEl = document.getElementById('result-summary');
    if (summaryEl) {
        summaryEl.innerHTML = '<p style="color:rgba(255,255,255,0.3);font-style:italic;">Summary cleared. Re-upload the paper to regenerate.</p>';
    }
    document.getElementById('results-paper-name').textContent = 'Analysis Complete';
    document.getElementById('figures-section').style.display = 'none';
    document.getElementById('tables-section').style.display = 'none';

    console.log("[CLEAR] Chat history and summary wiped.");
}

// ==============================================
// UI CONTROL
// ==============================================
function closeActivePaper() {
    activePaperId = null;
    document.getElementById('results-section').style.display = 'none';
    
    // Reset upload zone visually AND restore the file input
    const zone = document.getElementById('upload-zone');
    zone.innerHTML = `
        <div class="upload-icon">📄</div>
        <h2 class="upload-title">Drop your research paper here</h2>
        <p class="upload-sub">Supports PDF · Max 50MB</p>
        <label class="upload-btn" for="file-input">Choose File</label>
        <input type="file" id="file-input" accept=".pdf" hidden>
    `;
    
    // CRITICAL: Re-attach the listeners to the new input element
    setupUploadZone();
    
    document.getElementById('chat-panel').classList.remove('open');
    document.getElementById('workspace-view').scrollTo({ top: 0, behavior: 'smooth' });
}
