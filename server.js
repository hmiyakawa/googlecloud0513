require('dotenv').config();
const express = require('express');
const fetch = require('node-fetch');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 8080;
const ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY;

if (!ANTHROPIC_API_KEY) {
  console.error('ERROR: ANTHROPIC_API_KEY が設定されていません');
  process.exit(1);
}

app.use(express.json({ limit: '1mb' }));
app.use(express.static(path.join(__dirname, 'public')));

// ── ヘルスチェック（Cloud Run 用）
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// ── 翻訳 API エンドポイント
app.post('/api/translate', async (req, res) => {
  const { prompt } = req.body;

  if (!prompt || typeof prompt !== 'string') {
    return res.status(400).json({ error: 'prompt が不正です' });
  }
  if (prompt.length > 5000) {
    return res.status(400).json({ error: 'テキストが長すぎます（上限 5000 文字）' });
  }

  try {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 1000,
        messages: [{ role: 'user', content: prompt }],
      }),
    });

    if (!response.ok) {
      const err = await response.text();
      console.error('Anthropic API error:', err);
      return res.status(502).json({ error: 'Anthropic API エラー' });
    }

    const data = await response.json();
    const text = data.content
      .filter((b) => b.type === 'text')
      .map((b) => b.text)
      .join('');

    res.json({ text });
  } catch (err) {
    console.error('Server error:', err);
    res.status(500).json({ error: 'サーバーエラー' });
  }
});

// ── SPA フォールバック
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`✅ サーバー起動: http://localhost:${PORT}`);
});
