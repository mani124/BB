import React from 'react';
import { Dialog } from '../../components/Dialog';
import { SHORTCUTS } from '../shortcuts';

export const ShortcutHelp: React.FC<{ onClose: () => void }> = ({ onClose }) => (
  <Dialog label="Keyboard shortcuts" onClose={onClose} className="p-4">
    <div style={{ maxWidth: 480 }}>
      <h2 className="text-base font-semibold mb-2">Keyboard shortcuts</h2>
      <table className="desk-table">
        <caption className="sr-only">Keyboard shortcuts</caption>
        <thead><tr><th scope="col">Keys</th><th scope="col">Action</th></tr></thead>
        <tbody>
          {SHORTCUTS.map((s) => (
            <tr key={s.id}><td><kbd className="desk-num">{s.keys}</kbd></td><td>{s.description}</td></tr>
          ))}
        </tbody>
      </table>
      <div className="flex justify-end mt-3"><button type="button" className="desk-btn" onClick={onClose}>Close</button></div>
    </div>
  </Dialog>
);
