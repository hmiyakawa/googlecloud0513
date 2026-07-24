require('dotenv').config();
const express = require('express');
const path = require('path');
const apiRoutes = require('../routes/summarizeTranslate');

const app = express();
const PORT = process.env.PORT || 8081;

if (!process.env.ANTHROPIC_API_KEY) {
  console.error('ERROR: ANTHROPIC_API_KEY が設定されていません');
  process.exit(1);
}

app.use(express.json({ limit: '10mb' }));
app.use(express.static(path.join(__dirname, '../public')));
app.use('/', apiRoutes);

app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});

app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, '../public', 'summarize.html'));
});

app.listen(PORT, () => {
  console.log(`✅ サーバー起動: http://localhost:${PORT}`);
});
