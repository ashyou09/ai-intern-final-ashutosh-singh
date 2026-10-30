/**
 * AI Research Assistant — Frontend Logic
 * Handles API calls, result rendering, rich text formatting, and file export.
 */

// The backend serves this page, so API calls are same-origin. When the HTML
// file is opened directly from disk, fall back to the default local server.
const API_BASE = window.location.protocol === "file:" ? "http://localhost:8000" : "";

// --- DOM Elements ---
const topicInput = document.getElementById("topic-input");
const researchBtn = document.getElementById("research-btn");
const charCount = document.getElementById("char-count");
const loadingSection = document.getElementById("loading");
const errorSection = document.getElementById("error-section");
const errorMsg = document.getElementById("error-msg");
const errorDismiss = document.getElementById("error-dismiss");
const resultsSection = document.getElementById("results");
const summaryContent = document.getElementById("summary-content");
const resultsTopic = document.getElementById("results-topic");
const exportTxtBtn = document.getElementById("export-txt");
const exportPdfBtn = document.getElementById("export-pdf");
const exportMdBtn = document.getElementById("export-md");
const copyBtn = document.getElementById("copy-btn");
const copyLabel = document.getElementById("copy-label");
const newResearchBtn = document.getElementById("new-research-btn");
const stopBtn = document.getElementById("stop-btn");
const mainLogo = document.getElementById("main-logo");

// Loading step elements
const stepPlan = document.getElementById("step-plan");
const stepSearch = document.getElementById("step-search");
const loadingText = document.getElementById("loading-text");
const planQueries = document.getElementById("plan-queries");
const stepAnalyze = document.getElementById("step-analyze");
const stepWrite = document.getElementById("step-write");

// --- State ---
let currentTopic = "";
let currentRawSummary = "";
let currentSources = [];
let abortController = null;

// =========================================================================
// Bring-your-own-key settings — stored only in this browser
// =========================================================================
const LLM_STORAGE_KEY = "ara.llm";
const FALLBACK_PROVIDERS = [
    { id: "openrouter", name: "OpenRouter", default_model: "openai/gpt-oss-120b:free", key_url: "https://openrouter.ai/keys" },
    { id: "groq", name: "Groq", default_model: "llama-3.3-70b-versatile", key_url: "https://console.groq.com/keys" },
    { id: "openai", name: "OpenAI", default_model: "gpt-4o-mini", key_url: "https://platform.openai.com/api-keys" },
    { id: "custom", name: "Custom (OpenAI-compatible)", default_model: "", key_url: "" },
];

const settingsBtn = document.getElementById("settings-btn");
const modelBadgeText = document.getElementById("model-badge-text");
const settingsDialog = document.getElementById("settings-dialog");
const settingsForm = document.getElementById("settings-form");
const settingsError = document.getElementById("settings-error");
const llmProvider = document.getElementById("llm-provider");
const llmKey = document.getElementById("llm-key");
const llmKeyToggle = document.getElementById("llm-key-toggle");
const llmKeyLink = document.getElementById("llm-key-link");
const llmModel = document.getElementById("llm-model");
const llmBaseRow = document.getElementById("llm-base-row");
const llmBaseUrl = document.getElementById("llm-base-url");
const llmRemember = document.getElementById("llm-remember");
const noticeBar = document.getElementById("notice-bar");
const noticeText = document.getElementById("notice-text");

let providers = FALLBACK_PROVIDERS;

function storageGet(storage) {
    try { return JSON.parse(storage.getItem(LLM_STORAGE_KEY) || "null"); } catch (_) { return null; }
}

/** The saved user model settings, or null to use the server models. */
function loadUserLLM() {
    return storageGet(localStorage) || storageGet(sessionStorage);
}

function saveUserLLM(llm, remember) {
    try {
        localStorage.removeItem(LLM_STORAGE_KEY);
        sessionStorage.removeItem(LLM_STORAGE_KEY);
        if (llm) (remember ? localStorage : sessionStorage).setItem(LLM_STORAGE_KEY, JSON.stringify(llm));
    } catch (_) { /* storage blocked — settings last for this page only */ }
    sessionLLM = llm;
}

let sessionLLM = loadUserLLM();

function providerById(id) {
    return providers.find((p) => p.id === id) || providers[0];
}

function updateModelBadge() {
    if (sessionLLM) {
        const p = providerById(sessionLLM.provider);
        modelBadgeText.textContent = `Your ${p.name.replace(/ \(.*\)$/, "")} key`;
        settingsBtn.classList.add("is-custom");
    } else {
        modelBadgeText.textContent = "Server models";
        settingsBtn.classList.remove("is-custom");
    }
}

function syncProviderFields() {
    const p = providerById(llmProvider.value);
    llmModel.placeholder = p.default_model ? `Default: ${p.default_model}` : "Model name, e.g. llama3-70b";
    llmBaseRow.classList.toggle("hidden", p.id !== "custom");
    llmKeyLink.classList.toggle("hidden", !p.key_url);
    if (p.key_url) {
        llmKeyLink.href = p.key_url;
        llmKeyLink.textContent = `Get a ${p.name} key ↗`;
    }
}

async function loadProviders() {
    try {
        const res = await fetch(`${API_BASE}/providers`);
        if (res.ok) providers = await res.json();
    } catch (_) { /* keep the built-in list */ }
    llmProvider.innerHTML = "";
    providers.forEach((p) => {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = p.name;
        llmProvider.appendChild(opt);
    });
    updateModelBadge();
}

function openSettings() {
    const llm = sessionLLM;
    llmProvider.value = llm ? llm.provider : providers[0].id;
    llmKey.value = llm ? llm.api_key : "";
    llmModel.value = llm ? llm.model || "" : "";
    llmBaseUrl.value = llm ? llm.base_url || "" : "";
    llmRemember.checked = !!storageGet(localStorage);
    llmKey.type = "password";
    llmKeyToggle.textContent = "Show";
    settingsError.classList.add("hidden");
    syncProviderFields();
    settingsDialog.showModal();
    llmKey.focus();
}

function showSettingsError(msg) {
    settingsError.textContent = msg;
    settingsError.classList.remove("hidden");
}

settingsBtn.addEventListener("click", openSettings);
llmProvider.addEventListener("change", syncProviderFields);
document.getElementById("llm-cancel").addEventListener("click", () => settingsDialog.close());
llmKeyToggle.addEventListener("click", () => {
    const hidden = llmKey.type === "password";
    llmKey.type = hidden ? "text" : "password";
    llmKeyToggle.textContent = hidden ? "Hide" : "Show";
});

document.getElementById("llm-clear").addEventListener("click", () => {
    saveUserLLM(null, false);
    updateModelBadge();
    settingsDialog.close();
});

settingsForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const key = llmKey.value.trim();
    const provider = llmProvider.value;
    const model = llmModel.value.trim();
    const baseUrl = llmBaseUrl.value.trim();

    if (!key) return showSettingsError("Paste an API key, or use “Remove key” to go back to the server models.");
    if (/\s/.test(key) || key.length < 8) return showSettingsError("That API key does not look valid.");
    if (provider === "custom") {
        if (!/^https:\/\//i.test(baseUrl)) return showSettingsError("A custom provider needs an https:// base URL.");
        if (!model) return showSettingsError("A custom provider needs a model name.");
    }

    const llm = { provider, api_key: key, model };
    if (provider === "custom") llm.base_url = baseUrl;
    saveUserLLM(llm, llmRemember.checked);
    updateModelBadge();
    settingsDialog.close();
});

function showNotice(msg) {
    noticeText.textContent = msg;
    noticeBar.classList.remove("hidden");
}

function hideNotice() {
    noticeBar.classList.add("hidden");
    noticeText.textContent = "";
}

document.getElementById("notice-dismiss").addEventListener("click", hideNotice);
loadProviders();

// --- Character Counter ---
topicInput.addEventListener("input", () => {
    const len = topicInput.value.length;
    charCount.textContent = len;
    charCount.style.color = len > 450 ? (len > 500 ? "#fb7185" : "#f59e0b") : "";
});

// --- Enter key to submit ---
topicInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !researchBtn.disabled) {
        researchBtn.click();
    }
});

// --- Research Button ---
researchBtn.addEventListener("click", async () => {
    const topic = topicInput.value.trim();

    if (!topic) {
        showError("Please enter a research topic.");
        return;
    }

    if (topic.length > 500) {
        showError("Topic must be 500 characters or fewer.");
        return;
    }

    currentTopic = topic;
    currentRawSummary = "";
    currentSources = [];
    showLoading(true);
    hideError();
    hideNotice();
    hideResults();
    setBusy(true);

    abortController = new AbortController();

    try {
        const res = await fetch(`${API_BASE}/research`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(sessionLLM ? { topic, llm: sessionLLM } : { topic }),
            signal: abortController.signal,
        });

        if (!res.ok) {
            throw new Error(await readErrorMessage(res, "Research failed. Please try again."));
        }

        resultsTopic.textContent = currentTopic;
        summaryContent.innerHTML = '<span class="typing-cursor"></span>';
        setExportEnabled(false);

        await readEventStream(res, handleStreamEvent);

    } catch (err) {
        if (err.name === "AbortError") {
            // User pressed Stop — keep whatever was generated so far
            if (currentRawSummary) finishRender();
        } else {
            showError(err.message || "Failed to connect to the server.");
        }
    } finally {
        abortController = null;
        showLoading(false);
        setBusy(false);
    }
});

stopBtn.addEventListener("click", () => {
    if (abortController) abortController.abort();
});

/** Read an SSE response body and call onEvent(payload) for every `data:` event. */
async function readEventStream(res, onEvent) {
    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";

        for (const event of events) {
            if (!event.startsWith("data: ")) continue;
            let payload;
            try {
                payload = JSON.parse(event.substring(6));
            } catch (e) {
                console.error("Could not parse stream event", e, event);
                continue;
            }
            onEvent(payload); // may throw (e.g. server-side error) — propagates to caller
        }
    }
}

function handleStreamEvent(payload) {
    switch (payload.type) {
        case "status":
            setStage(payload.stage);
            if (payload.message) loadingText.textContent = payload.message;
            break;

        case "plan":
            renderPlan(payload.queries || []);
            break;

        case "content":
            if (resultsSection.classList.contains("hidden")) {
                loadingSection.classList.add("hidden");
                resultsSection.classList.remove("hidden");
            }
            currentRawSummary += payload.text;
            summaryContent.innerHTML = renderRichContent(currentRawSummary) + '<span class="typing-cursor"></span>';
            break;

        case "notice":
            showNotice(payload.message);
            break;

        case "reset":
            // A model failed mid-answer; the server is retrying with a fallback model
            currentRawSummary = "";
            summaryContent.innerHTML = '<span class="typing-cursor"></span>';
            break;

        case "done":
            currentSources = payload.sources || [];
            finishRender();
            setTimeout(() => {
                resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
            }, 100);
            break;

        case "error":
            throw new Error(payload.message || "Research failed.");
    }
}

/** Final render: remove the cursor, enable export, typeset math. */
function finishRender() {
    loadingSection.classList.add("hidden");
    resultsSection.classList.remove("hidden");
    summaryContent.innerHTML = renderRichContent(currentRawSummary);
    setExportEnabled(true);

    if (window.MathJax && MathJax.typesetPromise) {
        MathJax.typesetClear([summaryContent]);
        MathJax.typesetPromise([summaryContent]).catch((err) => console.log("MathJax error:", err));
    }
}

function setExportEnabled(enabled) {
    [exportPdfBtn, exportTxtBtn, exportMdBtn, copyBtn].forEach((btn) => { btn.disabled = !enabled; });
}

function setBusy(busy) {
    researchBtn.disabled = busy;
    researchBtn.classList.toggle("btn-loading", busy);
    mainLogo.classList.toggle("logo-pulse", busy);
    stopBtn.classList.toggle("hidden", !busy);
}

function renderPlan(queries) {
    planQueries.innerHTML = "";
    queries.forEach((q) => {
        const chip = document.createElement("span");
        chip.className = "plan-chip";
        chip.textContent = q;
        planQueries.appendChild(chip);
    });
    planQueries.classList.toggle("hidden", queries.length === 0);
}

function setStage(stage) {
    const order = [stepPlan, stepSearch, stepAnalyze, stepWrite];
    const index = { plan: 0, search: 1, analyze: 2, write: 3 }[stage];
    if (index === undefined) return;
    order.forEach((step, i) => {
        step.classList.toggle("done", i < index);
        step.classList.toggle("active", i === index);
    });
}

async function readErrorMessage(res, fallback) {
    try {
        const data = await res.json();
        if (typeof data.error === "string") return data.error;
        if (typeof data.detail === "string") return data.detail;
    } catch (_) {}
    return fallback;
}

// =========================================================================
// HTML safety helpers — everything rendered comes from the AI or from
// third-party web pages, so it must be escaped before going into innerHTML.
// =========================================================================
function escapeHtml(text) {
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function isSafeUrl(url) {
    return /^https?:\/\//i.test(url);
}

function linkHtml(url, label) {
    return `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" class="rc-link">${label}</a>`;
}

// =========================================================================
// Rich Content Renderer — Converts markdown to beautiful styled HTML
// =========================================================================
function renderRichContent(text) {
    if (!text) return '<p class="empty-state">No content available.</p>';

    // Normalize line endings
    text = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");

    // Split into lines for block-level processing
    const lines = text.split("\n");
    let html = "";
    let inList = false;      // false | "ul" | "ol"
    let inSources = false;   // inside the "## Sources" section → list items get #ref-N anchors
    let inTable = false;
    let tableRows = [];
    
    // Math block tracking
    let inMath = false;
    let mathLines = [];

    let inCodeBlock = false;
    let codeBlockLines = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const trimmed = line.trim();

        // ---- Code block detection (``` ... ```) ----
        if (trimmed.startsWith("```")) {
            if (inCodeBlock) {
                // End of code block — render it as styled pre/code
                inCodeBlock = false;
                const codeContent = codeBlockLines.join('\n')
                    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                html += `<pre class="rc-codeblock"><code>${codeContent}</code></pre>`;
                codeBlockLines = [];
            } else {
                if (inList) { html += `</${inList}>`; inList = false; }
                inCodeBlock = true;
                codeBlockLines = [];
            }
            continue;
        }
        if (inCodeBlock) {
            codeBlockLines.push(line);
            continue;
        }

        // Math block parsing \[ or $$
        if (trimmed === "\\[" || trimmed === "$$") {
            if (!inMath) {
                inMath = true;
                mathLines = [trimmed];
                continue;
            }
        }
        if (inMath) {
            mathLines.push(line);
            if (trimmed === "\\]" || trimmed === "$$") {
                inMath = false;
                html += `<div class="rc-math" style="overflow-x:auto; margin: 1rem 0;">${escapeHtml(mathLines.join('\n'))}</div>`;
                mathLines = [];
            }
            continue;
        }

        // Empty line
        if (!trimmed) {
            if (inList) { html += `</${inList}>`; inList = false; }
            if (inTable) { html += renderTable(tableRows); inTable = false; tableRows = []; }
            continue;
        }

        // Table rows (starts with |)
        if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
            // Skip separator rows like |---|---|
            if (/^\|[\s\-:|]+\|$/.test(trimmed)) {
                if (!inTable) { inTable = true; }
                continue;
            }
            if (!inTable) inTable = true;
            tableRows.push(trimmed);
            continue;
        } else if (inTable) {
            html += renderTable(tableRows);
            inTable = false;
            tableRows = [];
        }

        // Headers
        if (trimmed.startsWith("### ")) {
            if (inList) { html += `</${inList}>`; inList = false; }
            html += `<h4 class="rc-h3">${inlineFormat(trimmed.slice(4))}</h4>`;
            continue;
        }
        if (trimmed.startsWith("## ")) {
            if (inList) { html += `</${inList}>`; inList = false; }
            inSources = /^sources$/i.test(trimmed.slice(3).trim());
            html += `<h3 class="rc-h2">${inlineFormat(trimmed.slice(3))}</h3>`;
            continue;
        }
        if (trimmed.startsWith("# ")) {
            if (inList) { html += `</${inList}>`; inList = false; }
            html += `<h2 class="rc-h1">${inlineFormat(trimmed.slice(2))}</h2>`;
            continue;
        }

        // Horizontal rule
        if (/^-{3,}$/.test(trimmed) || /^\*{3,}$/.test(trimmed)) {
            if (inList) { html += `</${inList}>`; inList = false; }
            html += "<hr class='rc-hr'>";
            continue;
        }

        // Bullet list items
        if (/^\s*[-*•]\s+/.test(line)) {
            if (inList === "ol") { html += "</ol>"; inList = false; }
            if (!inList) { html += '<ul class="rc-list">'; inList = "ul"; }
            const content = line.replace(/^\s*[-*•]\s+/, "");
            html += `<li>${inlineFormat(content)}</li>`;
            continue;
        }

        // Numbered list items
        const numMatch = line.match(/^\s*(\d+)\.\s+(.*)$/);
        if (numMatch) {
            if (inList === "ul") { html += "</ul>"; inList = false; }
            if (!inList) { html += '<ol class="rc-list rc-ol">'; inList = "ol"; }
            const n = numMatch[1];
            const anchor = inSources ? ` id="ref-${n}"` : "";
            html += `<li value="${n}"${anchor}>${inlineFormat(numMatch[2])}</li>`;
            continue;
        }

        // Close list if we hit a non-list line
        if (inList) {
            html += `</${inList}>`;
            inList = false;
        }

        // Blockquote
        if (trimmed.startsWith("> ")) {
            html += `<blockquote class="rc-quote">${inlineFormat(trimmed.slice(2))}</blockquote>`;
            continue;
        }

        // Regular paragraph
        html += `<p class="rc-p">${inlineFormat(trimmed)}</p>`;
    }

    // Close any open lists/tables
    if (inList) html += `</${inList}>`;
    if (inTable) html += renderTable(tableRows);

    return html;
}

// --- Inline formatting (bold, italic, links, code) ---
function inlineFormat(text) {
    // Pieces that must not be touched by later steps (code, links, citations)
    // are stashed and replaced with placeholders, then restored at the end.
    const stash = [];
    const keep = (html) => `\u0000${stash.push(html) - 1}\u0000`;

    let s = text
        // Inline code `text`
        .replace(/`([^`]+)`/g, (_, code) => keep(`<code class="rc-code">${escapeHtml(code)}</code>`))
        // Links [text](url) — only http(s) URLs become links
        .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, label, url) =>
            isSafeUrl(url) ? keep(linkHtml(url, escapeHtml(label))) : m)
        // Bare URLs
        .replace(/https?:\/\/[^\s<>"'()\]]+/g, (url) => {
            const trail = url.match(/[.,;:!?]+$/);
            const clean = trail ? url.slice(0, -trail[0].length) : url;
            return keep(linkHtml(clean, escapeHtml(clean))) + (trail ? trail[0] : "");
        })
        // Citations [1] or [1, 3] → superscript links to the Sources list
        .replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g, (_, nums) => keep(
            nums.split(/\s*,\s*/)
                .map((n) => `<sup class="rc-ref"><a href="#ref-${n}">[${n}]</a></sup>`)
                .join("")
        ));

    s = escapeHtml(s)
        // Bold **text** or __text__
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/__([^_]+)__/g, "<strong>$1</strong>")
        // Italic *text* or _text_
        .replace(/\*([^*]+)\*/g, "<em>$1</em>")
        .replace(/(?<!\w)_([^_]+)_(?!\w)/g, "<em>$1</em>");

    return s.replace(/\u0000(\d+)\u0000/g, (_, i) => stash[Number(i)]);
}

// --- Table renderer ---
function renderTable(rows) {
    if (rows.length === 0) return "";
    let html = '<div class="rc-table-wrap"><table class="rc-table">';

    rows.forEach((row, idx) => {
        const cells = row.split("|").filter((c) => c.trim() !== "");
        const tag = idx === 0 ? "th" : "td";
        html += "<tr>";
        cells.forEach((cell) => {
            html += `<${tag}>${inlineFormat(cell.trim())}</${tag}>`;
        });
        html += "</tr>";
    });

    html += "</table></div>";
    return html;
}

// --- Export Functions ---
async function exportAs(format) {
    const rawTopic = currentTopic || "research_output";
    const filename = rawTopic.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');

    // Send the raw markdown (it already contains the numbered Sources section)
    const content = currentRawSummary;

    if (!content.trim()) {
        showError("No content to export.");
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/export`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content, filename, format }),
        });

        if (!res.ok) {
            showError(await readErrorMessage(res, "Export failed."));
            return;
        }

        // Download the file
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${filename}.${format}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (err) {
        showError(err.message || "Export failed.");
    }
}

exportTxtBtn.addEventListener("click", () => exportAs("txt"));
exportMdBtn.addEventListener("click", () => exportAs("md"));

copyBtn.addEventListener("click", async () => {
    if (!currentRawSummary.trim()) return;
    try {
        await navigator.clipboard.writeText(currentRawSummary);
        copyLabel.textContent = "Copied!";
    } catch (_) {
        copyLabel.textContent = "Copy failed";
    }
    setTimeout(() => { copyLabel.textContent = "Copy"; }, 1800);
});
exportPdfBtn.addEventListener("click", () => exportAs("pdf"));

// --- New Research ---
newResearchBtn.addEventListener("click", () => {
    hideResults();
    hideError();
    topicInput.value = "";
    charCount.textContent = "0";
    currentRawSummary = "";
    currentSources = [];
    topicInput.focus();
    setBusy(false);

    document.getElementById("search-section").scrollIntoView({
        behavior: "smooth",
        block: "start",
    });
});

// --- Error Dismiss ---
errorDismiss.addEventListener("click", hideError);

// --- UI State Helpers ---
function showLoading(state) {
    if (state) {
        loadingSection.classList.remove("hidden");
        startLoadingSteps();
    } else {
        loadingSection.classList.add("hidden");
    }
}

function showError(msg) {
    errorMsg.textContent = msg;
    errorSection.classList.remove("hidden");
}

function hideError() {
    errorSection.classList.add("hidden");
    errorMsg.textContent = "";
}

function hideResults() {
    resultsSection.classList.add("hidden");
}

// --- Loading Step Animation ---
function startLoadingSteps() {
    [stepPlan, stepSearch, stepAnalyze, stepWrite].forEach((s) => {
        s.classList.remove("active", "done");
    });
    renderPlan([]);
    // Steps advance as the backend sends `status` events (see setStage)
    stepPlan.classList.add("active");
}

// --- Background Laser & Particle Effects ---
const canvas = document.getElementById('laser-canvas');
const ctx = canvas.getContext('2d');
let width, height;
let particles = [];
let lasers = [];

function resizeCanvas() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
}
window.addEventListener('resize', resizeCanvas);
resizeCanvas();

class Laser {
    constructor() {
        this.reset();
    }
    reset() {
        // Start from random edge
        const edge = Math.floor(Math.random() * 4);
        if (edge === 0) { this.x = Math.random() * width; this.y = 0; }
        else if (edge === 1) { this.x = width; this.y = Math.random() * height; }
        else if (edge === 2) { this.x = Math.random() * width; this.y = height; }
        else { this.x = 0; this.y = Math.random() * height; }
        
        // Target random point on screen, or occasionally aim at another active laser to force a collision
        if (Math.random() > 0.6 && lasers.length > 0) {
            const targetLaser = lasers[Math.floor(Math.random() * lasers.length)];
            if (targetLaser && targetLaser.active) {
                this.targetX = targetLaser.x + (targetLaser.vx * 30);
                this.targetY = targetLaser.y + (targetLaser.vy * 30);
            } else {
                this.targetX = Math.random() * width;
                this.targetY = Math.random() * height;
            }
        } else {
            this.targetX = Math.random() * width;
            this.targetY = Math.random() * height;
        }
        
        // Base Speed: Slow cinematic comet pace
        this.baseSpeed = Math.random() * 2 + 1;
        this.speed = this.baseSpeed;
        
        // Timing for "suddenly slow" bullet-time effect is now global!
        
        const angle = Math.atan2(this.targetY - this.y, this.targetX - this.x);
        this.angle = angle;
        
        this.vx = Math.cos(this.angle) * this.speed;
        this.vy = Math.sin(this.angle) * this.speed;
        
        // Fixed tail length — set once so it never jitters or shrinks
        this.tailLength = this.baseSpeed * (Math.random() * 20 + 15);
        this.color = `hsla(${Math.random() * 60 + 200}, 100%, 80%, 0.65)`; // Softer opacity/lightness
        this.active = true;
    }
    update() {
        if (!this.active) return;
        
        // Apply perfectly smooth global time dilation
        const currentSpeed = this.baseSpeed * globalTimeDilation;
        
        this.vx = Math.cos(this.angle) * currentSpeed;
        this.vy = Math.sin(this.angle) * currentSpeed;
        
        // Tail length stays fixed — no recalculation per frame
        
        this.x += this.vx;
        this.y += this.vy;
        
        // Check collision with OTHER active lasers
        for (let other of lasers) {
            if (other !== this && other.active) {
                const dist = Math.hypot(other.x - this.x, other.y - this.y);
                if (dist < 40) { // Collision radius
                    this.active = false;
                    other.active = false;
                    createExplosion((this.x + other.x) / 2, (this.y + other.y) / 2);
                    setTimeout(() => this.reset(), Math.random() * 2000 + 500);
                    setTimeout(() => other.reset(), Math.random() * 2000 + 500);
                    return;
                }
            }
        }
        
        // Safety bounds
        if (this.x < -100 || this.x > width + 100 || this.y < -100 || this.y > height + 100) {
            this.active = false;
            setTimeout(() => this.reset(), Math.random() * 1000);
        }
    }
    draw() {
        if (!this.active) return;
        // Increase tail length during slomo for more dramatic effect
        const dynamicTailLength = this.tailLength * (1 + (1 - globalTimeDilation) * 1.5);
        
        // Draw tail using dynamic length in the direction opposite to travel
        const tailX = this.x - Math.cos(this.angle) * dynamicTailLength;
        const tailY = this.y - Math.sin(this.angle) * dynamicTailLength;
        
        // Gradient from bright head to transparent tail
        const grad = ctx.createLinearGradient(this.x, this.y, tailX, tailY);
        grad.addColorStop(0, this.color);
        grad.addColorStop(1, 'rgba(100, 180, 255, 0)');
        
        ctx.beginPath();
        ctx.moveTo(this.x, this.y);
        ctx.lineTo(tailX, tailY);
        ctx.strokeStyle = grad;
        ctx.lineWidth = 2.5; // Slightly thinner than before
        ctx.lineCap = 'round';
        ctx.stroke();
    }
}

class Particle {
    constructor(x, y) {
        this.x = x;
        this.y = y;
        const angle = Math.random() * Math.PI * 2;
        const speed = Math.random() * 3 + 1;
        this.vx = Math.cos(angle) * speed;
        this.vy = Math.sin(angle) * speed;
        this.size = Math.random() * 2 + 1; // Slightly larger particles
        this.life = 0.8; // More opaque start for explosion
        this.decay = Math.random() * 0.02 + 0.015;
        this.color = `hsla(${Math.random() * 60 + 200}, 100%, 75%, 1)`;
    }
    update() {
        // Particles also obey global time dilation!
        this.x += this.vx * globalTimeDilation;
        this.y += this.vy * globalTimeDilation;
        this.life -= this.decay * globalTimeDilation;
    }
    draw() {
        if (this.life <= 0) return;
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctx.fillStyle = this.color.replace('1)', `${this.life})`);
        ctx.fill();
    }
}

function createExplosion(x, y) {
    for (let i = 0; i < 15; i++) {
        particles.push(new Particle(x + (Math.random() * 40 - 20), y + (Math.random() * 40 - 20)));
    }
}

// Initialize a balanced number of lasers (more than 3, fewer than 12)
for (let i = 0; i < 6; i++) {
    setTimeout(() => { lasers.push(new Laser()); }, i * 600);
}

let globalTimeDilation = 2.0;
let timeEffectTimer = 0;

function animate() {
    ctx.clearRect(0, 0, width, height);
    
    // Global Cinematic Slow-Motion Engine
    timeEffectTimer++;
    let targetDilation = 1.0;
    
    // Every ~800 frames, trigger a 250-frame global slow motion event (longer interval)
    if (timeEffectTimer % 1000 > 800) {
        targetDilation = 0.1; // 10% speed (deep bullet-time)
    }
    
    // Incredibly smooth interpolation for the whole screen (slower transition)
    globalTimeDilation += (targetDilation - globalTimeDilation) * 0.015;
    
    lasers.forEach(laser => {
        laser.update();
        laser.draw();
    });
    
    for (let i = particles.length - 1; i >= 0; i--) {
        particles[i].update();
        particles[i].draw();
        if (particles[i].life <= 0) {
            particles.splice(i, 1);
        }
    }
    
    requestAnimationFrame(animate);
}
animate();
