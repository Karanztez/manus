import { EventEmitter } from 'events';
import { GatewayConnector } from '../connectors/gateway_connector';
import { DashboardState } from '../types/trade';

export class BotManager extends EventEmitter {
  private gateway: GatewayConnector;
  private latestState: DashboardState;

  constructor(gatewayConnector: GatewayConnector) {
    super();
    this.gateway = gatewayConnector;
    this.latestState = {
      engine_running: false,
      connected: false,
      timeframe: 'M15',
      account: { login: 'Connecting...', server: 'XMGlobal-MT5 5', balance: 0, equity: 0, currency: 'THB', leverage: 0 },
      market: { symbol: 'GOLD#', bid: 0, ask: 0, spread: 0, candles: [] },
      positions: [],
      history: [],
      model: 'gemini-flash-latest'
    };

    this.gateway.on('message', (msg: { type: string; data: DashboardState }) => {
      if (msg.type === 'STATUS_UPDATE' && msg.data) {
        this.latestState = msg.data;
      }
    });
  }

  public updateRealData(account: any, market: any): void {
    if (account) {
      this.latestState.connected = true;
      this.latestState.account = {
        login: account.login,
        server: account.server,
        balance: account.balance,
        equity: account.equity,
        currency: account.currency,
        leverage: account.leverage || 100
      };
    }
    if (market) {
      this.latestState.market = market;
    }
    this.emit('real_sync', this.latestState);
  }

  public getGateway(): GatewayConnector {
    return this.gateway;
  }

  public getState(): DashboardState {
    return this.latestState;
  }

  public startTrading(): boolean {
    return this.gateway.sendCommand({ action: 'START_BOT' });
  }

  public stopTrading(): boolean {
    return this.gateway.sendCommand({ action: 'STOP_BOT' });
  }

  public closeAllPositions(): boolean {
    return this.gateway.sendCommand({ action: 'CLOSE_ALL' });
  }

  public setTimeframe(timeframe: string): boolean {
    return this.gateway.sendCommand({ action: 'SET_TIMEFRAME', timeframe });
  }

  public refreshStatus(): boolean {
    return this.gateway.sendCommand({ action: 'GET_STATUS' });
  }
}
