/**
 * AI Research Assistant — Frontend Logic
 * Handles API calls, result rendering, rich text formatting, and file export.
 */

const API_BASE = "http://localhost:8000";

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
const sourcesSection = document.getElementById("sources-section");
const sourcesList = document.getElementById("sources-list");
const exportTxtBtn = document.getElementById("export-txt");
const exportPdfBtn = document.getElementById("export-pdf");
const newResearchBtn = document.getElementById("new-research-btn");
const mainLogo = document.getElementById("main-logo");

// Loading step elements
const stepSearch = document.getElementById("step-search");
const stepAnalyze = document.getElementById("step-analyze");
const stepWrite = document.getElementById("step-write");

// --- State ---
let currentTopic = "";
let currentRawSummary = "";
let currentSources = [];
let loadingInterval = null;

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
    showLoading(true);
    hideError();
    hideResults();
    researchBtn.disabled = true;

    try {
        const res = await fetch(`${API_BASE}/research`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ topic }),
        });

        if (!res.ok) {
            let errMessage = "Research failed. Please try again.";
            try {
                const errData = await res.json();
                errMessage = errData.error || errData.detail || errMessage;
            } catch (_) {}
            throw new Error(errMessage);
        }

        // Setup streaming state (but keep loading section visible initially)
        resultsTopic.textContent = currentTopic;
        summaryContent.innerHTML = '<span class="typing-cursor"></span>';
        sourcesSection.classList.add("hidden");
        // Reset UI
        researchBtn.disabled = true;
        researchBtn.classList.add("btn-loading");
        mainLogo.classList.add("logo-pulse");
        exportPdfBtn.disabled = true;
        
        currentRawSummary = "";
        currentSources = [];
        let hasStartedContent = false;

        const reader = res.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            
            // Parse SSE chunks separated by double newline
            const lines = buffer.split("\n\n");
            buffer = lines.pop() || "";

            for (const line of lines) {
                if (line.startsWith("data: ")) {
                    try {
                        const payload = JSON.parse(line.substring(6));
                        
                        if (payload.type === "status") {
                            // Sync backend status to frontend visual steps
                            if (payload.message.includes("Analyzing")) {
                                stepSearch.classList.remove("active");
                                stepSearch.classList.add("done");
                                stepAnalyze.classList.add("active");
                            } else if (payload.message.includes("Generating")) {
                                stepAnalyze.classList.remove("active");
                                stepAnalyze.classList.add("done");
                                stepWrite.classList.add("active");
                            }
                        } else if (payload.type === "content") {
                            if (!hasStartedContent) {
                                hasStartedContent = true;
                                // Hide loading steps and show text streaming now
                                loadingSection.classList.add("hidden");
                                resultsSection.classList.remove("hidden");
                            }
                            currentRawSummary += payload.text;
                            // Re-parse and render current markdown progressively
                            summaryContent.innerHTML = renderRichContent(currentRawSummary) + '<span class="typing-cursor"></span>';
                        } else if (payload.type === "done") {
                            loadingSection.classList.add("hidden");
                            resultsSection.classList.remove("hidden");
                            
                            // Finish and show sources
                            currentSources = payload.sources || [];
                            renderSources(currentSources);
                            exportPdfBtn.disabled = false;
                            exportTxtBtn.disabled = false;
                            researchBtn.classList.remove("btn-loading");
                            mainLogo.classList.remove("logo-pulse");
                            
                            // Remove typing cursor
                            summaryContent.innerHTML = renderRichContent(currentRawSummary);
                            
                            // Render Math equations if MathJax is loaded
                            if (window.MathJax) {
                                MathJax.typesetClear([summaryContent]);
                                MathJax.typesetPromise([summaryContent]).catch((err) => console.log('MathJax error:', err));
                            }
                        } else if (payload.type === "error") {
                            throw new Error(payload.message);
                        }
                    } catch (e) {
                        if (e.message !== "Unexpected end of JSON input") {
                            console.error("Error parsing stream chunk", e, line);
                        }
                    }
                }
            }
        }

    } catch (err) {
        showError(err.message || "Failed to connect to the server.");
        researchBtn.disabled = false;
        researchBtn.classList.remove("btn-loading");
        mainLogo.classList.remove("logo-pulse");
    } finally {
        showLoading(false);
        researchBtn.disabled = false;
        researchBtn.classList.remove("btn-loading");
        mainLogo.classList.remove("logo-pulse");
    }
});

function renderSources(sources) {
    if (sources && sources.length > 0) {
        sourcesList.innerHTML = "";
        sources.forEach((url) => {
            const li = document.createElement("li");
            const a = document.createElement("a");
            a.href = url;
            a.target = "_blank";
            a.rel = "noopener noreferrer";
            try {
                const u = new URL(url);
                a.textContent = u.hostname + u.pathname.slice(0, 40);
            } catch {
                a.textContent = url;
            }
            li.appendChild(a);
            sourcesList.appendChild(li);
        });
        sourcesSection.classList.remove("hidden");
    } else {
        sourcesSection.classList.add("hidden");
    }

    // Smooth scroll to results
    setTimeout(() => {
        resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 100);
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
    let inList = false;
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
                if (inList) { html += "</ul>"; inList = false; }
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
                html += `<div class="rc-math" style="overflow-x:auto; margin: 1rem 0;">${mathLines.join('\n')}</div>`;
                mathLines = [];
            }
            continue;
        }

        // Empty line
        if (!trimmed) {
            if (inList) { html += "</ul>"; inList = false; }
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
            if (inList) { html += "</ul>"; inList = false; }
            html += `<h4 class="rc-h3">${inlineFormat(trimmed.slice(4))}</h4>`;
            continue;
        }
        if (trimmed.startsWith("## ")) {
            if (inList) { html += "</ul>"; inList = false; }
            html += `<h3 class="rc-h2">${inlineFormat(trimmed.slice(3))}</h3>`;
            continue;
        }
        if (trimmed.startsWith("# ")) {
            if (inList) { html += "</ul>"; inList = false; }
            html += `<h2 class="rc-h1">${inlineFormat(trimmed.slice(2))}</h2>`;
            continue;
        }

        // Horizontal rule
        if (/^-{3,}$/.test(trimmed) || /^\*{3,}$/.test(trimmed)) {
            if (inList) { html += "</ul>"; inList = false; }
            html += "<hr class='rc-hr'>";
            continue;
        }

        // Bullet list items
        if (/^\s*[-*•]\s+/.test(line)) {
            if (!inList) { html += '<ul class="rc-list">'; inList = true; }
            const content = line.replace(/^\s*[-*•]\s+/, "");
            html += `<li>${inlineFormat(content)}</li>`;
            continue;
        }

        // Numbered list items
        if (/^\s*\d+\.\s+/.test(line)) {
            if (!inList) { html += '<ol class="rc-list rc-ol">'; inList = true; }
            const content = line.replace(/^\s*\d+\.\s+/, "");
            html += `<li>${inlineFormat(content)}</li>`;
            continue;
        }

        // Close list if we hit a non-list line
        if (inList) {
            html += inList ? "</ul>" : "</ol>";
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
    if (inList) html += "</ul>";
    if (inTable) html += renderTable(tableRows);

    return html;
}

// --- Inline formatting (bold, italic, links, code) ---
function inlineFormat(text) {
    return text
        // Links [text](url)
        .replace(
            /\[([^\]]+)\]\(([^)]+)\)/g,
            '<a href="$2" target="_blank" rel="noopener noreferrer" class="rc-link">$1</a>'
        )
        // Bare URLs not already inside HTML or markdown links
        .replace(
            /(?<!href="|\]\()(https?:\/\/[^\s<)]+)/g, 
            '<a href="$1" target="_blank" rel="noopener noreferrer" class="rc-link">$1</a>'
        )
        // Bold **text** or __text__
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/__([^_]+)__/g, "<strong>$1</strong>")
        // Italic *text* or _text_
        .replace(/\*([^*]+)\*/g, "<em>$1</em>")
        .replace(/(?<!\w)_([^_]+)_(?!\w)/g, "<em>$1</em>")
        // Inline code `text`
        .replace(/`([^`]+)`/g, '<code class="rc-code">$1</code>')
        // Superscript markers like [1], [2] etc
        .replace(/\[(\d+)\]/g, '<sup class="rc-ref">[$1]</sup>');
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
    const filename = currentTopic || "research_output";

    // For TXT: send raw markdown text. For PDF: send raw text (backend handles formatting)
    let content = currentRawSummary;

    if (!content.trim()) {
        showError("No content to export.");
        return;
    }

    // Append sources to the exported file
    if (currentSources && currentSources.length > 0) {
        content += "\n\n## Sources\n";
        currentSources.forEach(src => {
            content += `- [${src}](${src})\n`;
        });
    }

    try {
        const res = await fetch(`${API_BASE}/export`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content, filename, format }),
        });

        if (!res.ok) {
            let errMessage = "Export failed.";
            try {
                const errData = await res.json();
                errMessage = errData.error || errData.detail || errMessage;
            } catch (_) {}
            showError(errMessage);
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
    researchBtn.classList.remove("btn-loading");
    researchBtn.disabled = false;

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
        stopLoadingSteps();
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
    [stepSearch, stepAnalyze, stepWrite].forEach((s) => {
        s.classList.remove("active", "done");
    });
    // Start at search phase
    stepSearch.classList.add("active");
    
    // Animation is now driven manually by SSE backend events instead of interval
}

function stopLoadingSteps() {
    if (loadingInterval) {
        clearInterval(loadingInterval);
        loadingInterval = null;
    }
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
        
        // Base Speed: Start slower globally
        this.baseSpeed = Math.random() * 4 + 2;
        this.speed = this.baseSpeed;
        
        // Timing for "suddenly slow" bullet-time effect is now global!
        
        const angle = Math.atan2(this.targetY - this.y, this.targetX - this.x);
        this.angle = angle;
        
        this.vx = Math.cos(this.angle) * this.speed;
        this.vy = Math.sin(this.angle) * this.speed;
        
        // Calculate constant length based on baseSpeed so it doesn't shrink during slow-mo
        this.length = this.baseSpeed * (Math.random() * 6 + 2);
        this.color = `hsla(${Math.random() * 60 + 200}, 100%, 75%, 0.45)`; // Brighter opacity
        this.active = true;
    }
    update() {
        if (!this.active) return;
        
        // Apply perfectly smooth global time dilation
        const currentSpeed = this.baseSpeed * globalTimeDilation;
        
        this.vx = Math.cos(this.angle) * currentSpeed;
        this.vy = Math.sin(this.angle) * currentSpeed;
        
        // Calculate constant length based on baseSpeed so it doesn't shrink during slow-mo
        this.length = this.baseSpeed * (Math.random() * 6 + 2);
        
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
        ctx.beginPath();
        ctx.moveTo(this.x, this.y);
        ctx.lineTo(this.x - this.vx * (this.length / this.speed), this.y - this.vy * (this.length / this.speed));
        ctx.strokeStyle = this.color;
        ctx.lineWidth = 2;
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

let globalTimeDilation = 1.0;
let timeEffectTimer = 0;

function animate() {
    ctx.clearRect(0, 0, width, height);
    
    // Global Cinematic Slow-Motion Engine
    timeEffectTimer++;
    let targetDilation = 1.0;
    
    // Every ~400 frames, trigger a 120-frame global slow motion event
    if (timeEffectTimer % 400 > 280) {
        targetDilation = 0.15; // 15% speed (bullet-time)
    }
    
    // Incredibly smooth interpolation for the whole screen
    globalTimeDilation += (targetDilation - globalTimeDilation) * 0.03;
    
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
