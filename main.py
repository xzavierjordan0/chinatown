import sys
import io
import os
import re
import signal
import threading
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import uvicorn
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, \
    MessageHandler, filters, ContextTypes, Application
from sqlalchemy import create_engine, text, and_
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import func

# ============================================================================
# 📦 IMPORTS
# ============================================================================

try:
    from database.models import User, Card, Order, Payment, Base
    from config.settings import BOT_TOKEN, USDT_ADDRESS, BTC_ADDRESS, LTC_ADDRESS, \
        ADMIN_IDS, DATABASE_URL, DEFAULT_NAKED_PRICE, DEFAULT_CLOTHED_PRICE
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from database.models import User, Card, Order, Payment, Base
    from config.settings import BOT_TOKEN, USDT_ADDRESS, BTC_ADDRESS, LTC_ADDRESS, \
        ADMIN_IDS, DATABASE_URL, DEFAULT_NAKED_PRICE, DEFAULT_CLOTHED_PRICE

# ============================================================================
# ⚙️ CONFIGURATION
# ============================================================================

APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", 8000))
WEBAPP_URL = os.getenv("WEBAPP_URL", f"https://localhost:{APP_PORT}")

# ============================================================================
# 🎨 HTML TEMPLATES (Embedded for single-file deployment)
# ============================================================================

WEBAPP_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chinatown Market</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #fff;
            min-height: 100vh;
        }
        .container { max-width: 800px; margin: 0 auto; padding: 20px; }
        .header {
            text-align: center;
            padding: 30px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .header h1 { font-size: 28px; margin-bottom: 10px; }
        .header p { color: #8892b0; }
        .balance-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 16px;
            padding: 20px;
            margin: 20px 0;
            text-align: center;
        }
        .balance-card .amount { font-size: 36px; font-weight: bold; }
        .balance-card .label { opacity: 0.8; margin-bottom: 10px; }
        .nav-buttons { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin: 20px 0; }
        .nav-btn {
            background: rgba(255,255,255,0.1);
            border: none;
            padding: 15px 20px;
            border-radius: 12px;
            color: #fff;
            font-size: 16px;
            cursor: pointer;
            transition: all 0.3s;
        }
        .nav-btn:hover { background: rgba(255,255,255,0.2); transform: translateY(-2px); }
        .card-grid { display: grid; gap: 15px; margin: 20px 0; }
        .card-item {
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 15px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .card-item .bin { font-size: 24px; font-weight: bold; margin-bottom: 5px; }
        .card-item .details { display: grid; grid-template-columns: repeat(2, 1fr); gap: 5px; font-size: 14px; color: #8892b0; }
        .card-item .type-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            margin-top: 10px;
        }
        .type-badge.clothed { background: #10b981; }
        .type-badge.naked { background: #f59e0b; }
        .card-item .price { font-size: 18px; color: #10b981; margin-top: 10px; }
        .card-item .buy-btn {
            width: 100%;
            padding: 10px;
            background: #667eea;
            border: none;
            border-radius: 8px;
            color: #fff;
            font-weight: bold;
            margin-top: 10px;
            cursor: pointer;
        }
        .search-box {
            width: 100%;
            padding: 15px;
            border: none;
            border-radius: 12px;
            background: rgba(255,255,255,0.1);
            color: #fff;
            font-size: 16px;
            margin: 20px 0;
        }
        .search-box::placeholder { color: #8892b0; }
        .section { display: none; }
        .section.active { display: block; }
        .loading { text-align: center; padding: 40px; color: #8892b0; }
        .error { background: rgba(220, 38, 38, 0.2); padding: 15px; border-radius: 8px; margin: 10px 0; }
        .success { background: rgba(16, 185, 129, 0.2); padding: 15px; border-radius: 8px; margin: 10px 0; }
        .crypto-btn {
            width: 100%;
            padding: 12px;
            margin: 8px 0;
            border: none;
            border-radius: 8px;
            font-weight: bold;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        .crypto-btn.usdt { background: #26A17B; }
        .crypto-btn.btc { background: #F7931A; }
        .crypto-btn.ltc { background: #345D9D; }
        .crypto-btn:hover { opacity: 0.9; }
        .crypto-address {
            background: rgba(255,255,255,0.1);
            padding: 15px;
            border-radius: 8px;
            word-break: break-all;
            font-size: 12px;
            margin: 10px 0;
        }
        .filter-buttons { display: flex; gap: 8px; margin: 15px 0; flex-wrap: wrap; }
        .filter-btn {
            padding: 8px 16px;
            border: 1px solid rgba(255,255,255,0.3);
            border-radius: 20px;
            background: transparent;
            color: #fff;
            cursor: pointer;
            font-size: 14px;
        }
        .filter-btn.active { background: #667eea; border-color: #667eea; }
        .filter-btn:hover { background: rgba(102, 126, 234, 0.3); }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏮 Chinatown Market</h1>
            <p>Premium Card Marketplace</p>
        </div>
        
        <!-- Home Section -->
        <div id="home" class="section active">
            <div class="balance-card">
                <div class="label">Your Balance</div>
                <div class="amount" id="balance">Loading...</div>
            </div>
            <div class="nav-buttons">
                <button class="nav-btn" onclick="showSection('catalog')">📦 Browse Cards</button>
                <button class="nav-btn" onclick="showSection('binsearch')">🔍 BIN Search</button>
                <button class="nav-btn" onclick="showSection('history')">📜 History</button>
                <button class="nav-btn" onclick="showSection('topup')">💰 Top Up</button>
            </div>
        </div>
        
        <!-- Catalog Section -->
        <div id="catalog" class="section">
            <h2>📦 Available Cards</h2>
            
            <div class="filter-buttons">
                <button class="filter-btn active" onclick="filterByType('all', this)">All</button>
                <button class="filter-btn" onclick="filterByType('clothed', this)">👔 Clothed</button>
                <button class="filter-btn" onclick="filterByType('naked', this)">👕 Naked</button>
            </div>
            
            <div class="filter-buttons">
                <button class="filter-btn active" onclick="filterByCountry('all', this)">All Countries</button>
                <button class="filter-btn" onclick="filterByCountry('US', this)">🇺🇸 USA</button>
                <button class="filter-btn" onclick="filterByCountry('CA', this)">🇨🇦 Canada</button>
                <button class="filter-btn" onclick="filterByCountry('UK', this)">🇬🇧 UK</button>
            </div>
            
            <input type="text" class="search-box" placeholder="Search by BIN..." oninput="filterCards(this.value)">
            <div id="card-grid" class="card-grid"></div>
            <button class="nav-btn" style="width:100%; margin-top:20px;" onclick="showSection('home')">← Back</button>
        </div>
        
        <!-- BIN Search Section -->
        <div id="binsearch" class="section">
            <h2>🔍 BIN Search</h2>
            <input type="text" class="search-box" id="bin-input" placeholder="Enter 6-digit BIN" maxlength="6">
            <button class="nav-btn" style="width:100%" onclick="searchBIN()">Search</button>
            <div id="bin-results" style="margin-top:20px;"></div>
            <button class="nav-btn" style="width:100%; margin-top:20px;" onclick="showSection('home')">← Back</button>
        </div>
        
        <!-- History Section -->
        <div id="history" class="section">
            <h2>📜 Purchase History</h2>
            <div id="history-list"></div>
            <button class="nav-btn" style="width:100%; margin-top:20px;" onclick="showSection('home')">← Back</button>
        </div>
        
        <!-- Top Up Section -->
        <div id="topup" class="section">
            <h2>💰 Top Up Balance</h2>
            
            <button class="crypto-btn usdt" onclick="showCrypto('USDT')">
                💎 USDT (TRC20)
            </button>
            <button class="crypto-btn btc" onclick="showCrypto('BTC')">
                ₿ Bitcoin
            </button>
            <button class="crypto-btn ltc" onclick="showCrypto('LTC')">
                🥌 Litecoin
            </button>
            
            <div id="crypto-display" style="margin-top:20px;">
                <div class="label" id="crypto-label">Select a payment method</div>
                <div class="crypto-address" id="crypto-address"></div>
                <button class="nav-btn" style="width:100%" onclick="copyAddress()">📋 Copy Address</button>
            </div>
            
            <button class="nav-btn" style="width:100%; margin-top:20px;" onclick="showSection('home')">← Back</button>
        </div>
    </div>
    
    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        
        let userData = null;
        let allCards = [];
        let currentTypeFilter = 'all';
        let currentCountryFilter = 'all';
        
        document.addEventListener('DOMContentLoaded', () => {
            fetchUserData();
        });
        
        async function fetchUserData() {
            try {
                const response = await fetch('/api/user');
                userData = await response.json();
                document.getElementById('balance').textContent = `$${userData.balance?.toFixed(2) || '0.00'} USDT`;
            } catch (e) {
                console.error('Failed to fetch user data:', e);
            }
        }
        
        async function loadCatalog() {
            try {
                const response = await fetch('/api/cards');
                allCards = await response.json();
                renderCards(allCards);
            } catch (e) {
                console.error('Failed to load cards:', e);
            }
        }
        
        function renderCards(cards) {
            const grid = document.getElementById('card-grid');
            if (!cards.length) {
                grid.innerHTML = '<div class="loading">No cards available</div>';
                return;
            }
            grid.innerHTML = cards.map(card => `
                <div class="card-item">
                    <div class="bin">${card.bin} ****${card.number.slice(-4)}</div>
                    <div class="details">
                        <div>📅 ${card.expiry}</div>
                        <div>🌍 ${card.country}</div>
                    </div>
                    <div class="type-badge ${card.billing ? 'clothed' : 'naked'}">
                        ${card.billing ? '👔 CLOTHED' : '👕 NAKED'}
                    </div>
                    <div class="price">$${card.price?.toFixed(2)} USDT</div>
                    <button class="buy-btn" onclick="buyCard(${card.id})">🛒 Buy Now</button>
                </div>
            `).join('');
        }
        
        function filterCards(query) {
            let filtered = allCards;
            if (currentTypeFilter !== 'all') {
                filtered = filtered.filter(card => currentTypeFilter === 'clothed' ? card.billing : !card.billing);
            }
            if (currentCountryFilter !== 'all') {
                filtered = filtered.filter(card => card.country === currentCountryFilter);
            }
            if (query) {
                filtered = filtered.filter(card => card.bin.includes(query));
            }
            renderCards(filtered);
        }
        
        function filterByType(type, btn) {
            currentTypeFilter = type;
            document.querySelectorAll('.filter-buttons .filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            filterCards('');
        }
        
        function filterByCountry(country, btn) {
            currentCountryFilter = country;
            document.querySelectorAll('.filter-buttons .filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            filterCards('');
        }
        
        async function searchBIN() {
            const bin = document.getElementById('bin-input').value;
            if (!bin || bin.length !== 6) {
                tg.showAlert('Please enter a valid 6-digit BIN');
                return;
            }
            try {
                const response = await fetch(`/api/bin/${bin}`);
                const results = await response.json();
                document.getElementById('bin-results').innerHTML = `
                    <div class="success">
                        <strong>${results.clothed_count} Clothed</strong>, 
                        <strong>${results.naked_count} Naked</strong> available
                    </div>
                    <button class="nav-btn" style="width:100%; margin-top:10px;" onclick="orderFromBIN('${bin}', 'cloth')">🛒 Order Clothed ($${results.clothed_price})</button>
                    <button class="nav-btn" style="width:100%; margin-top:10px;" onclick="orderFromBIN('${bin}', 'naked')">🛒 Order Naked ($${results.naked_price})</button>
                `;
            } catch (e) {
                console.error('BIN search failed:', e);
            }
        }
        
        async function buyCard(cardId) {
            if (!confirm('Confirm purchase?')) return;
            try {
                const response = await fetch('/api/purchase', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ card_id: cardId })
                });
                const result = await response.json();
                if (result.success) {
                    tg.showAlert('✅ Purchase successful! Check Telegram for your card file.');
                    fetchUserData();
                    loadCatalog();
                } else {
                    tg.showAlert('❌ ' + result.error);
                }
            } catch (e) {
                tg.showAlert('Purchase failed: ' + e.message);
            }
        }
        
        async function orderFromBIN(bin, type) {
            tg.sendData(JSON.stringify({ action: 'order', bin, type }));
        }
        
        function showCrypto(crypto) {
            const addresses = {
                'USDT': '${USDT_ADDRESS}',
                'BTC': '${BTC_ADDRESS}',
                'LTC': '${LTC_ADDRESS}'
            };
            document.getElementById('crypto-label').textContent = crypto + ' Address';
            document.getElementById('crypto-address').textContent = addresses[crypto];
        }
        
        function copyAddress() {
            const address = document.getElementById('crypto-address').textContent;
            navigator.clipboard.writeText(address);
            tg.showAlert('Address copied!');
        }
        
        function showSection(id) {
            document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
            document.getElementById(id).classList.add('active');
            if (id === 'catalog') loadCatalog();
            if (id === 'history') loadHistory();
        }
        
        async function loadHistory() {
            try {
                const response = await fetch('/api/history');
                const orders = await response.json();
                const list = document.getElementById('history-list');
                if (!orders.length) {
                    list.innerHTML = '<div class="loading">No order history</div>';
                    return;
                }
                list.innerHTML = orders.map(order => `
                    <div class="card-item">
                        <div>
                            <strong>Order #${order.id}</strong> - ${order.details}
                        </div>
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:10px;">
                            <span>$${order.amount?.toFixed(2)} USDT • ${new Date(order.created_at).toLocaleDateString()}</span>
                            <button class="nav-btn" style="padding:8px 16px; font-size:14px;" 
                                    onclick="downloadOrder(${order.id})">📄 Download</button>
                        </div>
                    </div>
                `).join('');
            } catch (e) {
                console.error('Failed to load history:', e);
            }
        }
        
        async function downloadOrder(orderId) {
            try {
                const response = await fetch(`/api/order/${orderId}/download`);
                if (!response.ok) throw new Error('Download failed');
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `order_${orderId}.txt`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                tg.showAlert('✅ Download started!');
            } catch (e) {
                tg.showAlert('❌ Download failed: ' + e.message);
            }
        }
    </script>
</body>
</html>
"""

ADMIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin - Chinatown Market</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #fff; min-height: 100vh; }
        .container { max-width: 1000px; margin: 0 auto; padding: 20px; }
        .header { text-align: center; padding: 30px 0; border-bottom: 1px solid rgba(255,255,255,0.1); }
        .header h1 { font-size: 28px; margin-bottom: 10px; }
        .stats-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin: 20px 0; }
        .stat-card { background: rgba(255,255,255,0.05); border-radius: 12px; padding: 20px; text-align: center; }
        .stat-card .value { font-size: 32px; font-weight: bold; color: #667eea; }
        .stat-card .label { opacity: 0.7; margin-top: 5px; }
        .section { margin: 30px 0; }
        .section h2 { margin-bottom: 15px; }
        .btn { background: #667eea; border: none; padding: 12px 24px; border-radius: 8px; color: #fff; font-weight: bold; cursor: pointer; margin: 5px; }
        .btn:hover { background: #5a67d8; }
        .btn-danger { background: #ef4444; }
        .btn-success { background: #10b981; }
        textarea { width: 100%; height: 150px; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; color: #fff; padding: 15px; font-family: monospace; }
        input[type="file"] { margin: 15px 0; }
        .form-group { margin: 15px 0; }
        .form-group label { display: block; margin-bottom: 5px; opacity: 0.8; }
        .form-group input { width: 100%; padding: 12px; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; color: #fff; }
        .card-table { width: 100%; border-collapse: collapse; margin: 15px 0; }
        .card-table th, .card-table td { padding: 12px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); }
        .card-table th { background: rgba(255,255,255,0.05); }
        .badge { padding: 4px 10px; border-radius: 20px; font-size: 12px; }
        .badge-sold { background: #ef4444; }
        .badge-available { background: #10b981; }
        .loading { text-align: center; padding: 40px; opacity: 0.7; }
        .message { padding: 15px; border-radius: 8px; margin: 15px 0; }
        .message.success { background: rgba(16, 185, 129, 0.2); }
        .message.error { background: rgba(239, 68, 68, 0.2); }
        .payment-list { margin: 15px 0; }
        .payment-item {
            background: rgba(255,255,255,0.05);
            padding: 15px;
            margin: 10px 0;
            border-radius: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .payment-item.pending { border-left: 3px solid #f59e0b; }
        .payment-item.confirmed { border-left: 3px solid #10b981; }
        .payment-item.rejected { border-left: 3px solid #ef4444; }
        .payment-actions button { margin: 0 5px; padding: 6px 12px; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏮 Chinatown Market - Admin</h1>
            <p>Store Management Panel</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="value" id="total-cards">-</div>
                <div class="label">Total Cards</div>
            </div>
            <div class="stat-card">
                <div class="value" id="available-cards">-</div>
                <div class="label">Available</div>
            </div>
            <div class="stat-card">
                <div class="value" id="total-users">-</div>
                <div class="label">Total Users</div>
            </div>
            <div class="stat-card">
                <div class="value" id="total-orders">-</div>
                <div class="label">Total Orders</div>
            </div>
            <div class="stat-card">
                <div class="value" id="total-revenue">-</div>
                <div class="label">Total Revenue</div>
            </div>
            <div class="stat-card">
                <div class="value" id="pending-payments">-</div>
                <div class="label">Pending Payments</div>
            </div>
        </div>
        
        <div class="section">
            <h2>📤 Upload Cards</h2>
            <div class="form-group">
                <label>Upload File (.txt, .csv, .dat)</label>
                <input type="file" id="upload-file" accept=".txt,.csv,.dat,.log">
            </div>
            <div class="form-group">
                <label>Paste Raw Data (Format: cc|mm|yy|cvv|name|address)</label>
                <textarea id="raw-data" placeholder="4147201234567890|12|28|567|John Smith|123 Main St, New York, NY 10001"></textarea>
            </div>
            <div class="form-group">
                <label>Default Price for Naked Cards</label>
                <input type="number" id="naked-price" placeholder="0.33" step="0.01">
            </div>
            <div class="form-group">
                <label>Default Price for Clothed Cards</label>
                <input type="number" id="clothed-price" placeholder="25.00" step="0.01">
            </div>
            <button class="btn btn-success" onclick="uploadData()">🚀 Process & Upload</button>
            <div id="upload-result"></div>
        </div>
        
        <div class="section">
            <h2>💰 Payment Management</h2>
            <button class="btn" onclick="loadPayments()">🔄 Refresh Payments</button>
            <div id="payments-list" class="payment-list"></div>
        </div>
        
        <div class="section">
            <h2>📋 Recent Cards</h2>
            <button class="btn" onclick="loadCards()">🔄 Refresh</button>
            <button class="btn" onclick="exportCards()">📥 Export All</button>
            <div id="cards-container"></div>
        </div>
        
        <div class="section">
            <h2>💰 Price Management</h2>
            <div class="form-group">
                <label>Update BIN Price</label>
                <div style="display: flex; gap: 10px;">
                    <input type="text" id="bin-update" placeholder="BIN (6 digits)" maxlength="6">
                    <input type="number" id="bin-price" placeholder="Price" step="0.01">
                    <button class="btn" onclick="updateBINPrice()">Update</button>
                </div>
            </div>
            <button class="btn" onclick="updateDefaultPrices()">💾 Update Default Prices</button>
        </div>
        
        <div class="section">
            <h2>📂 Database Actions</h2>
            <button class="btn btn-danger" onclick="clearSoldCards()">🗑️ Clear Sold Cards</button>
            <button class="btn" onclick="exportCards()">📥 Export All Cards</button>
            <button class="btn" onclick="exportRevenue()">📊 Export Revenue Report</button>
        </div>
        
                <div class="section">
            <h2>👥 User Management</h2>
            <button class="btn" onclick="loadUsers()">👥 Load Users</button>
            <div id="users-container"></div>
        </div>
    </div>
    
    <script>
        async function loadStats() {
            try {
                const response = await fetch('/api/admin/stats');
                const data = await response.json();
                document.getElementById('total-cards').textContent = data.total_cards;
                document.getElementById('available-cards').textContent = data.available;
                document.getElementById('total-users').textContent = data.total_users;
                document.getElementById('total-orders').textContent = data.total_orders;
                document.getElementById('total-revenue').textContent = '$' + data.total_revenue.toFixed(2);
                document.getElementById('pending-payments').textContent = data.pending_payments;
            } catch (e) {
                console.error('Failed to load stats:', e);
            }
        }
        
        async function loadCards() {
            try {
                const response = await fetch('/api/admin/cards');
                const cards = await response.json();
                renderCards(cards);
            } catch (e) {
                console.error('Failed to load cards:', e);
            }
        }
        
        function renderCards(cards) {
            const container = document.getElementById('cards-container');
            if (!cards.length) {
                container.innerHTML = '<div class="loading">No cards found</div>';
                return;
            }
            const html = `
                <table class="card-table">
                    <thead>
                        <tr>
                            <th>BIN</th>
                            <th>Number</th>
                            <th>Expiry</th>
                            <th>Country</th>
                            <th>Type</th>
                            <th>Price</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${cards.slice(0, 20).map(card => `
                            <tr>
                                <td>${card.bin}</td>
                                <td>****${card.number.slice(-4)}</td>
                                <td>${card.expiry}</td>
                                <td>${card.country}</td>
                                <td>${card.billing ? '👔 Clothed' : '👕 Naked'}</td>
                                <td>$${card.price?.toFixed(2)}</td>
                                <td><span class="badge ${card.is_sold ? 'badge-sold' : 'badge-available'}">${card.is_sold ? 'SOLD' : 'Available'}</span></td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
            container.innerHTML = html;
        }
        
        async function uploadData() {
            const fileInput = document.getElementById('upload-file');
            const rawData = document.getElementById('raw-data').value;
            const nakedPrice = parseFloat(document.getElementById('naked-price').value) || 0.33;
            const clothedPrice = parseFloat(document.getElementById('clothed-price').value) || 25.00;
            const resultDiv = document.getElementById('upload-result');
            
            resultDiv.innerHTML = '<div class="loading">Processing...</div>';
            
            try {
                let formData = new FormData();
                
                if (fileInput.files.length > 0) {
                    formData.append('file', fileInput.files[0]);
                }
                
                if (rawData.trim()) {
                    const blob = new Blob([rawData], { type: 'text/plain' });
                    formData.append('raw_data', blob);
                }
                
                formData.append('naked_price', nakedPrice);
                formData.append('clothed_price', clothedPrice);
                
                const response = await fetch('/api/admin/upload', {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();
                
                if (result.success) {
                    resultDiv.innerHTML = `<div class="message success">✅ ${result.message}</div>`;
                    setTimeout(() => {
                        loadCards();
                        loadStats();
                    }, 1500);
                } else {
                    resultDiv.innerHTML = `<div class="message error">❌ ${result.error}</div>`;
                }
            } catch (e) {
                resultDiv.innerHTML = `<div class="message error">❌ ${e.message}</div>`;
            }
        }
        
        async function loadPayments() {
            try {
                const response = await fetch('/api/admin/payments');
                const payments = await response.json();
                const list = document.getElementById('payments-list');
                
                if (!payments.length) {
                    list.innerHTML = '<div class="loading">No pending payments</div>';
                    return;
                }
                
                list.innerHTML = payments.map(payment => `
                    <div class="payment-item ${payment.status}">
                        <div>
                            <strong>💰 ${payment.amount.toFixed(2)} ${payment.crypto_type}</strong><br>
                            <small>User: ${payment.telegram_id} | ${new Date(payment.created_at).toLocaleString()}</small><br>
                            <small>Hash: ${payment.tx_hash || 'N/A'}</small>
                        </div>
                        <div class="payment-actions">
                            ${payment.status === 'pending' ? `
                                <button class="btn btn-success" onclick="approvePayment(${payment.id})">✅ Approve</button>
                                <button class="btn btn-danger" onclick="rejectPayment(${payment.id})">❌ Reject</button>
                            ` : ''}
                            <span>${payment.status.toUpperCase()}</span>
                        </div>
                    </div>
                `).join('');
            } catch (e) {
                console.error('Failed to load payments:', e);
            }
        }
        
        async function approvePayment(paymentId) {
            try {
                const response = await fetch(`/api/admin/payment/${paymentId}/approve`, { method: 'POST' });
                const result = await response.json();
                if (result.success) {
                    loadPayments();
                    loadStats();
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }
        
        async function rejectPayment(paymentId) {
            try {
                const response = await fetch(`/api/admin/payment/${paymentId}/reject`, { method: 'POST' });
                const result = await response.json();
                if (result.success) {
                    loadPayments();
                    loadStats();
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }
        
        async function updateBINPrice() {
            const bin = document.getElementById('bin-update').value;
            const price = parseFloat(document.getElementById('bin-price').value);
            
            if (!bin || !price || bin.length !== 6) {
                alert('Please enter valid BIN and price');
                return;
            }
            
            try {
                const response = await fetch('/api/admin/bin_price', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ bin: bin, price: price })
                });
                const result = await response.json();
                alert(result.message);
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }
        
        async function updateDefaultPrices() {
            const nakedPrice = parseFloat(document.getElementById('naked-price').value);
            const clothedPrice = parseFloat(document.getElementById('clothed-price').value);
            
            if (isNaN(nakedPrice) || isNaN(clothedPrice)) {
                alert('Please enter valid prices');
                return;
            }
            
            try {
                const response = await fetch('/api/admin/prices', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ naked_price: nakedPrice, clothed_price: clothedPrice })
                });
                const result = await response.json();
                alert(result.message);
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }
        
        async function clearSoldCards() {
            if (!confirm('Clear all sold cards?')) return;
            try {
                const response = await fetch('/api/admin/clear-sold', { method: 'DELETE' });
                const result = await response.json();
                alert(result.message);
                loadCards();
                loadStats();
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }
        
        async function exportCards() {
            window.location.href = '/api/admin/export';
        }
        
        async function exportRevenue() {
            window.location.href = '/api/admin/export-revenue';
        }
        
        async function loadUsers() {
            try {
                const response = await fetch('/api/admin/users');
                const users = await response.json();
                const container = document.getElementById('users-container');
                
                if (!users.length) {
                    container.innerHTML = '<div class="loading">No users found</div>';
                    return;
                }
                
                container.innerHTML = `
                    <table class="card-table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Telegram ID</th>
                                <th>Username</th>
                                <th>Balance</th>
                                <th>Orders</th>
                                <th>Admin</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${users.slice(0, 20).map(user => `
                                <tr>
                                    <td>${user.id}</td>
                                    <td>${user.telegram_id}</td>
                                    <td>${user.username || 'N/A'}</td>
                                    <td>$${user.balance?.toFixed(2)}</td>
                                    <td>${user.order_count || 0}</td>
                                    <td>${user.is_admin ? '✅' : '❌'}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `;
            } catch (e) {
                console.error('Failed to load users:', e);
            }
        }
        
        // Initialize
        loadStats();
        loadCards();
        loadPayments();
    </script>
</body>
</html>
"""

# ============================================================================
# 🧠 SMART CARD PARSER
# ============================================================================

class SmartCardParser:
    """Intelligent parser for card data with cardholder & billing detection"""
    
    CARD_NUMBER_PATTERN = re.compile(r'\b\d{13,19}\b')
    EXPIRY_PATTERN = re.compile(r'(\d{1,2})/(\d{2,4})')
    CVV_PATTERN = re.compile(r'\b\d{3,4}\b')
    
    NAME_PATTERNS = [
        re.compile(r'(?:name|cardholder|holder)\s*[:\-=]\s*([A-Za-z\s]+)', re.IGNORECASE),
        re.compile(r'([A-Z][a-z]+\s+[A-Z][a-z]+)', re.IGNORECASE),
    ]
    
    ADDRESS_PATTERNS = [
        re.compile(r'(?:address|billing)\s*[:\-=]\s*(.+?)(?:\n|$)', re.IGNORECASE),
        re.compile(r'(\d+\s+[A-Za-z\s]+,\s*[A-Za-z\s]+,\s*[A-Z]{2}\s*\d{5})', re.IGNORECASE),
    ]
    
    @classmethod
    def parse_line(cls, line: str) -> Optional[Dict[str, Any]]:
        """Parse a single line of card data"""
        if not line.strip() or line.startswith('#'):
            return None
        
        delimiters = ['|', ',', '\t', ';']
        delimiter = max(delimiters, key=lambda d: line.count(d))
        
        parts = [p.strip() for p in line.split(delimiter) if p.strip()]
        
        if len(parts) < 4:
            return None
        
        try:
            card_number = parts[0].strip()
            if not cls.CARD_NUMBER_PATTERN.fullmatch(card_number):
                return None
            
            expiry_month = parts[1].strip()
            expiry_year = parts[2].strip()
            cvv = parts[3].strip()
            
            if not expiry_month.isdigit() or not expiry_year.isdigit():
                return None
            if len(expiry_month) == 1:
                expiry_month = '0' + expiry_month
            if len(expiry_year) == 2:
                expiry_year = '20' + expiry_year
            
            expiry = f"{expiry_month}/{expiry_year}"
            bin_number = card_number[:6]
            
            cardholder = None
            if len(parts) > 4:
                potential_name = parts[4]
                if any(cls.NAME_PATTERNS[i].search(potential_name) for i in range(len(cls.NAME_PATTERNS))):
                    cardholder = potential_name
            
            billing_address = None
            has_billing = False
            if len(parts) > 5:
                potential_address = parts[5]
                if any(cls.ADDRESS_PATTERNS[i].search(potential_address) for i in range(len(cls.ADDRESS_PATTERNS))):
                    billing_address = potential_address
                    has_billing = True
            
            country = 'US'
            if has_billing and billing_address:
                country_codes = {
                    'US': ['United States', 'USA', 'US', 'CA', 'NY', 'TX', 'FL'],
                    'UK': ['United Kingdom', 'UK', 'GB', 'London', 'England'],
                    'CA': ['Canada', 'CA', 'ON', 'BC', 'Toronto'],
                    'DE': ['Germany', 'DE', 'Berlin', 'Munich'],
                    'FR': ['France', 'FR', 'Paris'],
                    'AU': ['Australia', 'AU', 'Sydney', 'Melbourne'],
                }
                for code, keywords in country_codes.items():
                    if any(kw.lower() in billing_address.lower() for kw in keywords):
                        country = code
                        break
            
            return {
                'bin': bin_number,
                'number': card_number,
                'expiry': expiry,
                'cvv': cvv,
                'country': country,
                'billing': has_billing,
                'cardholder': cardholder,
                'billing_address': billing_address,
                'price': DEFAULT_CLOTHED_PRICE if has_billing else DEFAULT_NAKED_PRICE
            }
        except (ValueError, IndexError) as e:
            return None
    
    @classmethod
    def parse_file(cls, file_path: str) -> tuple:
        """Parse entire file"""
        cards = []
        success = 0
        failed = 0
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                result = cls.parse_line(line)
                if result:
                    cards.append(result)
                    success += 1
                else:
                    failed += 1
        
        return cards, success, failed
    
    @classmethod
    def parse_raw_text(cls, text: str) -> tuple:
        """Parse raw pasted text"""
        cards = []
        success = 0
        failed = 0
        
        for line in text.strip().split('\n'):
            result = cls.parse_line(line)
            if result:
                cards.append(result)
                success += 1
            else:
                failed += 1
        
        return cards, success, failed


# ============================================================================
# 🚀 FASTAPI WEBAPP
# ============================================================================

app = FastAPI(title="Chinatown Market API", version="1.0.0")

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Path("static").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory="static", check_dir=False), name="static")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=create_engine(
    DATABASE_URL, echo=False, pool_pre_ping=True, pool_recycle=3600
))

# ============================================================================
# 📊 API ROUTES
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def webapp(request: Request):
    """Main webapp page"""
    return WEBAPP_HTML

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    """Admin panel page"""
    return ADMIN_HTML

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/api/user")
async def get_user():
    """Get current user data"""
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id="123456789").first()
        if not user:
            return {"id": 1, "telegram_id": "123456789", "balance": 0.00, "usdt_address": USDT_ADDRESS, "is_admin": False}
        return {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "balance": user.balance,
            "usdt_address": user.usdt_address,
            "btc_address": user.btc_address,
            "ltc_address": user.ltc_address,
            "is_admin": user.is_admin
        }
    finally:
        session.close()

@app.get("/api/cards")
async def get_cards(country: Optional[str] = None, card_type: Optional[str] = None):
    """Get available cards"""
    session = SessionLocal()
    try:
        query = session.query(Card).filter(Card.is_sold == False)
        
        if country and country != "all":
            query = query.filter(Card.country == country)
        
        if card_type == "clothed":
            query = query.filter(Card.billing == True)
        elif card_type == "naked":
            query = query.filter(Card.billing == False)
        
        cards = query.limit(100).all()
        return [{
            "id": card.id,
            "bin": card.bin,
            "number": card.number,
            "expiry": card.expiry,
            "cvv": card.cvv,
            "country": card.country,
            "billing": card.billing,
            "price": card.price,
            "is_sold": card.is_sold
        } for card in cards]
    finally:
        session.close()

@app.get("/api/bin/{bin_number}")
async def search_bin(bin_number: str):
    """Search cards by BIN"""
    if len(bin_number) != 6 or not bin_number.isdigit():
        raise HTTPException(status_code=400, detail="Invalid BIN number")
    
    session = SessionLocal()
    try:
        clothed = session.query(Card).filter(
            Card.bin == bin_number, Card.billing == True, Card.is_sold == False
        ).count()
        
        naked = session.query(Card).filter(
            Card.bin == bin_number, Card.billing == False, Card.is_sold == False
        ).count()
        
        clothed_price = session.query(Card).filter(
            Card.bin == bin_number, Card.billing == True
        ).first().price if session.query(Card).filter(
            Card.bin == bin_number, Card.billing == True
        ).first() else DEFAULT_CLOTHED_PRICE
        
        naked_price = session.query(Card).filter(
            Card.bin == bin_number, Card.billing == False
        ).first().price if session.query(Card).filter(
            Card.bin == bin_number, Card.billing == False
        ).first() else DEFAULT_NAKED_PRICE
        
        return {
            "bin": bin_number,
            "clothed_count": clothed,
            "naked_count": naked,
            "clothed_price": clothed_price,
            "naked_price": naked_price
        }
    finally:
        session.close()

@app.get("/api/history")
async def get_history():
    """Get user purchase history"""
    session = SessionLocal()
    try:
        orders = session.query(Order).filter(Order.user_id == 1).order_by(Order.created_at.desc()).limit(20).all()
        return [{
            "id": order.id,
            "amount": order.amount,
            "status": order.status,
            "details": order.details,
            "created_at": order.created_at.isoformat()
        } for order in orders]
    finally:
        session.close()

@app.post("/api/purchase")
async def purchase_card(card_id: int):
    """Process card purchase"""
    session = SessionLocal()
    try:
        card = session.query(Card).filter_by(id=card_id).first()
        if not card or card.is_sold:
            return {"success": False, "error": "Card not available"}
        
        user = session.query(User).filter_by(telegram_id="123456789").first()
        if not user or user.balance < card.price:
            return {"success": False, "error": "Insufficient balance"}
        
        order = Order(user_id=user.id, amount=card.price, status="completed", details=f"Card ID: {card_id}")
        session.add(order)
        
        card.is_sold = True
        card.order_id = order.id
        user.balance -= card.price
        session.commit()
        
        return {"success": True, "order_id": order.id}
    finally:
        session.close()

@app.get("/api/order/{order_id}/download")
async def download_order(order_id: int):
    """Download order as .txt file"""
    session = SessionLocal()
    try:
        order = session.query(Order).filter_by(id=order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        cards = session.query(Card).filter_by(order_id=order_id).all()
        if not cards:
            raise HTTPException(status_code=404, detail="No cards found for this order")
        
        txt_content = (
            f"{'='*50}\n"
            f"🏮 CHINATOWN MARKET\n"
            f"{'='*50}\n\n"
            f"Order: #{order.id}\n"
            f"Date: {order.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Total: ${order.amount:.2f}\n"
            f"Cards: {len(cards)}\n\n"
        )
        
        for card in cards:
            txt_content += f"{card.number}|{card.expiry}|{card.cvv}\n"
        
        txt_content += f"\n{'='*50}\n✅ All cards verified!"
        
        return FileResponse(
            io.BytesIO(txt_content.encode('utf-8')),
            media_type="text/plain",
            filename=f"order_{order_id}_{datetime.now().strftime('%Y%m%d')}.txt"
        )
    finally:
        session.close()

# ============================================================================
# 👑 ADMIN API ROUTES
# ============================================================================

@app.get("/api/admin/stats")
async def admin_stats():
    """Get store statistics"""
    session = SessionLocal()
    try:
        return {
            "total_cards": session.query(Card).count(),
            "available": session.query(Card).filter(Card.is_sold == False).count(),
            "total_users": session.query(User).count(),
            "total_orders": session.query(Order).count(),
            "total_revenue": session.query(func.sum(Order.amount)).scalar() or 0,
            "pending_payments": session.query(Payment).filter(Payment.status == "pending").count()
        }
    finally:
        session.close()

@app.get("/api/admin/cards")
async def admin_get_cards(limit: int = 50):
    """Get all cards for admin"""
    session = SessionLocal()
    try:
        cards = session.query(Card).order_by(Card.created_at.desc()).limit(limit).all()
        return [{
            "id": card.id,
            "bin": card.bin,
            "number": card.number,
            "expiry": card.expiry,
            "country": card.country,
            "billing": card.billing,
            "checked": card.checked,
            "price": card.price,
            "is_sold": card.is_sold
        } for card in cards]
    finally:
        session.close()

@app.post("/api/admin/upload")
async def admin_upload(file: bytes = None, raw_data: str = None, naked_price: float = 0.33, clothed_price: float = 25.00):
    """Upload cards from file or raw text"""
    session = SessionLocal()
    try:
        global DEFAULT_NAKED_PRICE, DEFAULT_CLOTHED_PRICE
        DEFAULT_NAKED_PRICE = naked_price
        DEFAULT_CLOTHED_PRICE = clothed_price
        
        cards_to_add = []
        success = 0
        failed = 0
        
        if file:
            file_path = f"uploads/temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(file_path, 'wb') as f:
                f.write(file)
            
            cards, s, f = SmartCardParser.parse_file(file_path)
            os.remove(file_path)
            cards_to_add.extend(cards)
            success += s
            failed += f
        
        if raw_data:
            cards, s, f = SmartCardParser.parse_raw_text(raw_data)
            cards_to_add.extend(cards)
            success += s
            failed += f
        
        for card_data in cards_to_add:
            card = Card(
                bin=card_data['bin'],
                number=card_data['number'],
                expiry=card_data['expiry'],
                cvv=card_data['cvv'],
                country=card_data['country'],
                billing=card_data['billing'],
                cardholder=card_data.get('cardholder'),
                billing_address=card_data.get('billing_address'),
                price=card_data['price'],
                is_sold=False,
                checked=False
            )
            session.add(card)
        session.commit()
        
        return {"success": True, "message": f"Uploaded {success} cards, {failed} failed"}
    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e)}
    finally:
        session.close()

@app.get("/api/admin/payments")
async def admin_get_payments():
    """Get pending payments"""
    session = SessionLocal()
    try:
        payments = session.query(Payment).order_by(Payment.created_at.desc()).limit(50).all()
        return [{
            "id": p.id,
            "telegram_id": p.user.telegram_id,
            "amount": p.amount,
            "crypto_type": p.crypto_type,
            "tx_hash": p.tx_hash,
            "status": p.status,
            "created_at": p.created_at.isoformat()
        } for p in payments]
    finally:
        session.close()

@app.post("/api/admin/payment/{payment_id}/approve")
async def approve_payment(payment_id: int):
    """Approve a payment"""
    session = SessionLocal()
    try:
        payment = session.query(Payment).filter_by(id=payment_id).first()
        if not payment:
            return {"success": False, "error": "Payment not found"}
        
        payment.status = "confirmed"
        payment.confirmed_at = datetime.utcnow()
        
        user = session.query(User).filter_by(id=payment.user_id).first()
        if user:
            user.balance += payment.amount
        
        session.commit()
        return {"success": True, "message": f"Payment approved, ${payment.amount} added to user balance"}
    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e)}
    finally:
        session.close()

@app.post("/api/admin/payment/{payment_id}/reject")
async def reject_payment(payment_id: int):
    """Reject a payment"""
    session = SessionLocal()
    try:
        payment = session.query(Payment).filter_by(id=payment_id).first()
        if not payment:
            return {"success": False, "error": "Payment not found"}
        
        payment.status = "rejected"
        session.commit()
        return {"success": True, "message": "Payment rejected"}
    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e)}
    finally:
        session.close()

@app.post("/api/admin/bin_price")
async def update_bin_price(bin: str, price: float):
    """Update price for specific BIN"""
    session = SessionLocal()
    try:
        count = session.query(Card).filter(Card.bin == bin).count()
        if count == 0:
            return {"success": False, "error": "No cards found with this BIN"}
        
        session.query(Card).filter(Card.bin == bin).update({"price": price})
        session.commit()
        return {"success": True, "message": f"Updated {count} cards for BIN {bin}"}
    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e)}
    finally:
        session.close()

@app.post("/api/admin/prices")
async def update_default_prices(naked_price: float, clothed_price: float):
    """Update default prices"""
    global DEFAULT_NAKED_PRICE, DEFAULT_CLOTHED_PRICE
    DEFAULT_NAKED_PRICE = naked_price
    DEFAULT_CLOTHED_PRICE = clothed_price
    
    session = SessionLocal()
    try:
        session.query(Card).filter(Card.billing == False, Card.is_sold == False).update({"price": naked_price})
        session.query(Card).filter(Card.billing == True, Card.is_sold == False).update({"price": clothed_price})
        session.commit()
        return {"success": True, "message": f"Prices updated - Naked: ${naked_price}, Clothed: ${clothed_price}"}
    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e)}
    finally:
        session.close()

@app.delete("/api/admin/clear-sold")
async def admin_clear_sold():
    """Clear all sold cards"""
    session = SessionLocal()
    try:
        count = session.query(Card).filter(Card.is_sold == True).delete()
        session.commit()
        return {"success": True, "message": f"Deleted {count} sold cards"}
    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e)}
    finally:
        session.close()

@app.get("/api/admin/export")
async def admin_export():
    """Export all cards"""
    session = SessionLocal()
    try:
        cards = session.query(Card).all()
        content = f"🏮 CHINATOWN MARKET - CARD EXPORT\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n📊 Total: {len(cards)}\n\n"
        for card in cards:
            content += f"{card.number}|{card.expiry}|{card.cvv}|{card.country}|{'Clothed' if card.billing else 'Naked'}|{'Checked' if card.checked else 'Unchecked'}\n"
        
        return FileResponse(
            io.BytesIO(content.encode('utf-8')),
            media_type="text/plain",
            filename=f"cards_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
    finally:
        session.close()

@app.get("/api/admin/export-revenue")
async def admin_export_revenue():
    """Export revenue report"""
    session = SessionLocal()
    try:
        orders = session.query(Order).all()
        
        total_revenue = sum(o.amount for o in orders)
        total_orders = len(orders)
        avg_order = total_revenue / total_orders if total_orders > 0 else 0
        
        content = (
            f"🏮 CHINATOWN MARKET - REVENUE REPORT\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"{'━'*50}\n"
            f"💰 TOTAL REVENUE: ${total_revenue:.2f}\n"
            f"📦 TOTAL ORDERS: {total_orders}\n"
            f"💵 AVG ORDER: ${avg_order:.2f}\n"
            f"{'━'*50}\n\n"
            f"📊 RECENT ORDERS:\n"
            f"{'━'*50}\n"
        )
        
        for order in orders[:50]:
            content += f"Order #{order.id} | ${order.amount:.2f} | {order.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        
        return FileResponse(
            io.BytesIO(content.encode('utf-8')),
            media_type="text/plain",
            filename=f"revenue_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
    finally:
        session.close()

@app.get("/api/admin/users")
async def admin_get_users():
    """Get all users"""
    session = SessionLocal()
    try:
        users = session.query(User).order_by(User.created_at.desc()).limit(50).all()
        return [{
            "id": u.id,
            "telegram_id": u.telegram_id,
            "username": u.username,
            "balance": u.balance,
            "is_admin": u.is_admin,
            "order_count": session.query(Order).filter(Order.user_id == u.id).count()
        } for u in users]
    finally:
        session.close()

# ============================================================================
# 🤖 TELEGRAM BOT HANDLERS
# ============================================================================

def create_main_menu():
    """Create main menu with WebApp button"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="🏮 Open WebApp", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text="💰 Balance", callback_data="menu_balance")],
        [InlineKeyboardButton(text="📦 Shop Cards", callback_data="menu_catalog")],
        [InlineKeyboardButton(text="✅ Checked Cards", callback_data="menu_checked")],
        [InlineKeyboardButton(text="❌ Unchecked Cards", callback_data="menu_unchecked")],
        [InlineKeyboardButton(text="🔍 BIN Search", callback_data="menu_bin")],
        [InlineKeyboardButton(text="📜 History", callback_data="menu_history")],
        [InlineKeyboardButton(text="💸 Top Up", callback_data="menu_topup")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message"""
    await get_or_create_user(update.effective_user.id)
    welcome_text = """
✨ **WELCOME TO CHINATOWN MARKET!** ✨

🏮 *Premium Card Marketplace*
💰 *USDT | BTC | LTC Payments*
🌍 *Global Card Selection*

👇 *Tap a button below to get started:*
"""
    await update.message.reply_text(welcome_text, reply_markup=create_main_menu(), parse_mode="Markdown")

async def get_or_create_user(telegram_id: int):
    """Get or create user in database"""
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=str(telegram_id)).first()
        if not user:
            user = User(
                telegram_id=str(telegram_id),
                username="",
                usdt_address=USDT_ADDRESS,
                btc_address=BTC_ADDRESS,
                ltc_address=LTC_ADDRESS,
                is_admin=telegram_id in ADMIN_IDS,
                balance=0.00
            )
            session.add(user)
            session.commit()
        return user
    finally:
        session.close()

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show balance"""
    user = await get_or_create_user(update.effective_user.id)
    await update.message.reply_text(
        f"💰 **YOUR BALANCE**\n\n💵 Balance: `{user.balance:.2f} USDT`",
        parse_mode="Markdown",
        reply_markup=create_main_menu()
    )

async def topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show topup options"""
    keyboard = [
        [InlineKeyboardButton(text="💎 USDT (TRC20)", callback_data="crypto_usdt")],
                [InlineKeyboardButton(text="₿ Bitcoin", callback_data="crypto_btc")],
        [InlineKeyboardButton(text="🥌 Litecoin", callback_data="crypto_ltc")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="menu_home")],
    ]
    await update.message.reply_text(
        "💸 **SELECT PAYMENT METHOD**\n\n*Choose your preferred cryptocurrency:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def crypto_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show crypto address"""
    query = update.callback_query
    await query.answer()
    
    user = await get_or_create_user(update.effective_user.id)
    
    if query.data == "crypto_usdt":
        address = user.usdt_address
        symbol = "💎 USDT"
    elif query.data == "crypto_btc":
        address = user.btc_address
        symbol = "₿ Bitcoin"
    elif query.data == "crypto_ltc":
        address = user.ltc_address
        symbol = "🥌 Litecoin"
    else:
        return
    
    keyboard = [
        [InlineKeyboardButton(text="📋 Copy Address", callback_data=f"copy_{query.data.split('_')[1]}")],
        [InlineKeyboardButton(text="✅ Confirm Deposit", callback_data="confirm_deposit")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="menu_topup")],
    ]
    
    await query.edit_message_text(
        f"{symbol} **DEPOSIT ADDRESS**\n\n`{address}`\n\n"
        f"📡 *Send your {symbol.replace(' ', '').replace('💎', '').replace('₿', '').replace('🥌', '')} to this address*\n\n"
        f"💡 *Minimum: 0.01 USDT equivalent*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def copy_crypto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Copy crypto address"""
    query = update.callback_query
    await query.answer("✅ Address copied!", show_alert=True)

async def confirm_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm deposit"""
    query = update.callback_query
    await query.answer("✅ Deposit confirmed! Please send crypto to the address above.", show_alert=True)

async def catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show catalog"""
    keyboard = [
        [InlineKeyboardButton(text="🌐 Open WebApp", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text="🇺🇸 USA Cards", callback_data="cat_US")],
        [InlineKeyboardButton(text="🇨🇦 Canada", callback_data="cat_CA")],
        [InlineKeyboardButton(text="🇬🇧 UK", callback_data="cat_UK")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="menu_home")],
    ]
    await update.message.reply_text(
        "📦 **SHOP CARDS**\n\n*Select a category or open WebApp for full catalog:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def catalog_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle catalog selection"""
    query = update.callback_query
    await query.answer()
    
    country = query.data.split("_")[1]
    session = SessionLocal()
    try:
        cards = session.query(Card).filter(Card.country == country, Card.is_sold == False).limit(5).all()
        
        if not cards:
            await query.answer(f"📭 No {country} cards available.", show_alert=True)
            return
        
        text = f"📍 **{country} CARDS**\n\n"
        keyboard = []
        
        for idx, card in enumerate(cards, 1):
            text += (
                f"{idx}. BIN: `{card.bin}` ****{card.number[-4:]}\n"
                f"   📅 {card.expiry} | 🌍 {card.country}\n"
                f"   🏷️ {'👔 CLOTHED' if card.billing else '👕 NAKED'}\n"
                f"   💰 ${card.price:.2f} USDT\n\n"
            )
            keyboard.append([InlineKeyboardButton(text=f"🛒 Buy Card {idx}", callback_data=f"buy_{card.id}")])
        
        keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="menu_catalog")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    finally:
        session.close()

async def buy_card_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle card purchase"""
    query = update.callback_query
    await query.answer()
    
    card_id = int(query.data.split("_")[1])
    user = await get_or_create_user(update.effective_user.id)
    session = SessionLocal()
    try:
        card = session.query(Card).filter_by(id=card_id).first()
        if not card or card.is_sold:
            await query.answer("❌ Card no longer available!", show_alert=True)
            return
        
        if user.balance < card.price:
            await query.answer(
                f"❌ Insufficient Balance!\n\n"
                f"💰 Required: ${card.price:.2f}\n"
                f"💵 Your Balance: ${user.balance:.2f}",
                show_alert=True
            )
            return
        
        # Process order
        order = Order(user_id=user.id, amount=card.price, status="completed", details=f"Card ID: {card.id}")
        session.add(order)
        
        card.is_sold = True
        card.order_id = order.id
        user.balance -= card.price
        session.commit()
        
        # Create .txt file
        txt_content = (
            f"{'='*50}\n"
            f"🏮 CHINATOWN MARKET\n"
            f"{'='*50}\n\n"
            f"Order: #{order.id}\n"
            f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"User: {user.telegram_id}\n"
            f"Amount: ${card.price:.2f}\n\n"
            f"{'━'*50}\n"
            f"💳 CARD DETAILS\n"
            f"{'━'*50}\n"
            f"Number: {card.number}\n"
            f"Expiry: {card.expiry}\n"
            f"CVV: {card.cvv}\n"
            f"BIN: {card.bin}\n"
            f"Country: {card.country}\n"
            f"Type: {'CLOTHED' if card.billing else 'NAKED'}\n"
            f"Status: {'Checked' if card.checked else 'Unchecked'}\n"
        )
        
        if card.cardholder:
            txt_content += f"\nCardholder: {card.cardholder}"
        if card.billing_address:
            txt_content += f"\nBilling: {card.billing_address}"
        
        txt_content += f"""
{'━'*50}
💵 New Balance: ${user.balance:.2f}
{'━'*50}

✅ Card delivered instantly!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Chinatown Market
"""
        
        file_bytes = io.BytesIO(txt_content.encode('utf-8'))
        file_bytes.name = f"card_{order.id}_{card.bin}.txt"
        
        await query.message.reply_document(
            document=file_bytes,
            caption=f"""✅ **PURCHASE COMPLETE!**

🎴 Order #{order.id}
💰 ${card.price:.2f}

📄 Card details in file above.
💵 New Balance: ${user.balance:.2f}
""",
            parse_mode="Markdown"
        )
        
        await query.edit_message_text(
            "✅ **CARD PURCHASED!**\n\n📄 Check your card file above.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text="🔙 Back", callback_data="menu_home")]])
        )
    finally:
        session.close()

async def bin_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """BIN search"""
    await update.message.reply_text(
        "🔍 **BIN SEARCH**\n\n*Enter 6-digit BIN (e.g., /bin 414720):*",
        parse_mode="Markdown"
    )
    context.user_data['waiting_for_bin'] = True

async def handle_bin_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle BIN search"""
    if not context.user_data.get('waiting_for_bin'):
        return
    
    parts = update.message.text.split(' ')
    if len(parts) < 2:
        return
    
    bin_num = parts[1].strip()
    if len(bin_num) != 6 or not bin_num.isdigit():
        await update.message.reply_text("❌ BIN must be 6 digits.")
        return
    
    session = SessionLocal()
    try:
        clothed = session.query(Card).filter(Card.bin == bin_num, Card.billing == True, Card.is_sold == False).count()
        naked = session.query(Card).filter(Card.bin == bin_num, Card.billing == False, Card.is_sold == False).count()
        
        clothed_card = session.query(Card).filter(Card.bin == bin_num, Card.billing == True).first()
        clothed_price = clothed_card.price if clothed_card else DEFAULT_CLOTHED_PRICE
        naked_card = session.query(Card).filter(Card.bin == bin_num, Card.billing == False).first()
        naked_price = naked_card.price if naked_card else DEFAULT_NAKED_PRICE
        
        text = f"🔍 **BIN: {bin_num}**\n\n"
        text += f"👔 Clothed: {clothed} @ ${clothed_price:.2f}\n"
        text += f"👕 Naked: {naked} @ ${naked_price:.2f}\n\n"
        
        if clothed + naked == 0:
            text += "📭 No cards available"
        
        keyboard = []
        if clothed > 0:
            keyboard.append([InlineKeyboardButton(text=f"🛒 Order {clothed} Clothed", callback_data=f"order_bin_cloth_{bin_num}")])
        if naked > 0:
            keyboard.append([InlineKeyboardButton(text=f"🛒 Order {naked} Naked", callback_data=f"order_bin_naked_{bin_num}")])
        keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="menu_home")])
        
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        context.user_data['waiting_for_bin'] = False
    finally:
        session.close()

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show history"""
    user = await get_or_create_user(update.effective_user.id)
    session = SessionLocal()
    try:
        orders = session.query(Order).filter(Order.user_id == user.id).order_by(Order.created_at.desc()).limit(10).all()
        
        if not orders:
            await update.message.reply_text("📭 No purchase history yet.", reply_markup=create_main_menu())
            return
        
        text = "📜 **PURCHASE HISTORY**\n\n"
        for order in orders:
            text += f"🆔 #{order.id} | ${order.amount:.2f} | {order.created_at.strftime('%Y-%m-%d')}\n"
        
        await update.message.reply_text(text, reply_markup=create_main_menu(), parse_mode="Markdown")
    finally:
        session.close()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command"""
    await update.message.reply_text(
        "❓ **HELP**\n\n"
        "/start - Welcome\n"
        "/balance - Check balance\n"
        "/topup - Add funds\n"
        "/catalog - Browse cards\n"
        "/checked - Browse checked cards\n"
        "/unchecked - Browse unchecked cards\n"
        "/bin - BIN search\n"
        "/history - Order history\n"
        "/help - This message\n\n"
        "*Admin Commands:*\n"
        "/stats - Store stats\n"
        "/upload - Upload cards\n"
        "/export - Export cards\n"
        "/prices - Admin price management\n"
        "/clearcards - Delete ALL cards\n"
        "/clearsold - Delete sold cards",
        parse_mode="Markdown",
        reply_markup=create_main_menu()
    )

# ── ADMIN COMMANDS ──

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin stats"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin only!")
        return
    
    session = SessionLocal()
    try:
        total_cards = session.query(Card).count()
        sold = session.query(Card).filter(Card.is_sold == True).count()
        revenue = session.query(func.sum(Order.amount)).scalar() or 0
        
        text = (
            f"📊 **STORE STATS**\n\n"
            f"{'━'*40}\n"
            f"🎴 Total Cards: {total_cards}\n"
            f"✅ Sold: {sold}\n"
            f"📉 Available: {total_cards - sold}\n"
            f"💰 Revenue: ${revenue:.2f}\n"
            f"{'━'*40}"
        )
        
        await update.message.reply_text(text, parse_mode="Markdown")
    finally:
        session.close()


async def admin_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin upload - asks checked or unchecked"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin only!")
        return
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Checked Cards", callback_data="upload_checked"),
            InlineKeyboardButton("❌ Unchecked Cards", callback_data="upload_unchecked"),
        ],
    ])
    
    await update.message.reply_text(
        "📦 **UPLOAD CARDS**\n\n"
        "Select card type before uploading:\n\n"
        "✅ **Checked** — Verified cards\n"
        "❌ **Unchecked** — Unverified cards\n\n"
        "After selecting, send a file (.txt, .csv) or paste raw data.\n"
        "Format: `cc|mm|yy|cvv|name|address`",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


async def upload_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle checked/unchecked selection"""
    query = update.callback_query
    await query.answer()
    
    card_status = query.data.split("_")[1]
    context.user_data["uploading"] = True
    context.user_data["upload_type"] = card_status
    
    label = "✅ Checked" if card_status == "checked" else "❌ Unchecked"
    
    await query.edit_message_text(
        f"📦 **UPLOAD — {label}**\n\n"
        f"Now send a file (.txt, .csv) or paste raw card data.\n\n"
        f"Format: `cc|mm|yy|cvv|name|address`\n\n"
        f"⚠️ All cards from this upload will be marked as **{label}**",
        parse_mode="Markdown"
    )


async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle file upload"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin or not context.user_data.get("uploading"):
        return
    
    document = update.message.document
    if not document.file_name.endswith((".txt", ".csv", ".dat")):
        return
    
    card_status = context.user_data.get("upload_type", "unchecked")
    is_checked = card_status == "checked"
    
    await update.message.reply_text(f"⏳ Processing {'✅ checked' if is_checked else '❌ unchecked'} cards...")
    
    try:
        file_path = f"uploads/{document.file_name}"
        file = await context.bot.get_file(document.file_id)
        await file.download_to_drive(file_path)
        
        cards, success, failed = SmartCardParser.parse_file(file_path)
        
        session = SessionLocal()
        try:
            for card_data in cards:
                card = Card(
                    bin=card_data["bin"],
                    number=card_data["number"],
                    expiry=card_data["expiry"],
                    cvv=card_data["cvv"],
                    country=card_data["country"],
                    billing=card_data["billing"],
                    cardholder=card_data.get("cardholder"),
                    billing_address=card_data.get("billing_address"),
                    price=card_data["price"],
                    is_sold=False,
                    checked=is_checked,
                )
                session.add(card)
            session.commit()
            
            await update.message.reply_text(
                f"✅ **UPLOADED {'✅ CHECKED' if is_checked else '❌ UNCHECKED'}!**\n\n"
                f"📊 Success: {success}\n"
                f"❌ Failed: {failed}",
                parse_mode="Markdown"
            )
        finally:
            session.close()
            os.remove(file_path)
            context.user_data["uploading"] = False
            context.user_data["upload_type"] = None
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        context.user_data["uploading"] = False
        context.user_data["upload_type"] = None


async def handle_raw_text_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle raw text paste for uploads"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin or not context.user_data.get("uploading"):
        return
    
    if update.message.text.startswith("/"):
        return
    
    card_status = context.user_data.get("upload_type", "unchecked")
    is_checked = card_status == "checked"
    raw_data = update.message.text
    
    await update.message.reply_text(f"⏳ Processing {'✅ checked' if is_checked else '❌ unchecked'} cards...")
    
    try:
        cards, success, failed = SmartCardParser.parse_raw_text(raw_data)
        
        session = SessionLocal()
        try:
            for card_data in cards:
                card = Card(
                    bin=card_data["bin"],
                    number=card_data["number"],
                    expiry=card_data["expiry"],
                    cvv=card_data["cvv"],
                    country=card_data["country"],
                    billing=card_data["billing"],
                    cardholder=card_data.get("cardholder"),
                    billing_address=card_data.get("billing_address"),
                    price=card_data["price"],
                    is_sold=False,
                    checked=is_checked
                )
                session.add(card)
            session.commit()
            
            await update.message.reply_text(
                f"✅ **UPLOADED {'✅ CHECKED' if is_checked else '❌ UNCHECKED'}!**\n\n"
                f"📊 Success: {success}\n"
                f"❌ Failed: {failed}",
                parse_mode="Markdown"
            )
        finally:
            session.close()
            context.user_data["uploading"] = False
            context.user_data["upload_type"] = None
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        context.user_data["uploading"] = False
        context.user_data["upload_type"] = None


async def admin_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin export"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin only!")
        return
    
    session = SessionLocal()
    try:
        cards = session.query(Card).all()
        content = f"🏮 CHINATOWN MARKET EXPORT\n📅 {datetime.now().strftime('%Y-%m-%d')}\n📊 {len(cards)} cards\n\n"
        for card in cards:
            content += f"{card.number}|{card.expiry}|{card.cvv}|{'C' if card.checked else 'U'}\n"
        
        file_bytes = io.BytesIO(content.encode('utf-8'))
        file_bytes.name = f"export_{datetime.now().strftime('%Y%m%d')}.txt"
        
        await update.message.reply_document(document=file_bytes)
    finally:
        session.close()


async def admin_clear_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete ALL cards (sold and unsold)"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin only!")
        return
    
    session = SessionLocal()
    try:
        count = session.query(Card).delete()
        session.commit()
        await update.message.reply_text(f"🗑️ Deleted ALL {count} cards from database.")
    except Exception as e:
        session.rollback()
        await update.message.reply_text(f"❌ Error: {e}")
    finally:
        session.close()


async def admin_clear_sold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete only sold cards"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin only!")
        return
    
    session = SessionLocal()
    try:
        count = session.query(Card).filter(Card.is_sold == True).delete()
        session.commit()
        await update.message.reply_text(f"🗑️ Deleted {count} sold cards.")
    except Exception as e:
        session.rollback()
        await update.message.reply_text(f"❌ Error: {e}")
    finally:
        session.close()


async def admin_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin price management menu"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin only!")
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Set Default Prices", callback_data="price_default")],
        [InlineKeyboardButton("🎯 Set BIN Price", callback_data="price_bin")],
        [InlineKeyboardButton("📊 View Current Prices", callback_data="price_view")],
        [InlineKeyboardButton("🔙 Back", callback_data="menu_home")],
    ])
    
    await update.message.reply_text(
        "💰 **PRICE MANAGEMENT**\n\n*Select an option:*",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


async def price_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle price menu callbacks"""
    query = update.callback_query
    await query.answer()
    
    action = query.data.split("_")[1]
    
    if action == "default":
        context.user_data["price_mode"] = "default"
        await query.edit_message_text(
            "💰 **SET DEFAULT PRICES**\n\n"
            "Send prices in this format:\n\n"
            "`naked clothed`\n\n"
            "Example: `0.33 25.00`\n\n"
            "This updates ALL unsold cards.",
            parse_mode="Markdown"
        )
    
    elif action == "bin":
        context.user_data["price_mode"] = "bin"
        await query.edit_message_text(
            "🎯 **SET BIN PRICE**\n\n"
            "Send in this format:\n\n"
            "`BIN price`\n\n"
            "Example: `514377 15.00`\n\n"
            "This updates ALL unsold cards with that BIN.",
            parse_mode="Markdown"
        )
    
    elif action == "view":
        session = SessionLocal()
        try:
            from sqlalchemy import distinct, func
            
            bins = session.query(
                Card.bin,
                func.count(Card.id).label('count'),
                Card.billing,
                Card.price
            ).filter(
                Card.is_sold == False
            ).group_by(
                Card.bin, Card.billing, Card.price
            ).all()
            
            if not bins:
                await query.edit_message_text("📭 No cards in stock.")
                return
            
            text = "📊 **CURRENT PRICES**\n\n"
            
            naked_bins = [b for b in bins if b.billing == False]
            clothed_bins = [b for b in bins if b.billing == True]
            
            if naked_bins:
                text += "👕 **NAKED CARDS:**\n"
                for b in naked_bins[:20]:
                    text += f"  BIN `{b.bin}` — {b.count} cards @ ${b.price:.2f}\n"
                text += "\n"
            
            if clothed_bins:
                text += "👔 **CLOTHED CARDS:**\n"
                for b in clothed_bins[:20]:
                    text += f"  BIN `{b.bin}` — {b.count} cards @ ${b.price:.2f}\n"
            
            await query.edit_message_text(text, parse_mode="Markdown")
        finally:
            session.close()


async def handle_price_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle price input from admin"""
    if not context.user_data.get("price_mode"):
        return
    
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        return
    
    text = update.message.text.strip()
    mode = context.user_data["price_mode"]
    
    session = SessionLocal()
    try:
        if mode == "default":
            parts = text.split()
            if len(parts) != 2:
                await update.message.reply_text("❌ Format: `naked clothed`\nExample: `0.33 25.00`", parse_mode="Markdown")
                return
            
            try:
                naked_price = float(parts[0])
                clothed_price = float(parts[1])
            except ValueError:
                await update.message.reply_text("❌ Invalid prices. Use numbers only.")
                return
            
            session.query(Card).filter(Card.billing == False, Card.is_sold == False).update({"price": naked_price})
            session.query(Card).filter(Card.billing == True, Card.is_sold == False).update({"price": clothed_price})
            session.commit()
            
            await update.message.reply_text(
                f"✅ **PRICES UPDATED**\n\n👕 Naked: ${naked_price:.2f}\n👔 Clothed: ${clothed_price:.2f}\n\nAll unsold cards updated.",
                parse_mode="Markdown"
            )
        
        elif mode == "bin":
            parts = text.split()
            if len(parts) != 2:
                await update.message.reply_text("❌ Format: `BIN price`\nExample: `514377 15.00`", parse_mode="Markdown")
                return
            
            bin_num = parts[0]
            try:
                price = float(parts[1])
            except ValueError:
                await update.message.reply_text("❌ Invalid price.")
                return
            
            count = session.query(Card).filter(Card.bin == bin_num, Card.is_sold == False).count()
            
            if count == 0:
                await update.message.reply_text(f"❌ No unsold cards found for BIN `{bin_num}`", parse_mode="Markdown")
                return
            
            session.query(Card).filter(Card.bin == bin_num, Card.is_sold == False).update({"price": price})
            session.commit()
            
            await update.message.reply_text(
                f"✅ **BIN PRICE UPDATED**\n\nBIN: `{bin_num}`\nPrice: ${price:.2f}\nCards updated: {count}",
                parse_mode="Markdown"
            )
        
        context.user_data["price_mode"] = None
    
    except Exception as e:
        session.rollback()
        await update.message.reply_text(f"❌ Error: {e}")
    finally:
        session.close()


async def download_order_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download order"""
    parts = update.message.text.split(' ')
    if len(parts) < 2:
        await update.message.reply_text("Usage: /download ORDER_ID")
        return
    
    session = SessionLocal()
    try:
        order = session.query(Order).filter_by(id=parts[1].strip()).first()
        if not order:
            await update.message.reply_text("❌ Order not found!")
            return
        
        cards = session.query(Card).filter_by(order_id=order.id).all()
        content = f"Order #{order.id}\nDate: {order.created_at.strftime('%Y-%m-%d')}\n\n"
        for card in cards:
            content += f"{card.number}|{card.expiry}|{card.cvv}\n"
        
        file_bytes = io.BytesIO(content.encode('utf-8'))
        file_bytes.name = f"order_{order.id}.txt"
        
        await update.message.reply_document(document=file_bytes)
    finally:
        session.close()


# ── BIN ORDER FLOW ──

async def order_bin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle BIN order with quantity selector"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_")
    order_type = parts[2]
    bin_number = parts[3]
    
    context.user_data["selected_bin"] = bin_number
    context.user_data["order_type"] = order_type
    
    session = SessionLocal()
    try:
        if order_type == "cloth":
            available = session.query(Card).filter(
                Card.bin == bin_number, Card.billing == True, Card.is_sold == False
            ).count()
            card_type = "👔 CLOTHED"
            card_price = DEFAULT_CLOTHED_PRICE
        else:
            available = session.query(Card).filter(
                Card.bin == bin_number, Card.billing == False, Card.is_sold == False
            ).count()
            card_type = "👕 NAKED"
            card_price = DEFAULT_NAKED_PRICE
        
        order_text = (
            f"🛒 **ORDER {card_type} CARDS**\n"
            f"🎯 **BIN:** `{bin_number}`\n\n"
            f"📦 **Available:** {available} cards\n"
            f"💰 **Price:** ${card_price:.2f} USDT each\n\n"
            f"🎯 *Select quantity:*\n"
        )
        
        keyboard = [
            [
                InlineKeyboardButton(text="1", callback_data=f"qty_1_{bin_number}_{order_type}"),
                InlineKeyboardButton(text="5", callback_data=f"qty_5_{bin_number}_{order_type}"),
                InlineKeyboardButton(text="10", callback_data=f"qty_10_{bin_number}_{order_type}"),
            ],
            [
                InlineKeyboardButton(text="25", callback_data=f"qty_25_{bin_number}_{order_type}"),
                InlineKeyboardButton(text="50", callback_data=f"qty_50_{bin_number}_{order_type}"),
                InlineKeyboardButton(text="🔢 Custom", callback_data=f"qty_custom_{bin_number}_{order_type}"),
            ],
            [InlineKeyboardButton(text="🔙 Back", callback_data=f"order_bin_{order_type}_{bin_number}")],
        ]
        
        await query.edit_message_text(order_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    finally:
        session.close()


async def handle_quantity_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quantity selection"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_")
    quantity = int(parts[1])
    bin_number = parts[2]
    order_type = parts[3]
    
    context.user_data["selected_quantity"] = quantity
    
    session = SessionLocal()
    try:
        if order_type == "cloth":
            available = session.query(Card).filter(
                Card.bin == bin_number, Card.billing == True, Card.is_sold == False
            ).count()
            card_price = DEFAULT_CLOTHED_PRICE
        else:
            available = session.query(Card).filter(
                Card.bin == bin_number, Card.billing == False, Card.is_sold == False
            ).count()
            card_price = DEFAULT_NAKED_PRICE
        
        total_cost = quantity * card_price
        user = await get_or_create_user(update.effective_user.id)
        
        if quantity > available:
            await query.answer(f"❌ Only {available} cards available!", show_alert=True)
            return
        
        if user.balance < total_cost:
            await query.answer(
                f"❌ Insufficient Balance!\n\n💰 Required: ${total_cost:.2f}\n💵 Your Balance: ${user.balance:.2f}",
                show_alert=True
            )
            return
        
        await query.edit_message_text(
            f"""🛒 **ORDER SUMMARY**

🎯 **BIN:** `{bin_number}`
📦 **Quantity:** {quantity} cards
🏷️ **Type:** {'👔 CLOTHED' if order_type == 'cloth' else '👕 NAKED'}
💰 **Total:** ${total_cost:.2f} USDT
💵 **Your Balance:** ${user.balance:.2f} USDT

*Confirm order?*""",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="✅ YES, Complete Order", callback_data=f"confirm_order_{bin_number}_{order_type}_{quantity}")],
                [InlineKeyboardButton(text="❌ Cancel", callback_data=f"order_bin_{order_type}_{bin_number}")],
            ]),
        )
    finally:
        session.close()


async def confirm_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle confirmed BIN order"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_")
    bin_number = parts[2]
    order_type = parts[3]
    quantity = int(parts[4])
    
    user = await get_or_create_user(update.effective_user.id)
    session = SessionLocal()
    try:
        if order_type == "cloth":
            cards_to_sell = session.query(Card).filter(
                Card.bin == bin_number, Card.billing == True, Card.is_sold == False
            ).limit(quantity).all()
            card_type = "👔 CLOTHED"
            card_price = DEFAULT_CLOTHED_PRICE
        else:
            cards_to_sell = session.query(Card).filter(
                Card.bin == bin_number, Card.billing == False, Card.is_sold == False
            ).limit(quantity).all()
            card_type = "👕 NAKED"
            card_price = DEFAULT_NAKED_PRICE
        
        if len(cards_to_sell) < quantity:
            await query.answer(f"❌ Only {len(cards_to_sell)} cards available!", show_alert=True)
            return
        
        total_cost = len(cards_to_sell) * card_price
        
        order = Order(
            user_id=user.id,
            amount=total_cost,
            status="completed",
            details=f"BIN {bin_number} - {quantity} {card_type}"
        )
        session.add(order)
        
        for card in cards_to_sell:
            card.is_sold = True
            card.order_id = order.id
        
        user.balance -= total_cost
        session.commit()
        
        txt_content = (
            f"{'=' * 50}\n"
            f"🎴 CARD DELIVERY - Chinatown Market\n"
            f"{'=' * 50}\n\n"
                        f"🆔 Order ID: #{order.id}\n"
            f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"👤 User: {user.telegram_id}\n"
            f"🎴 BIN: {bin_number}\n"
            f"📦 Total Cards: {len(cards_to_sell)}\n"
            f"💰 Total Cost: ${total_cost:.2f} USDT\n\n"
            f"{'━' * 50}\n"
            f"💳 {card_type} CARDS ({len(cards_to_sell)})\n"
            f"{'━' * 50}\n"
        )
        
        for card in cards_to_sell:
            txt_content += f"{card.number}|{card.expiry}|{card.cvv}\n"
        
        txt_content += f"\n{'━' * 50}\n💵 New Balance: ${user.balance:.2f} USDT\n{'━' * 50}\n\n✅ All cards delivered!\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nChinatown Market\n"
        
        file_bytes = io.BytesIO(txt_content.encode("utf-8"))
        file_bytes.name = f"order_{order.id}_BIN_{bin_number}.txt"
        
        await query.message.reply_document(
            document=file_bytes,
            caption=f"✅ **ORDER #{order.id} COMPLETE!**\n\n🎴 BIN: `{bin_number}`\n📦 {len(cards_to_sell)} {card_type} cards\n💰 Total: ${total_cost:.2f} USDT\n💵 New Balance: ${user.balance:.2f} USDT\n\n📄 Card details in file above!",
            parse_mode="Markdown",
        )
        
        await query.edit_message_text(
            f"✅ **ORDER COMPLETE!**\n\n📦 {len(cards_to_sell)} {card_type} cards delivered\n💰 Total: ${total_cost:.2f} USDT\n💵 New Balance: ${user.balance:.2f} USDT",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="🏠 Back to Home", callback_data="menu_home")],
            ]),
        )
    finally:
        session.close()


# ── CHECKED/UNCHECKED BROWSING FLOW ──

async def checked_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_cards_by_status(update, context, checked=True)


async def unchecked_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_cards_by_status(update, context, checked=False)


async def show_cards_by_status(update: Update, context: ContextTypes.DEFAULT_TYPE, checked: bool):
    session = SessionLocal()
    try:
        bins = session.query(
            Card.bin,
            Card.billing,
            func.count(Card.id).label("count"),
            Card.price,
        ).filter(Card.is_sold == False, Card.checked == checked).group_by(Card.bin, Card.billing, Card.price).all()

        if not bins:
            label = "✅ Checked" if checked else "❌ Unchecked"
            await update.message.reply_text(f"📭 No {label} cards available.", reply_markup=create_main_menu())
            return

        label = "✅ CHECKED" if checked else "❌ UNCHECKED"
        total = sum(b.count for b in bins)

        text = f"📦 **{label} CARDS**\n📊 Total available: {total}\n\n"
        keyboard = []

        naked_bins = [b for b in bins if b.billing == False]
        clothed_bins = [b for b in bins if b.billing == True]

        if naked_bins:
            text += "👕 **NAKED:**\n"
            for b in naked_bins[:15]:
                text += f"  BIN `{b.bin}` — {b.count} @ ${b.price:.2f}\n"
                keyboard.append([InlineKeyboardButton(
                    text=f"👕 {b.bin} — {b.count} naked @ ${b.price:.2f}",
                    callback_data=f"statusbin_{b.bin}_naked_{'1' if checked else '0'}",
                )])
            text += "\n"

        if clothed_bins:
            text += "👔 **CLOTHED:**\n"
            for b in clothed_bins[:15]:
                text += f"  BIN `{b.bin}` — {b.count} @ ${b.price:.2f}\n"
                keyboard.append([InlineKeyboardButton(
                    text=f"👔 {b.bin} — {b.count} clothed @ ${b.price:.2f}",
                    callback_data=f"statusbin_{b.bin}_cloth_{'1' if checked else '0'}",
                )])

        keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="menu_home")])

        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    finally:
        session.close()


async def status_bin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    bin_number = parts[1]
    order_type = parts[2]
    checked = parts[3] == "1"

    session = SessionLocal()
    try:
        if order_type == "cloth":
            available = session.query(Card).filter(
                Card.bin == bin_number, Card.billing == True, Card.is_sold == False, Card.checked == checked
            ).count()
            card_type = "👔 CLOTHED"
            price_card = session.query(Card).filter(
                Card.bin == bin_number, Card.billing == True, Card.is_sold == False, Card.checked == checked
            ).first()
            card_price = price_card.price if price_card else DEFAULT_CLOTHED_PRICE
        else:
            available = session.query(Card).filter(
                Card.bin == bin_number, Card.billing == False, Card.is_sold == False, Card.checked == checked
            ).count()
            card_type = "👕 NAKED"
            price_card = session.query(Card).filter(
                Card.bin == bin_number, Card.billing == False, Card.is_sold == False, Card.checked == checked
            ).first()
            card_price = price_card.price if price_card else DEFAULT_NAKED_PRICE

        label = "✅ Checked" if checked else "❌ Unchecked"

        order_text = (
            f"🛒 **ORDER {card_type} — {label}**\n"
            f"🎯 **BIN:** `{bin_number}`\n\n"
            f"📦 **Available:** {available} cards\n"
            f"💰 **Price:** ${card_price:.2f} USDT each\n\n"
            f"🎯 *Select quantity:*\n"
        )

        keyboard = [
            [
                InlineKeyboardButton(text="1", callback_data=f"statusqty_1_{bin_number}_{order_type}_{parts[3]}"),
                InlineKeyboardButton(text="5", callback_data=f"statusqty_5_{bin_number}_{order_type}_{parts[3]}"),
                InlineKeyboardButton(text="10", callback_data=f"statusqty_10_{bin_number}_{order_type}_{parts[3]}"),
            ],
            [
                InlineKeyboardButton(text="25", callback_data=f"statusqty_25_{bin_number}_{order_type}_{parts[3]}"),
                InlineKeyboardButton(text="50", callback_data=f"statusqty_50_{bin_number}_{order_type}_{parts[3]}"),
                InlineKeyboardButton(text="🔢 Custom", callback_data=f"statusqty_custom_{bin_number}_{order_type}_{parts[3]}"),
            ],
            [InlineKeyboardButton(text="🔙 Back", callback_data=f"back_status_{'1' if checked else '0'}")],
        ]

        await query.edit_message_text(order_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    finally:
        session.close()


async def status_qty_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    quantity = int(parts[1])
    bin_number = parts[2]
    order_type = parts[3]
    checked = parts[4] == "1"

    session = SessionLocal()
    try:
        if order_type == "cloth":
            available = session.query(Card).filter(
                Card.bin == bin_number, Card.billing == True, Card.is_sold == False, Card.checked == checked
            ).count()
            price_card = session.query(Card).filter(
                Card.bin == bin_number, Card.billing == True, Card.is_sold == False, Card.checked == checked
            ).first()
            card_price = price_card.price if price_card else DEFAULT_CLOTHED_PRICE
        else:
            available = session.query(Card).filter(
                Card.bin == bin_number, Card.billing == False, Card.is_sold == False, Card.checked == checked
            ).count()
            price_card = session.query(Card).filter(
                Card.bin == bin_number, Card.billing == False, Card.is_sold == False, Card.checked == checked
            ).first()
            card_price = price_card.price if price_card else DEFAULT_NAKED_PRICE

        total_cost = quantity * card_price
        user = await get_or_create_user(update.effective_user.id)

        if quantity > available:
            await query.answer(f"❌ Only {available} cards available!", show_alert=True)
            return

        if user.balance < total_cost:
            await query.answer(
                f"❌ Insufficient Balance!\n\n💰 Required: ${total_cost:.2f}\n💵 Your Balance: ${user.balance:.2f}",
                show_alert=True,
            )
            return

        label = "✅ Checked" if checked else "❌ Unchecked"

        await query.edit_message_text(
            f"""🛒 **ORDER SUMMARY**

🎯 **BIN:** `{bin_number}`
📦 **Quantity:** {quantity} cards
🏷️ **Type:** {'👔 CLOTHED' if order_type == 'cloth' else '👕 NAKED'}
✅ **Status:** {label}
💰 **Total:** ${total_cost:.2f} USDT
💵 **Your Balance:** ${user.balance:.2f} USDT

*Confirm order?*""",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="✅ Confirm Order", callback_data=f"statusconfirm_{bin_number}_{order_type}_{quantity}_{parts[4]}")],
                [InlineKeyboardButton(text="❌ Cancel", callback_data=f"statusbin_{bin_number}_{order_type}_{parts[4]}")],
            ]),
        )
    finally:
        session.close()


async def status_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    bin_number = parts[1]
    order_type = parts[2]
    quantity = int(parts[3])
    checked = parts[4] == "1"

    user = await get_or_create_user(update.effective_user.id)
    session = SessionLocal()
    try:
        if order_type == "cloth":
            cards_to_sell = session.query(Card).filter(
                Card.bin == bin_number, Card.billing == True, Card.is_sold == False, Card.checked == checked
            ).limit(quantity).all()
            card_type = "👔 CLOTHED"
            price_card = cards_to_sell[0] if cards_to_sell else None
            card_price = price_card.price if price_card else DEFAULT_CLOTHED_PRICE
        else:
            cards_to_sell = session.query(Card).filter(
                Card.bin == bin_number, Card.billing == False, Card.is_sold == False, Card.checked == checked
            ).limit(quantity).all()
            card_type = "👕 NAKED"
            price_card = cards_to_sell[0] if cards_to_sell else None
            card_price = price_card.price if price_card else DEFAULT_NAKED_PRICE

        if len(cards_to_sell) < quantity:
            await query.answer(f"❌ Only {len(cards_to_sell)} available!", show_alert=True)
            return

        total_cost = len(cards_to_sell) * card_price
        label = "✅ Checked" if checked else "❌ Unchecked"

        order = Order(
            user_id=user.id,
            amount=total_cost,
            status="completed",
            details=f"BIN {bin_number} - {quantity} {card_type} - {label}",
        )
        session.add(order)

        for card in cards_to_sell:
            card.is_sold = True
            card.order_id = order.id

        user.balance -= total_cost
        session.commit()

        txt_content = (
            f"{'=' * 50}\n"
            f"🎴 CARD DELIVERY - Chinatown Market\n"
            f"{'=' * 50}\n\n"
            f"🆔 Order ID: #{order.id}\n"
            f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"👤 User: {user.telegram_id}\n"
            f"🎴 BIN: {bin_number}\n"
            f"📦 Total Cards: {len(cards_to_sell)}\n"
            f"💰 Total Cost: ${total_cost:.2f} USDT\n"
            f"✅ Status: {label}\n\n"
            f"{'━' * 50}\n"
            f"💳 {card_type} CARDS ({len(cards_to_sell)})\n"
            f"{'━' * 50}\n"
        )

        for card in cards_to_sell:
            txt_content += f"{card.number}|{card.expiry}|{card.cvv}\n"

        txt_content += f"\n{'━' * 50}\n💵 New Balance: ${user.balance:.2f} USDT\n{'━' * 50}\n\n✅ All cards delivered!\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nChinatown Market\n"

        file_bytes = io.BytesIO(txt_content.encode("utf-8"))
        file_bytes.name = f"order_{order.id}_BIN_{bin_number}.txt"

        await query.message.reply_document(
            document=file_bytes,
            caption=f"✅ **ORDER #{order.id} COMPLETE!**\n\n🎴 BIN: `{bin_number}`\n📦 {len(cards_to_sell)} {card_type} cards\n✅ Status: {label}\n💰 Total: ${total_cost:.2f} USDT\n💵 New Balance: ${user.balance:.2f} USDT\n\n📄 Card details in file above!",
            parse_mode="Markdown",
        )

        await query.edit_message_text(
            f"✅ **ORDER COMPLETE!**\n\n📦 {len(cards_to_sell)} {card_type} {label} cards delivered\n💰 Total: ${total_cost:.2f} USDT\n💵 New Balance: ${user.balance:.2f} USDT",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="🏠 Home", callback_data="menu_home")],
            ]),
        )
    finally:
        session.close()


async def back_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    checked = query.data.split("_")[2] == "1"

    session = SessionLocal()
    try:
        bins = session.query(
            Card.bin,
            Card.billing,
            func.count(Card.id).label("count"),
            Card.price,
        ).filter(Card.is_sold == False, Card.checked == checked).group_by(Card.bin, Card.billing, Card.price).all()

        if not bins:
            label = "✅ Checked" if checked else "❌ Unchecked"
            await query.edit_message_text(f"📭 No {label} cards available.")
            return

        label = "✅ CHECKED" if checked else "❌ UNCHECKED"
        total = sum(b.count for b in bins)

        text = f"📦 **{label} CARDS**\n📊 Total: {total}\n\n"
        keyboard = []

        naked_bins = [b for b in bins if b.billing == False]
        clothed_bins = [b for b in bins if b.billing == True]

        if naked_bins:
            text += "👕 **NAKED:**\n"
            for b in naked_bins[:15]:
                text += f"  BIN `{b.bin}` — {b.count} @ ${b.price:.2f}\n"
                keyboard.append([InlineKeyboardButton(
                    text=f"👕 {b.bin} — {b.count} naked @ ${b.price:.2f}",
                    callback_data=f"statusbin_{b.bin}_naked_{'1' if checked else '0'}",
                )])
            text += "\n"

        if clothed_bins:
            text += "👔 **CLOTHED:**\n"
            for b in clothed_bins[:15]:
                text += f"  BIN `{b.bin}` — {b.count} @ ${b.price:.2f}\n"
                keyboard.append([InlineKeyboardButton(
                    text=f"👔 {b.bin} — {b.count} clothed @ ${b.price:.2f}",
                    callback_data=f"statusbin_{b.bin}_cloth_{'1' if checked else '0'}",
                )])

        keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="menu_home")])

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    finally:
        session.close()


async def menu_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    checked = query.data == "menu_checked"

    session = SessionLocal()
    try:
        bins = session.query(
            Card.bin,
            Card.billing,
            func.count(Card.id).label("count"),
            Card.price,
        ).filter(Card.is_sold == False, Card.checked == checked).group_by(Card.bin, Card.billing, Card.price).all()

        if not bins:
            label = "✅ Checked" if checked else "❌ Unchecked"
            await query.edit_message_text(
                f"📭 No {label} cards available.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(text="🔙 Back", callback_data="menu_home")]
                ]),
            )
            return

        label = "✅ CHECKED" if checked else "❌ UNCHECKED"
        total = sum(b.count for b in bins)

        text = f"📦 **{label} CARDS**\n📊 Total: {total}\n\n"
        keyboard = []

        naked_bins = [b for b in bins if b.billing == False]
        clothed_bins = [b for b in bins if b.billing == True]

        if naked_bins:
            text += "👕 **NAKED:**\n"
            for b in naked_bins[:15]:
                text += f"  BIN `{b.bin}` — {b.count} @ ${b.price:.2f}\n"
                keyboard.append([InlineKeyboardButton(
                    text=f"👕 {b.bin} — {b.count} naked @ ${b.price:.2f}",
                    callback_data=f"statusbin_{b.bin}_naked_{'1' if checked else '0'}",
                )])
            text += "\n"

        if clothed_bins:
            text += "👔 **CLOTHED:**\n"
            for b in clothed_bins[:15]:
                text += f"  BIN `{b.bin}` — {b.count} @ ${b.price:.2f}\n"
                keyboard.append([InlineKeyboardButton(
                    text=f"👔 {b.bin} — {b.count} clothed @ ${b.price:.2f}",
                    callback_data=f"statusbin_{b.bin}_cloth_{'1' if checked else '0'}",
                )])

        keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="menu_home")])

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    finally:
        session.close()


async def country_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle country catalog selection (fallback)"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📦 **COUNTRY CATALOG**\n\n*Select a country:*")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Error handler"""
    logging.error(f"Error: {context.error}")
    
def run_bot_in_thread(application):
    """Run the bot in a background thread using the async API directly."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def run():
        await application.initialize()
        await application.start()
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    try:
        loop.run_until_complete(run())
        loop.run_forever()  # keeps the thread alive
    finally:
        loop.close()


# ============================================================================
# 🛠️ MAIN FUNCTION
# ============================================================================

def main():
    """Main entry point"""
    print("🏮 Starting Chinatown Market...")

    engine = create_engine(
        DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=3600
    )

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Database connected!")
    except Exception as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)

    Base.metadata.create_all(bind=engine)
    Path("uploads").mkdir(exist_ok=True)

    bot_app = ApplicationBuilder().token(BOT_TOKEN).build()

    # ── Commands ──
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("balance", balance))
    bot_app.add_handler(CommandHandler("topup", topup))
    bot_app.add_handler(CommandHandler("catalog", catalog))
    bot_app.add_handler(CommandHandler("checked", checked_cards))
    bot_app.add_handler(CommandHandler("unchecked", unchecked_cards))
    bot_app.add_handler(CommandHandler("bin", bin_lookup))
    bot_app.add_handler(CommandHandler("history", history))
    bot_app.add_handler(CommandHandler("help", help_command))
    bot_app.add_handler(CommandHandler("stats", admin_stats))
    bot_app.add_handler(CommandHandler("upload", admin_upload))
    bot_app.add_handler(CommandHandler("export", admin_export))
    bot_app.add_handler(CommandHandler("prices", admin_prices))
    bot_app.add_handler(CommandHandler("clearcards", admin_clear_cards))
    bot_app.add_handler(CommandHandler("clearsold", admin_clear_sold))
    bot_app.add_handler(CommandHandler("download", download_order_command))

    # ── Message Handlers ──
    bot_app.add_handler(MessageHandler(filters.Regex("^/bin "), handle_bin_search))
    
    # Raw text upload handler (must be before general text handlers)
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_raw_text_upload))
    
    # File upload handler
    bot_app.add_handler(MessageHandler(filters.Document.ALL, handle_file_upload))

    # Price input handler
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_price_input))

    # ── Callback Query Handlers ──
    bot_app.add_handler(CallbackQueryHandler(crypto_callback, pattern="^crypto_"))
    bot_app.add_handler(CallbackQueryHandler(copy_crypto, pattern="^copy_"))
    bot_app.add_handler(CallbackQueryHandler(confirm_deposit, pattern="^confirm_deposit$"))
    bot_app.add_handler(CallbackQueryHandler(catalog_callback, pattern="^cat_"))
    bot_app.add_handler(CallbackQueryHandler(buy_card_callback, pattern="^buy_"))
    bot_app.add_handler(CallbackQueryHandler(order_bin_callback, pattern="^order_bin_"))
    bot_app.add_handler(CallbackQueryHandler(handle_quantity_selection, pattern="^qty_"))
    bot_app.add_handler(CallbackQueryHandler(confirm_order_callback, pattern="^confirm_order_"))
    bot_app.add_handler(CallbackQueryHandler(price_callback, pattern="^price_"))
    bot_app.add_handler(CallbackQueryHandler(upload_type_callback, pattern="^upload_"))
    bot_app.add_handler(CallbackQueryHandler(menu_status_callback, pattern="^menu_checked$|^menu_unchecked$"))
    bot_app.add_handler(CallbackQueryHandler(status_bin_callback, pattern="^statusbin_"))
    bot_app.add_handler(CallbackQueryHandler(status_qty_callback, pattern="^statusqty_"))
    bot_app.add_handler(CallbackQueryHandler(status_confirm_callback, pattern="^statusconfirm_"))
    bot_app.add_handler(CallbackQueryHandler(back_status_callback, pattern="^back_status_"))

    bot_app.add_error_handler(error_handler)

    bot_thread = threading.Thread(
        target=run_bot_in_thread,
        args=(bot_app,),
        daemon=True
    )
    bot_thread.start()

    print("✅ Bot running!")
    print(f"🌐 WebApp: http://{APP_HOST}:{APP_PORT}")

    uvicorn.run(app, host=APP_HOST, port=APP_PORT, log_level="info")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


       
