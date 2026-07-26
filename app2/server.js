require('dotenv').config();
const express = require('express');
const path = require('path');
const session = require('express-session');
const passport = require('passport');
const GoogleStrategy = require('passport-google-oauth20').Strategy;
const apiRoutes = require('../routes/summarizeTranslate');

const app = express();
const PORT = process.env.PORT || 8081;

if (!process.env.ANTHROPIC_API_KEY) {
  console.error('ERROR: ANTHROPIC_API_KEY が設定されていません');
  process.exit(1);
}

// 許可するドメインとメールアドレス
const ALLOWED_DOMAINS = (process.env.ALLOWED_DOMAINS || '').split(',');
const ALLOWED_EMAILS = (process.env.ALLOWED_EMAILS || '').split(',');

function isAllowed(email) {
  if (ALLOWED_EMAILS.includes(email)) return true;
  const domain = email.split('@')[1];
  return ALLOWED_DOMAINS.includes(domain);
}

// セッション設定
app.use(session({
  secret: process.env.SESSION_SECRET || 'secret',
  resave: false,
  saveUninitialized: false,
  cookie: { maxAge: 24 * 60 * 60 * 1000 }
}));

// Passport設定
app.use(passport.initialize());
app.use(passport.session());

passport.use(new GoogleStrategy({
  clientID: process.env.GOOGLE_CLIENT_ID,
  clientSecret: process.env.GOOGLE_CLIENT_SECRET,
  callbackURL: 'http://tools.ad-comm.com:8081/auth/callback'
}, (accessToken, refreshToken, profile, done) => {
  const email = profile.emails[0].value;
  if (!isAllowed(email)) {
    return done(null, false, { message: 'アクセス権限がありません' });
  }
  return done(null, profile);
}));

passport.serializeUser((user, done) => done(null, user));
passport.deserializeUser((user, done) => done(null, user));

// 認証チェックミドルウェア
function requireAuth(req, res, next) {
  if (req.isAuthenticated()) return next();
  res.redirect('/login');
}

// 認証ルート
app.get('/login', (req, res) => {
  res.send(`
    <!DOCTYPE html>
    <html lang="ja">
    <head>
      <meta charset="UTF-8">
      <title>ログイン - AD-COMM Tools</title>
      <style>
        body { font-family: sans-serif; display: flex; align-items: center;
               justify-content: center; height: 100vh; margin: 0;
               background: #f0f4f8; }
        .box { background: white; padding: 40px; border-radius: 8px;
               text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        h1 { font-size: 20px; margin-bottom: 8px; }
        p { color: #666; margin-bottom: 24px; }
        a { display: inline-block; background: #4285f4; color: white;
            padding: 12px 24px; border-radius: 6px; text-decoration: none; }
        a:hover { background: #3367d6; }
      </style>
    </head>
    <body>
      <div class="box">
        <h1>AD-COMM Tools</h1>
        <p>組織のGoogleアカウントでログインしてください</p>
        <a href="/auth/google">Googleでログイン</a>
      </div>
    </body>
    </html>
  `);
});

app.get('/auth/google',
  passport.authenticate('google', { scope: ['profile', 'email'] })
);

app.get('/auth/callback',
  passport.authenticate('google', { failureRedirect: '/login?error=denied' }),
(req, res) => res.redirect('/summarize.html')
);

app.get('/logout', (req, res) => {
  req.logout(() => res.redirect('/login'));
});

// 以降のルートはすべて認証必須
app.use(express.json({ limit: '10mb' }));
app.use(requireAuth);
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