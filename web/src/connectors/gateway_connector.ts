import net from 'net';
import { EventEmitter } from 'events';
import { config } from '../config';
import { CommandPayload } from '../types/trade';

export class GatewayConnector extends EventEmitter {
  private client: net.Socket | null = null;
  private buffer: string = '';
  public isConnected: boolean = false;

  public connect(): void {
    this.client = new net.Socket();

    this.client.connect(config.PYTHON_GATEWAY.PORT, config.PYTHON_GATEWAY.HOST, () => {
      this.isConnected = true;
      console.log('[OK] Connected to Python MT5/Gemini Gateway (TypeScript)');
      this.emit('connected');
      this.sendCommand({ action: 'GET_STATUS' });
    });

    this.client.on('data', (data: Buffer) => {
      this.buffer += data.toString('utf-8');
      while (this.buffer.includes('\n')) {
        const line = this.buffer.substring(0, this.buffer.indexOf('\n'));
        this.buffer = this.buffer.substring(this.buffer.indexOf('\n') + 1);
        if (line.trim()) {
          try {
            const parsed = JSON.parse(line.trim());
            this.emit('message', parsed);
          } catch (e: any) {
            console.error('[PARSE_ERROR] Failed parsing gateway response:', e.message);
          }
        }
      }
    });

    this.client.on('error', (err: Error) => {
      console.log('[WARN] Gateway connection retry:', err.message);
    });

    this.client.on('close', () => {
      this.isConnected = false;
      this.emit('disconnected');
      setTimeout(() => this.connect(), config.PYTHON_GATEWAY.RETRY_INTERVAL_MS);
    });
  }

  public sendCommand(cmd: CommandPayload): boolean {
    if (this.client && !this.client.destroyed && this.isConnected) {
      this.client.write(JSON.stringify(cmd) + '\n');
      return true;
    }
    return false;
  }
}
