const { app, BrowserWindow, ipcMain, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

function createWindow() {
  const win = new BrowserWindow({
    width: 900,
    height: 700,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
    },
    alwaysOnTop: true
  });
  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
}

app.whenReady().then(() => {
  createWindow();

  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') app.quit();
});

ipcMain.handle('run-import', async (event, args) => {
  const py = args.python || 'python';
  const channel = args.channel;
  const limit = args.limit || 500;
  const out = args.out || './output';

  return await new Promise((resolve) => {
    const script = path.join(__dirname, 'src', 'run_import.py');
    // Prepare child env - copy parent env but inject LLM vars only for this run (kept in memory)
    const childEnv = Object.assign({}, process.env);
    if (args.llmBackend) childEnv.LLM_BACKEND = args.llmBackend;
    if (args.geminiApiUrl) childEnv.GEMINI_API_URL = args.geminiApiUrl;
    if (args.geminiApiKey) childEnv.GEMINI_API_KEY = args.geminiApiKey;
    if (args.llmApiUrl) childEnv.LLM_API_URL = args.llmApiUrl;
    if (args.llmApiKey) childEnv.LLM_API_KEY = args.llmApiKey;
    if (args.userCategories) childEnv.USER_CATEGORIES = args.userCategories;
    if (args.maxCategories) childEnv.MAX_CATEGORIES = String(args.maxCategories);
    if (args.sessionName) childEnv.SESSION_NAME = args.sessionName;

    const proc = spawn(py, [script, '--channel', channel, '--limit', String(limit), '--out', out], { env: childEnv });
    proc.stdout.on('data', (d) => {
      event.sender.send('import-log', d.toString());
    });
    proc.stderr.on('data', (d) => {
      event.sender.send('import-log', d.toString());
    });
    proc.on('close', (code) => {
      // Prefer tree.json (categorized structure); fall back to index.json
      const treePath = path.join(out, 'tree.json');
      const indexPath = path.join(out, 'index.json');
      if (fs.existsSync(treePath)) {
        try {
          const data = JSON.parse(fs.readFileSync(treePath, 'utf8'));
          resolve({ ok: true, data, source: 'tree' });
          return;
        } catch (e) {
          resolve({ ok: false, error: 'Failed to parse tree.json' });
          return;
        }
      } else if (fs.existsSync(indexPath)) {
        try {
          const data = JSON.parse(fs.readFileSync(indexPath, 'utf8'));
          resolve({ ok: true, data, source: 'index' });
          return;
        } catch (e) {
          resolve({ ok: false, error: 'Failed to parse index.json' });
          return;
        }
      }
      resolve({ ok: false, error: 'Import finished but no tree/index json found', code });
    });
  });
});

ipcMain.handle('read-index', async (event, indexPath) => {
  // Try tree.json in the same folder as the provided path (or default output)
  const provided = indexPath || path.join(__dirname, 'output', 'index.json');
  const baseDir = path.dirname(provided);
  const treePath = path.join(baseDir, 'tree.json');
  if (fs.existsSync(treePath)) {
    try {
      return { ok: true, data: JSON.parse(fs.readFileSync(treePath, 'utf8')), source: 'tree' };
    } catch (e) {
      return { ok: false, error: 'Failed to parse tree.json' };
    }
  }
  if (fs.existsSync(provided)) {
    try {
      return { ok: true, data: JSON.parse(fs.readFileSync(provided, 'utf8')), source: 'index' };
    } catch (e) {
      return { ok: false, error: 'Failed to parse index.json' };
    }
  }
  return { ok: false, error: 'No tree/index json found' };
});

ipcMain.handle('open-external', async (event, url) => {
  shell.openExternal(url);
});

ipcMain.handle('get-session-info', async (event, sessionName) => {
  // Determine the session name and file path (session file is stored in app root by Telethon by default)
  const name = sessionName || process.env.SESSION_NAME || 'telegram_course_session';
  const sessionFile = path.join(__dirname, `${name}.session`);
  return { sessionName: name, sessionPath: sessionFile, exists: fs.existsSync(sessionFile) };
});

ipcMain.handle('delete-session', async (event, sessionPath) => {
  try {
    if (!sessionPath) return { ok: false, error: 'no path provided' };
    if (fs.existsSync(sessionPath)) {
      fs.unlinkSync(sessionPath);
      return { ok: true };
    } else {
      return { ok: false, error: 'file not found' };
    }
  } catch (e) {
    return { ok: false, error: e.message };
  }
});

ipcMain.handle('tg-send-code', async (event, payload) => {
  const py = payload.python || 'python';
  const phone = payload.phone;
  const sessionName = payload.sessionName;
  if (!phone) {
    return { ok: false, error: 'phone is required' };
  }
  const script = path.join(__dirname, 'src', 'auth_flow.py');
  return await new Promise((resolve) => {
    const args = [script, 'send-code', '--phone', phone];
    if (sessionName) {
      args.push('--session', sessionName);
    }
    const childEnv = Object.assign({}, process.env);
    const proc = spawn(py, args, { env: childEnv });
    let out = '';
    let err = '';
    proc.stdout.on('data', (d) => { out += d.toString(); });
    proc.stderr.on('data', (d) => { err += d.toString(); });
    proc.on('close', (code) => {
      if (code === 0) {
        const hash = out.trim().split(/\s+/)[0] || '';
        resolve({ ok: true, codeHash: hash });
      } else {
        resolve({ ok: false, error: err || 'send-code failed' });
      }
    });
  });
});

ipcMain.handle('tg-sign-in', async (event, payload) => {
  const py = payload.python || 'python';
  const phone = payload.phone;
  const code = payload.code;
  const codeHash = payload.codeHash;
  const password = payload.password;
  const sessionName = payload.sessionName;
  if (!phone || !code || !codeHash) {
    return { ok: false, error: 'phone, code and codeHash are required' };
  }
  const script = path.join(__dirname, 'src', 'auth_flow.py');
  return await new Promise((resolve) => {
    const args = [script, 'sign-in', '--phone', phone, '--code', code, '--code-hash', codeHash];
    if (sessionName) {
      args.push('--session', sessionName);
    }
    if (password) {
      args.push('--password', password);
    }
    const childEnv = Object.assign({}, process.env);
    const proc = spawn(py, args, { env: childEnv });
    let out = '';
    let err = '';
    proc.stdout.on('data', (d) => { out += d.toString(); });
    proc.stderr.on('data', (d) => { err += d.toString(); });
    proc.on('close', (code) => {
      const text = out.trim();
      if (text.includes('PASSWORD_NEEDED')) {
        resolve({ ok: false, passwordNeeded: true });
        return;
      }
      if (code === 0 && text.includes('OK')) {
        resolve({ ok: true });
      } else {
        resolve({ ok: false, error: err || text || 'sign-in failed' });
      }
    });
  });
});

