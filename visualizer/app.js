// app.js
const express = require('express');
const path = require('path');
const { PUBLIC_DIR } = require('./config/paths');

const jobsRouter = require('./routes/jobs');
const blocksRouter = require('./routes/blocks');
const qubicRouter = require('./routes/qubic');
const orphanRouter = require('./routes/orphan');
const selfishRouter = require('./routes/selfish'); 

const app = express();

app.use(express.static(PUBLIC_DIR, { index: false }));

app.get('/healthz', (_req, res) => res.status(200).send('ok'));

app.get('/', (_req, res) => res.sendFile(path.join(PUBLIC_DIR, 'main.html')));
app.get('/jobs', (_req, res) => res.sendFile(path.join(PUBLIC_DIR, 'jobs.html')));
app.get('/blocks', (_req, res) => res.sendFile(path.join(PUBLIC_DIR, 'blocks.html')));
app.get('/selfish_mining', (_req, res) =>
  res.sendFile(path.join(PUBLIC_DIR, 'selfish_mining.html'))
); 

app.use(jobsRouter);
app.use(blocksRouter);
app.use(qubicRouter);
app.use(orphanRouter);
app.use(selfishRouter); 

app.use((req, res) => res.status(404).send('Not Found'));

module.exports = app;

