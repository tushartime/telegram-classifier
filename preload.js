const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  runImport: (args) => ipcRenderer.invoke('run-import', args),
  readIndex: (path) => ipcRenderer.invoke('read-index', path),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  onLog: (cb) => {
    ipcRenderer.on('import-log', (event, data) => cb(data));
  },
  getSessionInfo: (sessionName) => ipcRenderer.invoke('get-session-info', sessionName),
  deleteSession: (sessionPath) => ipcRenderer.invoke('delete-session', sessionPath),
  sendLoginCode: (payload) => ipcRenderer.invoke('tg-send-code', payload),
  verifyLogin: (payload) => ipcRenderer.invoke('tg-sign-in', payload)
});

