import React, { Suspense, lazy } from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { chooseShell } from './shell/chooseShell';
import '@fontsource/ibm-plex-sans/latin-400.css';
import '@fontsource/ibm-plex-sans/latin-500.css';
import '@fontsource/ibm-plex-sans/latin-600.css';
import '@fontsource/ibm-plex-sans/latin-ext-400.css';
import '@fontsource/ibm-plex-sans/latin-ext-500.css';
import '@fontsource/ibm-plex-sans/latin-ext-600.css';
import '@fontsource/ibm-plex-mono/latin-400.css';
import '@fontsource/ibm-plex-mono/latin-500.css';
import '@fontsource/ibm-plex-mono/latin-600.css';
import '@fontsource/ibm-plex-mono/latin-ext-400.css';
import '@fontsource/ibm-plex-mono/latin-ext-500.css';
import '@fontsource/ibm-plex-mono/latin-ext-600.css';
import './index.css';

const DockApp = lazy(() => import('./shell/DockApp'));
const shell = chooseShell(window.location.search, (() => { try { return window.localStorage; } catch { return null; } })());

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {shell === 'dock' ? (
      <Suspense fallback={<div className="p-4 text-sm">Loading dashboard</div>}><DockApp /></Suspense>
    ) : (
      <App />
    )}
  </React.StrictMode>
);
