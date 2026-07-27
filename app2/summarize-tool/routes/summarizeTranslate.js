// 要約 → 手直し → 英訳 アプリ用のAPIルート
// このファイルを既存プロジェクトの routes フォルダに追加してください。

const express = require('express');
const multer = require('multer');
const pdfParse = require('pdf-parse');
const mammoth = require('mammoth');
const Anthropic = require('@anthropic-ai/sdk');

const router = express.Router();

// アップロードされたファイルはディスクに保存せず、メモリ上でそのまま処理します
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 20 * 1024 * 1024 }, // 20MBまで
});

// .env の ANTHROPIC_API_KEY を読み込んでClaude APIクライアントを作成
const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

// 使用するモデル。.envで ANTHROPIC_MODEL を指定すれば変更可能
const MODEL = process.env.ANTHROPIC_MODEL || 'claude-sonnet-5';

/**
 * POST /api/extract-text
 * アップロードされたPDF/Wordファイルから本文テキストを抽出する
 * リクエスト: multipart/form-data、フィールド名 "file"
 * レスポンス: { text: string }
 */
router.post('/api/extract-text', upload.single('file'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: 'ファイルが送信されていません。' });
    }

    const { originalname, buffer, mimetype } = req.file;
    const lowerName = originalname.toLowerCase();
    let text = '';

    if (mimetype === 'application/pdf' || lowerName.endsWith('.pdf')) {
      const data = await pdfParse(buffer);
      text = data.text;
    } else if (
      mimetype === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
      lowerName.endsWith('.docx')
    ) {
      const result = await mammoth.extractRawText({ buffer });
      text = result.value;
    } else {
      return res.status(400).json({
        error: '対応していないファイル形式です（PDFまたはWord[.docx]のみ対応しています）。',
      });
    }

    res.json({ text });
  } catch (err) {
    console.error('extract-text error:', err);
    res.status(500).json({ error: 'ファイルからのテキスト抽出に失敗しました。' });
  }
});

/**
 * POST /api/summarize
 * リクエスト: { text: string }
 * レスポンス: { summary: string }
 */
router.post('/api/summarize', async (req, res) => {
  try {
    const { text } = req.body;
    if (!text || !text.trim()) {
      return res.status(400).json({ error: '要約する文章が入力されていません。' });
    }

    const message = await anthropic.messages.create({
      model: MODEL,
      max_tokens: 2000,
      messages: [
        {
          role: 'user',
  content:
  '私が送る文章を以下の観点から改善してください。\n\n' +
  '【基本方針】\n' +
  '- 原文のテイストや個性を尊重しながら、読みやすさと明確さを向上させる\n\n' +
  '【改善してほしいポイント】\n' +
  '1. 文法と表記：\n' +
  '   • 誤字脱字の修正\n' +
  '   • 表記揺れの統一（例：「〜です」と「〜である」の混在など）\n\n' +
  '2. 表現の洗練：\n' +
  '   • 冗長な表現の簡潔化\n' +
  '   • わかりにくい言い回しの明確化\n' +
  '   • 適切な接続詞の使用\n\n' +
  '3. 構造の最適化：\n' +
  '   • 読みやすい段落分け\n' +
  '   • 論理の流れの改善\n\n' +
  '【レスポンス形式】\n' +
  '- 修正前と修正後の文章を対比して示す\n' +
  '- 重要な修正点とその理由を簡潔に説明する\n\n' +
  '【文体について】\n' +
  '- 文章のコンテキストを尊重する（メールはメールらしく、チャットはチャットらしく、公式文書は公式文書らしく）\n' +
  '- 入力された文章の基本的な調子や個性を維持する\n\n' +
  'あくまで私の伝えたい内容や文体を尊重した上で、読み手にとって理解しやすい文章になるようお願いします。\n\n---\n' +
  text +
  '\n---',
        },
      ],
    });

    const summary = message.content
      .filter((block) => block.type === 'text')
      .map((block) => block.text)
      .join('\n');

    res.json({ summary });
  } catch (err) {
    console.error('summarize error:', err);
    res.status(500).json({ error: '要約の生成に失敗しました。しばらくしてから再度お試しください。' });
  }
});

/**
 * POST /api/translate
 * リクエスト: { text: string }
 * レスポンス: { translation: string }
 */
router.post('/api/translate', async (req, res) => {
  try {
    const { text } = req.body;
    if (!text || !text.trim()) {
      return res.status(400).json({ error: '翻訳する文章が入力されていません。' });
    }

    const message = await anthropic.messages.create({
      model: MODEL,
      max_tokens: 2000,
      messages: [
        {
          role: 'user',
content:
  '以下の日本語の文章を、自然で読みやすいビジネス向けの英語に翻訳してください。' +
  '説明や前置きは付けず、翻訳結果のみを出力してください。\n\n---\n' +
  text +
  '\n---',
        },
      ],
    });

    const translation = message.content
      .filter((block) => block.type === 'text')
      .map((block) => block.text)
      .join('\n');

    res.json({ translation });
  } catch (err) {
    console.error('translate error:', err);
    res.status(500).json({ error: '翻訳の生成に失敗しました。しばらくしてから再度お試しください。' });
  }
});

module.exports = router;
