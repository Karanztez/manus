export interface AccountState {
  login: string | number;
  server: string;
  balance: number;
  equity: number;
  currency: string;
  leverage: number;
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface MarketState {
  symbol: string;
  bid: number;
  ask: number;
  spread: number;
  candles: Candle[];
}

export interface Position {
  ticket: number;
  type: 'BUY' | 'SELL';
  volume: number;
  price_open: number;
  sl: number;
  tp: number;
  profit: number;
}

export interface DealHistory {
  ticket: number;
  order: number;
  symbol: string;
  type: 'BUY' | 'SELL' | 'OTHER';
  volume: number;
  price: number;
  profit: number;
  time: string;
}

export interface DashboardState {
  engine_running: boolean;
  connected: boolean;
  timeframe: string;
  account: AccountState;
  market: MarketState;
  positions: Position[];
  history: DealHistory[];
  model: string;
}

export type BotAction = 'START_BOT' | 'STOP_BOT' | 'CLOSE_ALL' | 'SET_TIMEFRAME' | 'GET_STATUS';

export interface CommandPayload {
  action: BotAction;
  timeframe?: string;
}
