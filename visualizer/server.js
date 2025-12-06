// server.js — entrypoint
const app = require('./app');
const PORT = process.env.PORT ? Number(process.env.PORT) : 3000;

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Listening on http://0.0.0.0:${PORT}`);
});

