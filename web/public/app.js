const socket = io();

// UI Elements
const elTerminalStatus = document.getElementById('terminal-status');
const elEngineStatus = document.getElementById('engine-status');
const elBalance = document.getElementById('val-balance');
const elEquity = document.getElementById('val-equity');
const elAccount = document.getElementById('val-account');
const elQuote = document.getElementById('val-quote');
const elModel = document.getElementById('val-model');
const elPositionsBody = document.getElementById('positions-body');
const elPosCount = document.getElementById('pos-count');
const elLogBox = document.getElementById('log-box');
const elLivePrice = document.getElementById('chart-live-price');
const chartContainer = document.getElementById('tradingview-chart');

// Lightweight Charts Initialization
let chart = null;
let candleSeries = null;
let isChartInitialized = false;

function initChart() {
  if (!chartContainer || typeof LightweightCharts === 'undefined') return;

  chart = LightweightCharts.createChart(chartContainer, {
    width: chartContainer.clientWidth,
    height: 380,
    layout: {
      background: { color: 'transparent' },
      textColor: '#94a3b8',
      fontFamily: "'JetBrains Mono', monospace"
    },
    grid: {
      vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
      horzLines: { color: 'rgba(255, 255, 255, 0.04)' }
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
    },
    rightPriceScale: {
      borderColor: 'rgba(255, 255, 255, 0.08)',
      scaleMargins: {
        top: 0.1,
        bottom: 0.1,
      },
    },
    timeScale: {
      borderColor: 'rgba(255, 255, 255, 0.08)',
      timeVisible: true,
      secondsVisible: false,
    },
  });

  candleSeries = chart.addCandlestickSeries({
    upColor: '#10b981',
    downColor: '#ef4444',
    borderVisible: false,
    wickUpColor: '#10b981',
    wickDownColor: '#ef4444',
  });

  // Responsive resize
  window.addEventListener('resize', () => {
    if (chart && chartContainer) {
      chart.applyOptions({ width: chartContainer.clientWidth });
    }
  });

  isChartInitialized = true;
}

// Log utility
function appendLog(text) {
  const line = document.createElement('div');
  line.className = 'log-line';
  const time = new Date().toLocaleTimeString();
  line.innerText = `[${time}] ${text}`;
  elLogBox.appendChild(line);
  elLogBox.scrollTop = elLogBox.scrollHeight;
}

socket.on('connect', () => {
  appendLog('Connected to Web Dashboard Server');
  if (!isChartInitialized) {
    initChart();
  }
});

socket.on('state_update', (data) => {
  if (!data) return;

  // Terminal connection
  if (data.connected) {
    elTerminalStatus.className = 'status-pill online';
    elTerminalStatus.querySelector('.text').innerText = 'MT5 CONNECTED';
  } else {
    elTerminalStatus.className = 'status-pill';
    elTerminalStatus.querySelector('.text').innerText = 'MT5 DISCONNECTED';
  }

  // Engine state
  if (data.engine_running) {
    elEngineStatus.className = 'status-pill active';
    elEngineStatus.querySelector('.text').innerText = 'BOT RUNNING';
  } else {
    elEngineStatus.className = 'status-pill';
    elEngineStatus.querySelector('.text').innerText = 'BOT PAUSED';
  }

  // Account
  if (data.account) {
    elBalance.innerHTML = `${Number(data.account.balance).toLocaleString('en-US', { minimumFractionDigits: 2 })} <span class="currency">${data.account.currency}</span>`;
    elEquity.innerHTML = `${Number(data.account.equity).toLocaleString('en-US', { minimumFractionDigits: 2 })} <span class="currency">${data.account.currency}</span>`;
    elAccount.innerText = `Login: ${data.account.login} | ${data.account.server}`;
  }

  // Market & Real-time Chart
  if (data.market) {
    elQuote.innerText = `Bid: ${data.market.bid} | Ask: ${data.market.ask} | Sprd: ${data.market.spread}`;
    if (elLivePrice && data.market.bid > 0) {
      elLivePrice.innerText = `${data.market.bid.toFixed(2)}`;
    }

    // Render / Update Chart Candles
    if (candleSeries && data.market.candles && data.market.candles.length > 0) {
      try {
        candleSeries.setData(data.market.candles);
        if (!window._chartFitted && chart) {
          chart.timeScale().fitContent();
          window._chartFitted = true;
        }
      } catch (err) {
        console.error('[CHART_RENDER_ERR]', err);
      }
    }
  }

  if (data.model) {
    elModel.innerText = data.model;
  }

  // Timeframe indicator
  if (data.timeframe) {
    const elTfLabel = document.getElementById('chart-tf-label');
    if (elTfLabel) elTfLabel.innerText = data.timeframe;

    // Update active button state
    document.querySelectorAll('.tf-btn').forEach(btn => {
      btn.classList.toggle('active', btn.innerText === data.timeframe);
    });
  }

  // Positions
  renderPositions(data.positions || []);

  // Order Execution History
  renderHistory(data.history || []);
});

function renderPositions(positions) {
  elPosCount.innerText = `${positions.length} ACTIVE`;

  if (positions.length === 0) {
    elPositionsBody.innerHTML = `<tr><td colspan="7" class="empty-state">No open positions currently active.</td></tr>`;
    return;
  }

  let html = '';
  positions.forEach((p) => {
    const isProfit = p.profit >= 0;
    const profitColor = isProfit ? '#10b981' : '#ef4444';
    html += `
      <tr>
        <td>#${p.ticket}</td>
        <td><strong style="color: ${p.type === 'BUY' ? '#38bdf8' : '#f59e0b'}">${p.type}</strong></td>
        <td>${p.volume}</td>
        <td>${p.price_open}</td>
        <td>${p.sl || '-'}</td>
        <td>${p.tp || '-'}</td>
        <td style="color: ${profitColor}; font-weight: 600;">${p.profit > 0 ? '+' : ''}${p.profit}</td>
      </tr>
    `;
  });
  elPositionsBody.innerHTML = html;
}

function renderHistory(history) {
  const elHistoryBody = document.getElementById('history-body');
  if (!elHistoryBody) return;

  if (history.length === 0) {
    elHistoryBody.innerHTML = `<tr><td colspan="8" class="empty-state">No past execution records found.</td></tr>`;
    return;
  }

  let html = '';
  history.forEach((d) => {
    const isProfit = d.profit >= 0;
    const profitColor = isProfit ? '#10b981' : '#ef4444';
    html += `
      <tr>
        <td>${d.time}</td>
        <td>#${d.ticket}</td>
        <td>#${d.order}</td>
        <td><strong>${d.symbol}</strong></td>
        <td><span style="color: ${d.type === 'BUY' ? '#38bdf8' : '#f59e0b'}; font-weight: 700;">${d.type}</span></td>
        <td>${d.volume}</td>
        <td>${d.price}</td>
        <td style="color: ${profitColor}; font-weight: 600;">${d.profit > 0 ? '+' : ''}${d.profit}</td>
      </tr>
    `;
  });
  elHistoryBody.innerHTML = html;
}

function setTimeframe(tf) {
  appendLog(`Switching chart timeframe to ${tf}...`);
  window._chartFitted = false; // Reset to refit chart
  fetch('/api/action', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'SET_TIMEFRAME', timeframe: tf })
  })
  .then(res => res.json())
  .then(data => {
    appendLog(`Timeframe changed to ${tf}`);
  })
  .catch(err => {
    appendLog(`Error changing timeframe: ${err.message}`);
  });
}

function sendAction(action) {
  appendLog(`Sending command: ${action}`);
  fetch('/api/action', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action })
  })
  .then(res => res.json())
  .then(data => {
    appendLog(`Response: ${data.action} accepted`);
  })
  .catch(err => {
    appendLog(`Error: ${err.message}`);
  });
}

// Initial chart trigger
document.addEventListener('DOMContentLoaded', () => {
  initChart();
});
