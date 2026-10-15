/**
 * ManusTrade Web Dashboard Entry Point
 * Enterprise Modular Architecture built on Node.js + TypeScript
 */

import express from 'express';
import http from 'http';
import path from 'path';
import { Server } from 'socket.io';

import { config } from './config';
import { GatewayConnector } from './connectors/gateway_connector';
import { BotManager } from './managers/bot_manager';
import { SocketManager } from './managers/socket_manager';
import { createApiRouter } from './routes/api';

const app = express();
const server = http.createServer(app);
const io = new Server(server);

// Middleware
app.use(express.json());
app.use(express.static(path.join(__dirname, '../public')));

// Initialize Components
const gatewayConnector = new GatewayConnector();
const botManager = new BotManager(gatewayConnector);
const socketManager = new SocketManager(io, botManager);

// API Router
app.use('/api', createApiRouter(botManager));

// Start Services
socketManager.init();
gatewayConnector.connect();

server.listen(config.HTTP_PORT, '0.0.0.0', () => {
  console.log(`[READY] ManusTrade Web Dashboard (TypeScript) running at http://0.0.0.0:${config.HTTP_PORT}`);
});
