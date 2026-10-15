import { Router, Request, Response } from 'express';
import { BotManager } from '../managers/bot_manager';
import { BotAction } from '../types/trade';

export function createApiRouter(botManager: BotManager): Router {
  const router = Router();

  router.get('/status', (_req: Request, res: Response) => {
    res.json(botManager.getState());
  });

  router.post('/sync', (req: Request, res: Response) => {
    const { account, market } = req.body;
    if (account || market) {
      botManager.updateRealData(account, market);
      return res.json({ success: true });
    }
    res.status(400).json({ error: 'Missing sync payload' });
  });

  router.post('/action', (req: Request, res: Response) => {
    const { action, timeframe } = req.body as { action: BotAction; timeframe?: string };
    let success = false;

    if (action === 'START_BOT') {
      success = botManager.startTrading();
    } else if (action === 'STOP_BOT') {
      success = botManager.stopTrading();
    } else if (action === 'CLOSE_ALL') {
      success = botManager.closeAllPositions();
    } else if (action === 'SET_TIMEFRAME') {
      success = botManager.setTimeframe(timeframe || 'M15');
    } else {
      return res.status(400).json({ error: 'Unsupported action' });
    }

    res.json({ success, action });
  });

  return router;
}
