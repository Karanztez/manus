# ManusTrade - AI MetaTrader 5 Trading Bot (Gemini API)

ระบบเทรดอัตโนมัติบน **MetaTrader 5 (MT5)** ขับเคลื่อนด้วย **Google Gemini API (Free Tier)** สำหรับวิเคราะห์โครงสร้างราคา, แท่งเทียน และอินดิเคเตอร์ทางเทคนิค เพื่อส่งคำสั่งซื้อขายอัตโนมัติ

---

## Architecture
1. **Python AI & Execution Core (`src/`)**:
   - `connectors/mt5_connector.py`: Connects to MetaTrader 5 Terminal, retrieves market data (OHLCV) and executes trade orders (Buy / Sell / Close).
   - `analysis/indicators.py`: Computes EMA, RSI, ATR, and support/resistance levels.
   - `analysis/gemini_trader.py`: Interfaces with Google Gemini API (Free tier) with multi-key pool failover & structured Pydantic output.
   - `managers/risk_manager.py`: Calculates lot size based on equity risk %, validates spread and Risk/Reward ratio.
   - `managers/order_manager.py`: Manages order lifecycle, prevents duplicate trades, and handles reversals.
   - `web_gateway.py`: Real-time IPC / Socket daemon bridging Python MT5 core to the web.

2. **Web Dashboard Module (`web/`) (Node.js + TypeScript)**:
   - `src/types/trade.ts`: Strictly typed interfaces (Account, Candles, Positions, Deals).
   - `src/connectors/gateway_connector.ts`: TCP socket client with auto-reconnection.
   - `src/managers/bot_manager.ts`: Application state & execution controller.
   - `src/managers/socket_manager.ts`: Real-time bi-directional WebSocket hub (Socket.IO).
   - `src/routes/api.ts`: Typed REST endpoints (`/api/status`, `/api/action`).
   - `public/`: Real-time TradingView Lightweight Charts & interactive control UI.

---

## Prerequisites
1. MetaTrader 5 Terminal installed on Windows with 'Allow Algo Trading' enabled (For Local run).
2. Python 3.14 with required packages installed (`requirements.txt`).
3. Node.js v24+ with TypeScript runner (`web/package.json`).
4. Google Gemini API Key from Google AI Studio (Free tier).

---

## 24/7 Linux VPS Deployment (Docker Headless)
หากต้องการรันบอทบน Linux Cloud VPS (Ubuntu/Debian) ตลอด 24 ชม. โดยไม่ต้องเปิดคอมพิวเตอร์ทิ้งไว้:

1. อัปโหลดโฟลเดอร์โปรเจกต์ `ManusTrade` ขึ้นไปยัง Linux VPS (ผ่าน Git หรือ SCP)
2. รันสคริปต์ One-Click Setup:
   ```bash
   chmod +x setup_linux.sh
   ./setup_linux.sh
   ```
3. เปิดหน้าต่างเบราว์เซอร์จากมือถือหรือคอมเครื่องใดก็ได้:
   ```text
   http://YOUR_SERVER_IP:3000
   ```
