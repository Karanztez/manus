import { Server, Socket } from 'socket.io';
import { BotManager } from './bot_manager';
import { CommandPayload, DashboardState } from '../types/trade';

export class SocketManager {
  private io: Server;
  private botManager: BotManager;

  constructor(io: Server, botManager: BotManager) {
    this.io = io;
    this.botManager = botManager;
  }

  public init(): void {
    this.io.on('connection', (socket: Socket) => {
      console.log('[WS] Client connected to TypeScript Dashboard');
      socket.emit('state_update', this.botManager.getState());

      socket.on('command', (cmd: CommandPayload) => {
        if (cmd.action === 'START_BOT') this.botManager.startTrading();
        else if (cmd.action === 'STOP_BOT') this.botManager.stopTrading();
        else if (cmd.action === 'CLOSE_ALL') this.botManager.closeAllPositions();
        else if (cmd.action === 'SET_TIMEFRAME' && cmd.timeframe) {
          this.botManager.setTimeframe(cmd.timeframe);
        }
      });
    });

    // Listen to real sync updates and broadcast to web clients
    this.botManager.on('real_sync', (state: DashboardState) => {
      this.io.emit('state_update', state);
    });

    // Listen to gateway events and broadcast to all connected web clients
    this.botManager.getGateway().on('message', (msg: { type: string; data: DashboardState }) => {
      if (msg.type === 'STATUS_UPDATE') {
        this.io.emit('state_update', msg.data);
      }
    });
  }

  public broadcastLog(message: string): void {
    this.io.emit('log_message', { timestamp: new Date().toISOString(), message });
  }
}
