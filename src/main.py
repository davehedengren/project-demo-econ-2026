"""
Main entry point for the career counselor chatbot.
Provides both CLI and web interfaces.
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, render_template_string, request, jsonify, session

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Verify API key
if not os.environ.get("ANTHROPIC_API_KEY"):
    print("Warning: ANTHROPIC_API_KEY not found in environment.")
    print("Chat functionality will not work without it.")

from .chatbot import ChatbotError, create_chatbot
from .occupation_store import OccupationStore
from .onet_data import OnetStore, load_onet_data
from .state_data import load_state_data

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

# Global stores — all backed by a single SQLite database
data_dir = Path(__file__).parent.parent / "data"
db_path = str(data_dir / "career_data.db")

if not (data_dir / "career_data.db").exists():
    logger.error("Database not found at %s", db_path)
    print(f"Error: career_data.db not found. Run 'python build_db.py' first.")
    sys.exit(1)

try:
    occupation_store = OccupationStore(db_path)
    logger.info("Loaded %d occupations from database.", occupation_store.count)
except Exception as e:
    logger.error("Failed to load occupation data: %s", e, exc_info=True)
    print(f"Error loading occupation data: {e}")
    sys.exit(1)

try:
    state_store = load_state_data(db_path)
    logger.info("Loaded state-level wage data from database.")
except Exception as e:
    logger.error("Failed to load state data: %s", e, exc_info=True)
    print(f"Error loading state data: {e}")
    sys.exit(1)

# O*NET data (optional — enhances skills/interests features)
onet_store = None
try:
    # Check if O*NET tables have data
    import sqlite3
    _check = sqlite3.connect(db_path)
    onet_count = _check.execute("SELECT COUNT(*) FROM onet_occupations").fetchone()[0]
    _check.close()
    if onet_count > 0:
        onet_store = load_onet_data(db_path)
        logger.info("Loaded O*NET skills, knowledge, and interests data.")
    else:
        logger.info("O*NET tables empty — skills/interests tools disabled.")
except Exception as e:
    logger.warning("Could not load O*NET data (non-fatal): %s", e)
    onet_store = None

# Global chatbot instances (keyed by session)
chatbots = {}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Career Counselor</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            font-size: 15px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 16px 16px 40px 16px;
            display: flex;
            flex-direction: column;
        }
        .site-footer {
            text-align: center;
            padding: 10px 0 2px 0;
            margin-top: auto;
            font-size: 13px;
        }
        .site-footer a {
            color: rgba(255,255,255,0.8);
            text-decoration: none;
        }
        .site-footer a:hover {
            color: #fff;
            text-decoration: underline;
        }
        .app-container {
            display: flex;
            gap: 16px;
            width: 100%;
            max-width: 1400px;
            margin: 0 auto;
            height: calc(100vh - 32px);
        }
        .chat-container {
            flex: 1;
            min-width: 0;
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            display: flex;
            flex-direction: column;
        }
        .sidebar {
            width: 340px;
            flex-shrink: 0;
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            display: flex;
            flex-direction: column;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 14px 18px;
            text-align: center;
            position: relative;
            border-radius: 12px 12px 0 0;
        }
        .header h1 { font-size: 20px; margin-bottom: 3px; font-weight: 600; }
        .header p { opacity: 0.9; font-size: 13px; }
        .chat-area {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            background: #f8f9fa;
        }
        .message { margin-bottom: 12px; display: flex; flex-direction: column; }
        .message.user { align-items: flex-end; }
        .message.assistant { align-items: flex-start; }
        .message-content {
            max-width: 85%;
            padding: 10px 14px;
            border-radius: 12px;
            line-height: 1.5;
            font-size: 15px;
        }
        .message.user .message-content {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-bottom-right-radius: 4px;
        }
        .message.assistant .message-content {
            background: white;
            color: #333;
            border-bottom-left-radius: 4px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        }
        .message-content p { margin-bottom: 6px; }
        .message-content p:last-child { margin-bottom: 0; }
        .message-content strong { color: #667eea; }
        .message.user .message-content strong { color: #fff; }
        .message-content table {
            margin: 10px 0;
            border-collapse: collapse;
            font-size: 14px;
            width: auto;
            background: white;
        }
        .message-content th, .message-content td {
            padding: 8px 12px;
            border: 1px solid #ddd;
            text-align: left;
        }
        .message-content th {
            background: #f5f5f5;
            font-weight: 600;
        }
        .message-content tr:hover td { background: #fafafa; }
        .input-area {
            padding: 12px;
            background: white;
            border-top: 1px solid #eee;
            border-radius: 0 0 12px 12px;
        }
        .input-form { display: flex; gap: 10px; }
        .input-form input {
            flex: 1;
            padding: 10px 14px;
            border: 1px solid #ddd;
            border-radius: 20px;
            font-size: 15px;
            outline: none;
        }
        .input-form input:focus { border-color: #667eea; }
        .input-form button {
            padding: 10px 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 20px;
            font-size: 15px;
            cursor: pointer;
        }
        .input-form button:disabled { opacity: 0.6; cursor: not-allowed; }
        .typing-indicator {
            display: none;
            padding: 8px 12px;
            background: white;
            border-radius: 10px;
            border-bottom-left-radius: 4px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.06);
            max-width: 50px;
        }
        .typing-indicator.show { display: block; }
        .typing-indicator span {
            display: inline-block; width: 5px; height: 5px;
            background: #667eea; border-radius: 50%; margin-right: 2px;
            animation: bounce 1.4s ease-in-out infinite;
        }
        .typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
        .typing-indicator span:nth-child(3) { animation-delay: 0.4s; margin-right: 0; }
        @keyframes bounce { 0%, 60%, 100% { transform: translateY(0); } 30% { transform: translateY(-2px); } }
        .reset-btn {
            position: absolute; top: 12px; right: 14px;
            background: rgba(255,255,255,0.2); border: none; color: white;
            padding: 6px 12px; border-radius: 12px; cursor: pointer;
            font-size: 13px;
        }
        .reset-btn:hover { background: rgba(255,255,255,0.3); }

        /* Sidebar */
        .sidebar-header {
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            color: white;
            padding: 14px 18px;
            text-align: center;
            border-radius: 12px 12px 0 0;
        }
        .sidebar-header h2 { font-size: 18px; margin-bottom: 3px; font-weight: 600; }
        .sidebar-header p { opacity: 0.9; font-size: 13px; }
        .sidebar-tabs {
            display: flex;
            border-bottom: 1px solid #eee;
            background: #fafafa;
        }
        .sidebar-tab {
            flex: 1;
            padding: 10px 12px;
            text-align: center;
            font-size: 13px;
            cursor: pointer;
            border: none;
            background: none;
            color: #666;
            border-bottom: 2px solid transparent;
        }
        .sidebar-tab.active { color: #11998e; border-bottom-color: #11998e; font-weight: 600; }
        .sidebar-tab .badge {
            background: #11998e; color: white; padding: 2px 6px;
            border-radius: 8px; font-size: 11px; margin-left: 4px;
        }
        .sidebar-content {
            flex: 1;
            overflow-y: auto;
            padding: 12px;
            background: #f8f9fa;
        }
        .sidebar-controls {
            padding: 10px 12px;
            background: white;
            border-bottom: 1px solid #eee;
        }
        .sidebar-controls select, .sidebar-controls input {
            width: 100%;
            padding: 8px 10px;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-size: 13px;
            margin-bottom: 6px;
        }
        .sidebar-controls input:focus, .sidebar-controls select:focus {
            border-color: #11998e; outline: none;
        }

        /* Cards */
        .occ-card {
            background: white;
            border-radius: 8px;
            margin-bottom: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            overflow: hidden;
            border: 1px solid #eee;
        }
        .occ-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .occ-card.suggested { border-color: #667eea; border-width: 2px; }
        .occ-card-header {
            padding: 10px 12px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 8px;
        }
        .occ-card-title {
            font-weight: 600;
            font-size: 14px;
            color: #333;
            flex: 1;
        }
        .occ-card-meta {
            display: flex;
            gap: 8px;
            margin-top: 4px;
            flex-wrap: wrap;
        }
        .occ-card-stat {
            font-size: 12px;
            color: #666;
        }
        .occ-card-stat strong { color: #333; }
        .occ-card-badge {
            font-size: 11px;
            padding: 2px 6px;
            border-radius: 6px;
            white-space: nowrap;
        }
        .badge-growth-high { background: #d4edda; color: #155724; }
        .badge-growth-med { background: #fff3cd; color: #856404; }
        .badge-growth-low { background: #f8d7da; color: #721c24; }
        .badge-growth-avg { background: #e2e3e5; color: #383d41; }
        .occ-card-actions {
            display: flex;
            gap: 6px;
            align-items: center;
        }
        .occ-card-btn {
            padding: 4px 8px;
            font-size: 12px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
        }
        .occ-card-btn-fav {
            background: none;
            font-size: 18px;
            padding: 0;
            color: #ccc;
        }
        .occ-card-btn-fav.favorited { color: #e74c3c; }
        .occ-card-details {
            display: none;
            padding: 0 12px 12px;
            border-top: 1px solid #eee;
            font-size: 13px;
            color: #555;
            line-height: 1.5;
        }
        .occ-card.expanded .occ-card-details { display: block; }
        .occ-card-details p { margin-bottom: 4px; }
        .occ-card-details a:hover { text-decoration: underline; }
        .detail-row {
            display: flex;
            justify-content: space-between;
            padding: 2px 0;
            border-bottom: 1px solid #f5f5f5;
        }
        .detail-row:last-child { border-bottom: none; }
        .detail-label { color: #888; }
        .detail-value { font-weight: 500; color: #333; }
        .card-actions-row {
            margin-top: 6px;
            display: flex;
            gap: 4px;
        }
        .btn-ask {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .btn-state { background: #eee; color: #555; }
        .expand-icon {
            font-size: 8px;
            color: #999;
            transition: transform 0.2s;
        }
        .occ-card.expanded .expand-icon { transform: rotate(180deg); }

        /* Compare View */
        .compare-panel {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.5);
            z-index: 100;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .compare-panel.show { display: flex; }
        .compare-content {
            background: white;
            border-radius: 12px;
            max-width: 95vw;
            max-height: 90vh;
            overflow: auto;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        .compare-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
        }
        .compare-header h3 { font-size: 18px; }
        .compare-close {
            background: rgba(255,255,255,0.2);
            border: none;
            color: white;
            padding: 6px 14px;
            border-radius: 12px;
            cursor: pointer;
            font-size: 14px;
        }
        .compare-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }
        .compare-table th, .compare-table td {
            padding: 10px 14px;
            text-align: left;
            border-bottom: 1px solid #eee;
            vertical-align: top;
        }
        .compare-table th {
            background: #f8f9fa;
            font-weight: 600;
            color: #555;
            position: sticky;
            left: 0;
            min-width: 120px;
        }
        .compare-table td { min-width: 160px; }
        .compare-table tr:hover td { background: #fafafa; }

        /* Responsive */
        @media (max-width: 900px) {
            .app-container { flex-direction: column; height: auto; }
            .chat-container { height: 55vh; min-height: 350px; }
            .sidebar { width: 100%; height: 45vh; min-height: 280px; }
        }
    </style>
</head>
<body>
    <div class="app-container">
        <div class="chat-container">
            <div class="header">
                <h1>Career Counselor</h1>
                <p>Chat about your interests and goals</p>
                <button class="reset-btn" onclick="resetChat()">New Chat</button>
            </div>
            <div class="chat-area" id="chatArea">
                <div class="message assistant">
                    <div class="message-content">
                        <p>Hi! I'm your career counselor with data on 340+ occupations.</p>
                        <p>Tell me about yourself - what subjects do you enjoy? What are your strengths? Any states you'd like to work in?</p>
                    </div>
                </div>
            </div>
            <div class="input-area">
                <form class="input-form" onsubmit="sendMessage(event)">
                    <input type="text" id="userInput" placeholder="Type your message..." autocomplete="off">
                    <button type="submit" id="sendBtn">Send</button>
                </form>
            </div>
        </div>

        <div class="sidebar">
            <div class="sidebar-header">
                <h2>Explore Careers</h2>
                <p>Browse, save, and compare</p>
            </div>
            <div class="sidebar-tabs">
                <button class="sidebar-tab active" data-tab="explore" onclick="switchTab('explore')">Explore</button>
                <button class="sidebar-tab" data-tab="favorites" onclick="switchTab('favorites')">
                    Favorites <span class="badge" id="favCount">0</span>
                </button>
                <button class="sidebar-tab" data-tab="suggested" onclick="switchTab('suggested')">Suggested</button>
            </div>
            <div class="sidebar-controls" id="exploreControls">
                <select id="categorySelect" onchange="filterByCategory()">
                    <option value="">All Categories</option>
                </select>
                <input type="text" id="searchBox" placeholder="Search occupations..." oninput="searchOccupations()">
            </div>
            <div class="sidebar-content" id="sidebarContent"></div>
            <div style="padding: 6px; background: white; border-top: 1px solid #eee; text-align: center;">
                <button class="occ-card-btn btn-ask" onclick="openCompare()" style="padding: 6px 16px;">
                    Compare Favorites
                </button>
            </div>
        </div>
    </div>

    <!-- Compare Modal -->
    <div class="compare-panel" id="comparePanel">
        <div class="compare-content">
            <div class="compare-header">
                <h3>Compare Careers</h3>
                <button class="compare-close" onclick="closeCompare()">Close</button>
            </div>
            <table class="compare-table" id="compareTable"></table>
        </div>
    </div>

    <script>
        const chatArea = document.getElementById('chatArea');
        const userInput = document.getElementById('userInput');
        const sendBtn = document.getElementById('sendBtn');
        const categorySelect = document.getElementById('categorySelect');
        const searchBox = document.getElementById('searchBox');
        const sidebarContent = document.getElementById('sidebarContent');
        const exploreControls = document.getElementById('exploreControls');

        let allOccupations = [];
        let categories = [];
        let favorites = JSON.parse(localStorage.getItem('careerFavorites') || '[]');
        let suggestedCodes = [];
        let currentTab = 'explore';

        // Load occupations
        async function loadOccupations() {
            const res = await fetch('/api/occupations');
            const data = await res.json();
            allOccupations = data.occupations;
            categories = data.categories;
            categories.forEach(cat => {
                const opt = document.createElement('option');
                opt.value = cat;
                opt.textContent = cat.replace(/-/g, ' ').replace(/\\b\\w/g, l => l.toUpperCase());
                categorySelect.appendChild(opt);
            });
            updateFavCount();
            renderCurrentTab();
        }

        function switchTab(tab) {
            currentTab = tab;
            document.querySelectorAll('.sidebar-tab').forEach(t => t.classList.remove('active'));
            document.querySelector(`[data-tab="${tab}"]`).classList.add('active');
            exploreControls.style.display = tab === 'explore' ? 'block' : 'none';
            renderCurrentTab();
        }

        function renderCurrentTab() {
            if (currentTab === 'explore') {
                const cat = categorySelect.value;
                const query = searchBox.value.toLowerCase();
                let filtered = allOccupations;
                if (cat) filtered = filtered.filter(o => o.category === cat);
                if (query) filtered = filtered.filter(o =>
                    o.title.toLowerCase().includes(query) || o.description.toLowerCase().includes(query)
                );
                renderCards(filtered.slice(0, 25));
            } else if (currentTab === 'favorites') {
                const favOccs = allOccupations.filter(o => favorites.includes(o.code));
                if (favOccs.length === 0) {
                    sidebarContent.innerHTML = '<p style="text-align:center;color:#888;padding:20px;font-size:13px;">No favorites yet. Click the heart on any career to save it.</p>';
                } else {
                    renderCards(favOccs);
                }
            } else if (currentTab === 'suggested') {
                const sugOccs = allOccupations.filter(o => suggestedCodes.includes(o.code));
                if (sugOccs.length === 0) {
                    sidebarContent.innerHTML = '<p style="text-align:center;color:#888;padding:20px;font-size:13px;">No suggestions yet. Chat with me and I\\'ll recommend careers for you!</p>';
                } else {
                    renderCards(sugOccs, true);
                }
            }
        }

        function getGrowthBadge(outlook, value) {
            if (!outlook) return '';
            const lower = outlook.toLowerCase();
            if (lower.includes('much faster')) return `<span class="occ-card-badge badge-growth-high">+${value||''}%</span>`;
            if (lower.includes('faster')) return `<span class="occ-card-badge badge-growth-med">+${value||''}%</span>`;
            if (lower.includes('decline')) return `<span class="occ-card-badge badge-growth-low">${value||''}%</span>`;
            if (lower.includes('little') || lower.includes('no change')) return `<span class="occ-card-badge badge-growth-low">0%</span>`;
            return `<span class="occ-card-badge badge-growth-avg">${value||'3'}%</span>`;
        }

        function formatSalary(val) { return val ? '$' + val.toLocaleString() : 'Varies'; }
        function formatJobs(val) {
            if (!val) return 'N/A';
            if (val >= 1000000) return (val/1000000).toFixed(1) + 'M';
            if (val >= 1000) return Math.round(val/1000) + 'K';
            return val.toLocaleString();
        }

        function renderCards(occs, isSuggested = false) {
            sidebarContent.innerHTML = occs.map(occ => {
                const isFav = favorites.includes(occ.code);
                const suggested = isSuggested || suggestedCodes.includes(occ.code);
                return `
                <div class="occ-card ${suggested ? 'suggested' : ''}" data-code="${occ.code}">
                    <div class="occ-card-header" onclick="toggleCard('${occ.code}')">
                        <div style="flex:1">
                            <div class="occ-card-title">${occ.title}</div>
                            <div class="occ-card-meta">
                                <span class="occ-card-stat"><strong>${formatSalary(occ.median_pay)}</strong>/yr</span>
                                ${getGrowthBadge(occ.outlook, occ.growth_pct)}
                            </div>
                        </div>
                        <div class="occ-card-actions">
                            <button class="occ-card-btn occ-card-btn-fav ${isFav ? 'favorited' : ''}"
                                    onclick="event.stopPropagation(); toggleFavorite('${occ.code}')">
                                ${isFav ? '♥' : '♡'}
                            </button>
                            <span class="expand-icon">▼</span>
                        </div>
                    </div>
                    <div class="occ-card-details">
                        <p>${occ.description}</p>
                        ${occ.url ? `<p style="margin-top:8px;"><a href="${occ.url}" target="_blank" rel="noopener" style="color:#667eea;text-decoration:none;font-size:12px;">📖 View full profile on BLS.gov →</a></p>` : ''}
                        <div class="detail-row"><span class="detail-label">Jobs (2024)</span><span class="detail-value">${formatJobs(occ.num_jobs)}</span></div>
                        <div class="detail-row"><span class="detail-label">Growth</span><span class="detail-value">${occ.growth_pct || 'N/A'}% (2024-34)</span></div>
                        <div class="detail-row"><span class="detail-label">Openings/yr</span><span class="detail-value">${formatJobs(occ.openings)}</span></div>
                        <div class="detail-row"><span class="detail-label">Education</span><span class="detail-value">${occ.education}</span></div>
                        <div class="card-actions-row">
                            <button class="occ-card-btn btn-ask" onclick="askAbout('${occ.code}')">Ask About This</button>
                            <button class="occ-card-btn btn-state" onclick="askStateData('${occ.code}', '${occ.title}')">State Data</button>
                        </div>
                    </div>
                </div>`;
            }).join('');
        }

        function toggleCard(code) {
            document.querySelector(`.occ-card[data-code="${code}"]`).classList.toggle('expanded');
        }

        function toggleFavorite(code) {
            if (favorites.includes(code)) {
                favorites = favorites.filter(c => c !== code);
            } else {
                favorites.push(code);
            }
            localStorage.setItem('careerFavorites', JSON.stringify(favorites));
            updateFavCount();
            renderCurrentTab();
        }

        function updateFavCount() {
            document.getElementById('favCount').textContent = favorites.length;
        }

        function filterByCategory() { searchBox.value = ''; renderCurrentTab(); }
        function searchOccupations() { categorySelect.value = ''; renderCurrentTab(); }

        function askAbout(code) {
            const occ = allOccupations.find(o => o.code === code);
            if (!occ) return;
            userInput.value = `Tell me about ${occ.title} (code: ${code}). It pays ${formatSalary(occ.median_pay)}/year, requires ${occ.education}, and has ${occ.growth_pct}% projected growth. What does the day-to-day work look like? What skills do I need? Is this a good career path?`;
            userInput.focus();
        }

        function askStateData(code, title) {
            const state = prompt('Enter a state name (e.g., California, Texas, Idaho):');
            if (!state) return;
            userInput.value = `Show me the job market data for ${title} (code: ${code}) in ${state}. What's the salary, employment, and how does it compare to the national average?`;
            sendMessage(new Event('submit'));
        }

        // Suggest careers from chat (called via response parsing)
        function suggestCareers(codes) {
            suggestedCodes = codes;
            document.querySelector('[data-tab="suggested"]').innerHTML =
                `Suggested <span class="badge">${codes.length}</span>`;
            if (codes.length > 0) switchTab('suggested');
        }

        // Compare view
        function openCompare() {
            if (favorites.length === 0) {
                alert('Add some favorites first by clicking the heart icon on careers.');
                return;
            }
            const favOccs = allOccupations.filter(o => favorites.includes(o.code));
            const fields = [
                ['Title', o => o.title],
                ['Salary', o => formatSalary(o.median_pay) + '/yr'],
                ['Education', o => o.education],
                ['Jobs (2024)', o => formatJobs(o.num_jobs)],
                ['Growth %', o => (o.growth_pct || 'N/A') + '%'],
                ['Outlook', o => o.outlook || 'N/A'],
                ['Openings/yr', o => formatJobs(o.openings)],
                ['Category', o => o.category.replace(/-/g, ' ')],
            ];
            let html = '<tbody>';
            fields.forEach(([label, fn]) => {
                html += `<tr><th>${label}</th>`;
                favOccs.forEach(o => html += `<td>${fn(o)}</td>`);
                html += '</tr>';
            });
            html += '</tbody>';
            document.getElementById('compareTable').innerHTML = html;
            document.getElementById('comparePanel').classList.add('show');
        }

        function closeCompare() {
            document.getElementById('comparePanel').classList.remove('show');
        }

        function renderMarkdown(text) {
            // Parse suggested careers
            const suggestMatch = text.match(/\\[SUGGEST:([^\\]]+)\\]/);
            if (suggestMatch) {
                const codes = suggestMatch[1].split(',').map(c => c.trim());
                suggestCareers(codes);
                text = text.replace(/\\[SUGGEST:[^\\]]+\\]/g, '');
            }
            // Headers
            text = text.replace(/^### (.+)$/gm, '<h4 style="margin:8px 0 4px;font-size:0.85em;">$1</h4>');
            text = text.replace(/^## (.+)$/gm, '<h3 style="margin:10px 0 6px;font-size:0.95em;">$1</h3>');
            text = text.replace(/^# (.+)$/gm, '<h2 style="margin:12px 0 8px;font-size:1.05em;">$1</h2>');
            // Bold and italic
            text = text.replace(/\\*\\*\\*(.+?)\\*\\*\\*/g, '<strong><em>$1</em></strong>');
            text = text.replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>');
            text = text.replace(/\\*(.+?)\\*/g, '<em>$1</em>');
            // Inline code
            text = text.replace(/`([^`]+)`/g, '<code style="background:#f0f0f0;padding:1px 4px;border-radius:3px;font-size:0.9em;">$1</code>');
            // Lists - unordered
            text = text.replace(/^[\\-\\*] (.+)$/gm, '<li style="margin-left:16px;margin-bottom:2px;">$1</li>');
            // Lists - ordered
            text = text.replace(/^(\\d+)\\. (.+)$/gm, '<li style="margin-left:16px;margin-bottom:2px;">$2</li>');
            // Wrap consecutive list items
            text = text.replace(/(<li[^>]*>.*<\\/li>\\n?)+/g, '<ul style="margin:4px 0;padding-left:8px;list-style:none;">$&</ul>');
            // Tables (improved)
            const tableRegex = /(^\\|.+\\|$\\n?)+/gm;
            text = text.replace(tableRegex, (tableBlock) => {
                const rows = tableBlock.trim().split('\\n').filter(r => r.trim());
                let html = '<table style="border-collapse:collapse;margin:8px 0;font-size:0.95em;border:1px solid #ddd;border-radius:4px;overflow:hidden;">';
                let isFirstRow = true;
                rows.forEach(row => {
                    const cells = row.replace(/^\\|/, '').replace(/\\|$/, '').split('|').map(c => c.trim());
                    // Skip separator row (----)
                    if (cells.every(c => /^[-:]+$/.test(c))) return;
                    if (isFirstRow) {
                        html += '<tr style="background:#f5f5f5;">' + cells.map(c =>
                            `<th style="padding:6px 10px;border:1px solid #ddd;font-weight:600;text-align:left;">${c}</th>`
                        ).join('') + '</tr>';
                        isFirstRow = false;
                    } else {
                        html += '<tr>' + cells.map(c =>
                            `<td style="padding:5px 10px;border:1px solid #eee;">${c}</td>`
                        ).join('') + '</tr>';
                    }
                });
                html += '</table>';
                return html;
            });
            // Line breaks and paragraphs
            text = text.split('\\n\\n').map(p => {
                p = p.trim();
                if (!p) return '';
                if (p.startsWith('<h') || p.startsWith('<ul') || p.startsWith('<table')) return p;
                return `<p style="margin-bottom:6px;">${p.replace(/\\n/g, '<br>')}</p>`;
            }).join('');
            return text;
        }

        function addMessage(content, role) {
            const div = document.createElement('div');
            div.className = `message ${role}`;
            const formatted = renderMarkdown(content);
            div.innerHTML = `<div class="message-content">${formatted}</div>`;
            chatArea.appendChild(div);
            chatArea.scrollTop = chatArea.scrollHeight;
        }

        function showTyping() {
            const div = document.createElement('div');
            div.className = 'message assistant';
            div.id = 'typingMessage';
            div.innerHTML = `<div class="typing-indicator show"><span></span><span></span><span></span></div>`;
            chatArea.appendChild(div);
            chatArea.scrollTop = chatArea.scrollHeight;
        }
        function hideTyping() { document.getElementById('typingMessage')?.remove(); }

        async function sendMessage(e) {
            e.preventDefault();
            const message = userInput.value.trim();
            if (!message) return;
            addMessage(message, 'user');
            userInput.value = '';
            sendBtn.disabled = true;
            showTyping();
            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message})
                });
                const data = await response.json();
                hideTyping();
                if (data.error) {
                    addMessage('**Error:** ' + data.error, 'assistant');
                } else {
                    addMessage(data.response, 'assistant');
                }
            } catch (error) {
                hideTyping();
                if (error.name === 'TypeError' && !navigator.onLine) {
                    addMessage('You appear to be offline. Please check your connection and try again.', 'assistant');
                } else {
                    addMessage('Sorry, something went wrong. Please try again.', 'assistant');
                }
            }
            sendBtn.disabled = false;
            userInput.focus();
        }

        async function resetChat() {
            await fetch('/reset', {method: 'POST'});
            suggestedCodes = [];
            document.querySelector('[data-tab="suggested"]').innerHTML = 'Suggested';
            chatArea.innerHTML = `
                <div class="message assistant">
                    <div class="message-content">
                        <p>Hi! I'm your career counselor with data on 340+ occupations.</p>
                        <p>Tell me about yourself - what subjects do you enjoy? What are your strengths? Any states you'd like to work in?</p>
                    </div>
                </div>`;
        }

        userInput.focus();
        loadOccupations();
    </script>
    <footer class="site-footer">
        <a href="https://github.com/davehedengren/project-demo-econ-2026" target="_blank" rel="noopener noreferrer">View on GitHub</a>
    </footer>
</body>
</html>
"""


def get_chatbot():
    """Get or create chatbot for current session."""
    session_id = session.get('session_id')
    if not session_id:
        session_id = os.urandom(16).hex()
        session['session_id'] = session_id
    if session_id not in chatbots:
        chatbots[session_id] = create_chatbot()
    return chatbots[session_id]


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/health')
def health():
    return jsonify({'status': 'ok'}), 200


@app.route('/api/occupations')
def get_occupations():
    """Get all occupations for the explore panel."""
    try:
        rows = occupation_store.get_all_for_api()
        occs = [{
            "code": r["code"],
            "title": r["title"],
            "description": r["description"],
            "category": r["category"],
            "median_pay": r["median_pay_annual"],
            "education": r["entry_level_education"],
            "outlook": r["employment_outlook"],
            "growth_pct": r["employment_outlook_value"],
            "num_jobs": r["number_of_jobs"],
            "openings": r["employment_openings"],
            "url": r["url"],
        } for r in rows]
        return jsonify({"occupations": occs, "categories": sorted(occupation_store.categories)})
    except Exception as e:
        logger.error("Error loading occupations: %s", e, exc_info=True)
        return jsonify({"error": "Failed to load occupation data."}), 500


@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    if not data:
        return jsonify({'error': 'Invalid request body.'}), 400
    message = data.get('message', '')
    if not message:
        return jsonify({'error': 'No message provided'}), 400
    try:
        chatbot = get_chatbot()
        response = chatbot.chat(message)
        return jsonify({'response': response})
    except Exception as e:
        print(f"Chat error: {type(e).__name__}: {e}")
        return jsonify({'error': 'Something went wrong'}), 500


@app.route('/reset', methods=['POST'])
def reset():
    try:
        chatbot = get_chatbot()
        chatbot.reset()
        return jsonify({'status': 'ok'})
    except Exception as e:
        logger.error("Error resetting chat: %s", e, exc_info=True)
        return jsonify({'error': 'Failed to reset conversation.'}), 500


def run_cli():
    """Run the chatbot in CLI mode."""
    print("Career Counselor Chatbot")
    print("=" * 40)
    print("Loading BLS occupation data...")
    chatbot = create_chatbot()
    print(f"Loaded {chatbot.store.count} occupations.")
    print("\nHi! I'm your career counselor. Tell me about yourself -")
    print("what subjects do you enjoy? What are your strengths?")
    print("Are there any locations you'd like to work in?")
    print("\nType 'quit' to exit, 'reset' to start over.")
    print("-" * 40)

    while True:
        try:
            user_input = input("\nYou: ").strip()
            if not user_input: continue
            if user_input.lower() == 'quit':
                print("Goodbye!")
                break
            if user_input.lower() == 'reset':
                chatbot.reset()
                print("\nConversation reset. Let's start fresh!")
                continue
            print("\nCounselor: ", end="", flush=True)
            for chunk in chatbot.chat_stream(user_input):
                print(chunk, end="", flush=True)
            print()
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except ChatbotError as e:
            print(f"\n\nError: {e}")
            print("Please try again.")
        except Exception as e:
            logger.error("Unexpected CLI error: %s", e, exc_info=True)
            print(f"\n\nSomething went wrong: {e}")
            print("Please try again.")


def main():
    """Main entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Career Counselor Chatbot")
    parser.add_argument('--cli', action='store_true', help='Run in CLI mode')
    parser.add_argument('--port', type=int, default=8080, help='Port for web server')
    parser.add_argument('--host', default='0.0.0.0', help='Host for web server')
    args = parser.parse_args()

    if args.cli:
        run_cli()
    else:
        print(f"Starting Career Counselor web interface...")
        print(f"Open http://localhost:{args.port} in your browser")
        app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
