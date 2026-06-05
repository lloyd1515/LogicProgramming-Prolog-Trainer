APP_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Outfit:wght@500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');

.stApp, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background-color: #090a0f !important;
    color: #cbd5e0 !important;
    font-family: 'Inter', sans-serif !important;
}

[data-testid="stHeader"], [data-testid="stSidebar"], [data-testid="stSidebar"] > div {
    background-color: #090a0f !important;
}

[data-testid="stSidebar"], [data-testid="stSidebar"] > div {
    border-right: 1px solid #2e3440 !important;
}

.app-title {
    font-family: 'Outfit', sans-serif !important;
    font-size: 2.5rem !important;
    font-weight: 800 !important;
    color: #ffffff !important;
    margin-bottom: 0.3rem !important;
    text-transform: uppercase !important;
}

.app-subtitle {
    font-family: 'Outfit', sans-serif !important;
    font-size: 1.05rem !important;
    color: #718096 !important;
    margin-bottom: 2rem !important;
}

.private-beta-badge {
    display: inline-block !important;
    margin-left: 0.5rem !important;
    padding: 0.12rem 0.45rem !important;
    border: 1px solid rgba(99, 235, 158, 0.25) !important;
    border-radius: 999px !important;
    color: #63eb9e !important;
    font-size: 0.68rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    vertical-align: middle !important;
}

/* ── Search chips ─────────────────────────────── */
.search-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-bottom: 1rem;
}

.search-chip {
    display: inline-block;
    padding: 0.25rem 0.7rem;
    background: rgba(255,255,255,0.05);
    border: 1px solid #2e3440;
    border-radius: 999px;
    font-size: 0.8rem;
    color: #94a3b8;
    cursor: pointer;
    font-family: 'JetBrains Mono', monospace;
    transition: background 0.15s, border-color 0.15s, color 0.15s;
}

.search-chip:hover {
    background: rgba(255,255,255,0.1);
    border-color: #4a5568;
    color: #e2e8f0;
}

/* ── Slide result cards ───────────────────────── */
.slide-card {
    background-color: #111318 !important;
    border: 1px solid #1e2433 !important;
    border-radius: 10px !important;
    padding: 1.25rem 1.4rem !important;
    margin-bottom: 1rem !important;
}

.slide-card-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
    flex-wrap: wrap;
}

.badge {
    display: inline-block !important;
    padding: 0.2rem 0.55rem !important;
    font-size: 0.7rem !important;
    font-weight: 600 !important;
    border-radius: 4px !important;
    margin-right: 0.4rem !important;
    font-family: 'Outfit', sans-serif !important;
    text-transform: uppercase !important;
    letter-spacing: 0.04em !important;
}

.badge-similarity {
    background-color: rgba(99, 235, 158, 0.12) !important;
    color: #63eb9e !important;
    border: 1px solid rgba(99, 235, 158, 0.25) !important;
}

.badge-similarity.low {
    background-color: rgba(251, 191, 36, 0.1) !important;
    color: #fbbf24 !important;
    border-color: rgba(251, 191, 36, 0.2) !important;
}

.badge-source {
    background-color: rgba(99, 179, 237, 0.1) !important;
    color: #63b3ed !important;
    border: 1px solid rgba(99, 179, 237, 0.2) !important;
}

.badge-page {
    background-color: rgba(255, 255, 255, 0.04) !important;
    color: #718096 !important;
    border: 1px solid #2e3440 !important;
}

.slide-title {
    font-family: 'Outfit', sans-serif !important;
    font-size: 1.05rem !important;
    font-weight: 700 !important;
    color: #f0f4f8 !important;
    margin: 0.5rem 0 0.75rem 0 !important;
}

.slide-text-block {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.9rem !important;
    color: #a0aec0 !important;
    line-height: 1.7 !important;
    white-space: pre-wrap !important;
    word-break: break-word !important;
}

/* ── AI answer structured output ─────────────── */
.ai-answer-box {
    background: linear-gradient(135deg, #0f1117 0%, #131720 100%);
    border: 1px solid #1e3a5f;
    border-left: 3px solid #3b82f6;
    border-radius: 10px;
    padding: 1.5rem 1.75rem;
    margin-bottom: 1.5rem;
}

/* ── Buttons ──────────────────────────────────── */
div.stButton > button {
    background-color: #161821 !important;
    color: #cbd5e0 !important;
    border: 1px solid #2e3440 !important;
    border-radius: 6px !important;
    font-family: 'Outfit', sans-serif !important;
    font-weight: 500 !important;
}

div.stButton > button[type="primary"] {
    background-color: #e2e8f0 !important;
    color: #090a0f !important;
    border: 1px solid #e2e8f0 !important;
    font-weight: 600 !important;
}

div[data-testid="stAlert"], [data-testid="stExpander"] {
    background-color: #161821 !important;
    border: 1px solid #2e3440 !important;
    border-radius: 6px !important;
}

/* ── Admin dashboard ─────────────────────────── */
.admin-shell {
    margin-top: 0.5rem;
}

.admin-kicker {
    color: #94a3b8;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    margin-bottom: 0.35rem;
    text-transform: uppercase;
}

.admin-title {
    color: #f8fafc;
    font-family: 'Outfit', sans-serif !important;
    font-size: 1.95rem;
    font-weight: 750;
    letter-spacing: 0 !important;
    line-height: 1.15;
    margin-bottom: 0.3rem;
}

.admin-subtitle {
    color: #94a3b8;
    font-size: 0.95rem;
    margin-bottom: 1.35rem;
}

.admin-section-title {
    color: #e5edf8;
    font-family: 'Outfit', sans-serif !important;
    font-size: 1rem;
    font-weight: 700;
    letter-spacing: 0 !important;
    margin: 0.2rem 0 0.7rem;
}

.admin-panel {
    background: #11141b;
    border: 1px solid #252b38;
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1rem;
}

.admin-danger {
    background: rgba(127, 29, 29, 0.14);
    border: 1px solid rgba(248, 113, 113, 0.35);
    border-radius: 8px;
    padding: 1rem;
    margin-top: 1rem;
}

.admin-danger-title {
    color: #fecaca;
    font-family: 'Outfit', sans-serif !important;
    font-size: 0.95rem;
    font-weight: 700;
    margin-bottom: 0.25rem;
}

.admin-danger-copy {
    color: #b6c2d2;
    font-size: 0.82rem;
    line-height: 1.45;
    margin-bottom: 0.75rem;
}

.admin-metrics-grid {
    display: grid;
    gap: 0.75rem;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    margin: 0.8rem 0 1.25rem;
}

.admin-metric-card {
    background: #11141b;
    border: 1px solid #252b38;
    border-radius: 8px;
    min-height: 5.1rem;
    padding: 0.8rem 0.9rem;
}

.admin-metric-label {
    color: #9aa6b8;
    font-size: 0.74rem;
    font-weight: 650;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    white-space: nowrap;
}

.admin-metric-value {
    color: #f8fafc;
    font-family: 'Outfit', sans-serif !important;
    font-size: 2rem;
    font-weight: 750;
    line-height: 1.15;
    margin-top: 0.45rem;
}

.admin-live-note {
    color: #64748b;
    font-size: 0.82rem;
    margin-top: -0.35rem;
}

.admin-divider {
    border-top: 1px solid #2a303d;
    margin: 1.4rem 0;
}

.admin-filter-note {
    color: #94a3b8;
    font-size: 0.82rem;
    margin-bottom: 0.35rem;
}

.admin-log-count {
    color: #94a3b8;
    font-size: 0.86rem;
    margin: -0.25rem 0 0.75rem;
}

.st-key-filter_search [data-testid="stTextInputRootElement"],
.st-key-delete_user_input [data-testid="stTextInputRootElement"],
.st-key-filter_search [data-baseweb="base-input"],
.st-key-delete_user_input [data-baseweb="base-input"],
.st-key-filter_search input,
.st-key-delete_user_input input {
    background: #111827 !important;
    color: #e5e7eb !important;
    border-color: #374151 !important;
    min-height: 2.55rem !important;
    height: 2.55rem !important;
    font-family: 'Inter', sans-serif !important;
}

.st-key-admin_delete_user_btn button,
.st-key-admin_delete_all_guests_btn button {
    border-color: rgba(248, 113, 113, 0.55) !important;
    color: #fecaca !important;
}

/* ── Quiz Moodle-style ────────────────────────── */
.moodle-qnumber {
    display: inline-block !important;
    background: #f2f2f2 !important;
    color: #202020 !important;
    border: 1px solid #d0d0d0 !important;
    border-radius: 3px !important;
    padding: 0.25rem 0.5rem !important;
    margin-bottom: 0.75rem !important;
    font-weight: 700 !important;
}

.moodle-nav-title {
    background: #f2f2f2 !important;
    color: #202020 !important;
    border: 1px solid #d0d0d0 !important;
    border-radius: 3px 3px 0 0 !important;
    padding: 0.45rem 0.6rem !important;
    font-weight: 700 !important;
    margin-bottom: 0.5rem !important;
}

[data-testid="stColumn"]:has(.moodle-nav-title) div.stButton > button {
    min-width: 2.35rem !important;
    height: 2.25rem !important;
    padding: 0.2rem !important;
    border-radius: 3px !important;
    background: #ffffff !important;
    color: #202020 !important;
    border: 1px solid #bdbdbd !important;
}

[data-testid="stColumn"]:has(.moodle-nav-title) div.stButton > button[type="primary"] {
    width: 100% !important;
    min-width: 100% !important;
    background-color: #e2e8f0 !important;
    color: #090a0f !important;
    border: 1px solid #e2e8f0 !important;
}

/* ── Inline code blanks ───────────────────────── */
.inline-code-line,
.inline-code-piece {
    background: transparent !important;
    color: #e5e7eb !important;
    border: 0 !important;
    padding: 0 !important;
    margin: 0 !important;
    font-family: "JetBrains Mono", Consolas, monospace !important;
    font-size: 0.98rem !important;
    line-height: 1.8rem !important;
    white-space: pre !important;
}

.inline-code-gap {
    height: 0 !important;
    margin-top: -0.55rem !important;
}

.inline-code-filler {
    display: block !important;
    height: 1px !important;
}

[data-testid="stColumn"] [data-testid="stTextInput"] {
    margin: 0 !important;
}

[data-testid="stColumn"] [data-testid="stTextInput"] > div {
    margin: 0 !important;
}

[data-testid="stColumn"] [data-testid="stTextInputRootElement"],
[data-testid="stColumn"] [data-baseweb="base-input"] {
    background: #f8fafc !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 4px !important;
    box-shadow: none !important;
    min-height: 1.75rem !important;
    height: 1.75rem !important;
}

[data-testid="stColumn"] [data-testid="stTextInput"] input {
    background: #f8fafc !important;
    color: #111827 !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 4px !important;
    min-height: 1.75rem !important;
    height: 1.75rem !important;
    padding: 0.1rem 0.4rem !important;
    font-family: "JetBrains Mono", Consolas, monospace !important;
    font-size: 0.95rem !important;
}

[data-testid="stColumn"] [data-testid="stTextInput"] input:focus {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 1px #2563eb !important;
}

/* ── Token estimation box ─────────────────────── */
.token-estimate {
    background: rgba(251, 191, 36, 0.05);
    border: 1px solid rgba(251, 191, 36, 0.2);
    border-radius: 8px;
    padding: 0.9rem 1.2rem;
    margin-bottom: 1rem;
    font-size: 0.85rem;
    color: #94a3b8;
}

.token-estimate strong {
    color: #fbbf24;
}

/* ── Model Selector Badges and Tooltips ─────────────────────── */
.model-selector-title {
    font-size: 0.85rem;
    font-weight: 500;
    color: #718096;
    margin-bottom: 0.4rem;
    font-family: 'Outfit', sans-serif !important;
}

.model-badges-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.5rem;
    margin-bottom: 0.5rem;
}

.model-hover-badge {
    position: relative;
    display: inline-block;
    padding: 0.35rem 0.75rem;
    background: #111318;
    border: 1px solid #2e3440;
    border-radius: 6px;
    font-size: 0.8rem;
    font-weight: 500;
    color: #94a3b8;
    cursor: pointer;
    text-decoration: none !important;
    transition: all 0.2s ease;
    font-family: 'Outfit', sans-serif !important;
}

.model-hover-badge.active-model {
    border-color: #3b82f6;
    background: rgba(59, 130, 246, 0.05);
    color: #e2e8f0;
    box-shadow: 0 0 8px rgba(59, 130, 246, 0.25);
}

.model-hover-badge.exhausted-model {
    border-color: #ef4444;
    background: rgba(239, 68, 68, 0.05);
    color: #f87171;
}

.model-hover-badge:hover {
    background: #1a1e29;
    border-color: #4b5563;
}

.model-hover-badge.active-model:hover {
    border-color: #60a5fa;
}

.model-hover-badge.exhausted-model:hover {
    border-color: #f87171;
}

/* ── Footer ───────────────────────────────────── */
.footer {
    text-align: center;
    margin-top: 3rem;
    font-size: 0.8rem;
    color: #4a5568;
    border-top: 1px solid #2e3440;
    padding-top: 1.5rem;
    font-family: 'Outfit', sans-serif !important;
}

/* ── Prevent text cursor (I-beam) in selectboxes ── */
.st-key-quiz_topic_selectbox *, 
.st-key-model_selector_ui * {
    cursor: pointer !important;
}

.st-key-quiz_topic_selectbox input,
.st-key-model_selector_ui input {
    caret-color: transparent !important;
}

/* ── Mobile responsiveness overrides ── */
@media (max-width: 768px) {
    .block-container {
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
        padding-top: 4.5rem !important;
        padding-bottom: 1.5rem !important;
    }
    .app-title {
        font-size: 1.7rem !important;
        margin-top: 0.5rem !important;
        margin-bottom: 0.2rem !important;
        line-height: 2.2rem !important;
    }
    .app-subtitle {
        font-size: 0.9rem !important;
        margin-bottom: 1.25rem !important;
    }
    .admin-title {
        font-size: 1.55rem !important;
    }
    .admin-subtitle {
        font-size: 0.88rem !important;
    }
    .admin-metrics-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .admin-metric-card {
        min-height: 4.55rem;
        padding: 0.7rem 0.75rem;
    }
    .admin-metric-value {
        font-size: 1.65rem;
    }
    .slide-card {
        padding: 0.9rem 1rem !important;
    }
    .badge {
        font-size: 0.65rem !important;
        padding: 0.15rem 0.4rem !important;
        margin-right: 0.25rem !important;
    }
    .ai-answer-box {
        padding: 1rem 1.1rem !important;
    }
    
    /* Prevent vertical stacking of inline code completion columns */
    [data-testid="stHorizontalBlock"]:has(.inline-code-piece),
    [data-testid="stHorizontalBlock"]:has(.inline-code-line) {
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
        max-width: 100% !important;
        width: 100% !important;
        box-sizing: border-box !important;
    }
    [data-testid="stHorizontalBlock"]:has(.inline-code-piece) div[data-testid="stColumn"]:has([data-testid="stTextInput"]) {
        width: 110px !important;
        min-width: 110px !important;
        flex-shrink: 0 !important;
        flex-grow: 0 !important;
    }
    [data-testid="stHorizontalBlock"]:has(.inline-code-piece) div[data-testid="stColumn"]:not(:has([data-testid="stTextInput"])),
    [data-testid="stHorizontalBlock"]:has(.inline-code-line) div[data-testid="stColumn"] {
        width: auto !important;
        min-width: auto !important;
        flex-shrink: 0 !important;
        flex-grow: 0 !important;
    }
    [data-testid="stHorizontalBlock"]:has(.inline-code-piece) [data-testid="stTextInput"],
    [data-testid="stHorizontalBlock"]:has(.inline-code-piece) [data-testid="stTextInputRootElement"],
    [data-testid="stHorizontalBlock"]:has(.inline-code-piece) [data-baseweb="base-input"],
    [data-testid="stHorizontalBlock"]:has(.inline-code-piece) [data-testid="stTextInput"] input {
        width: 100% !important;
        min-width: 100% !important;
    }
    .inline-code-piece, .inline-code-line {
        font-size: 0.82rem !important;
        white-space: pre !important;
        word-break: keep-all !important;
        overflow-wrap: normal !important;
    }
    [data-testid="stColumn"] [data-testid="stTextInput"] input {
        font-size: 0.8rem !important;
        padding: 0.05rem 0.2rem !important;
    }
    
    /* Prevent vertical stacking of quiz navigation grid buttons */
    [data-testid="stColumn"]:has(.moodle-nav-title) [data-testid="stHorizontalBlock"],
    div:has(.moodle-nav-title) [data-testid="stHorizontalBlock"] {
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        gap: 0.4rem !important;
        margin-bottom: 0.4rem !important;
    }
    [data-testid="stColumn"]:has(.moodle-nav-title) [data-testid="stColumn"],
    div:has(.moodle-nav-title) [data-testid="stColumn"] {
        width: 20% !important;
        min-width: 0 !important;
        flex-shrink: 0 !important;
    }
    
    /* Make navigation buttons fill the column and be large tap targets */
    [data-testid="stColumn"]:has(.moodle-nav-title) div.stButton > button,
    div:has(.moodle-nav-title) div.stButton > button {
        width: 100% !important;
        min-width: 0 !important;
        height: 2.4rem !important;
        font-size: 0.9rem !important;
        font-weight: 600 !important;
        border-radius: 4px !important;
        padding: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }

    /* Standardize code block typography and viewport safety */
    div[data-testid="stCodeBlock"] pre {
        font-size: 0.8rem !important;
        max-width: 100% !important;
        overflow-x: auto !important;
    }

    /* Place quiz navigation column on top of the main question card on mobile */
    div[data-testid="stHorizontalBlock"]:has(.moodle-nav-title) {
        display: flex !important;
        flex-direction: column-reverse !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.moodle-nav-title) > div[data-testid="stColumn"] {
        width: 100% !important;
        min-width: 100% !important;
    }
    
    /* Ensure the navigation column has vertical space when reversed */
    div[data-testid="stColumn"]:has(.moodle-nav-title) {
        margin-bottom: 1.5rem !important;
    }
}
"""
