export const config = {
  HTTP_PORT: process.env.PORT ? parseInt(process.env.PORT, 10) : 3000,
  PYTHON_GATEWAY: {
    HOST: process.env.GATEWAY_HOST || '127.0.0.1',
    PORT: process.env.GATEWAY_PORT ? parseInt(process.env.GATEWAY_PORT, 10) : 9999,
    RETRY_INTERVAL_MS: 3000
  }
};
