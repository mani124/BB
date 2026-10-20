import * as fs from 'fs';
import * as path from 'path';

export function getDashboardKey(): string {
  try {
    const keyPath = path.resolve(__dirname, '../../../backend/data/dashboard_key');
    if (fs.existsSync(keyPath)) {
      return fs.readFileSync(keyPath, 'utf8').trim();
    }
  } catch {
    // fallback if file read fails
  }
  return process.env.DASHBOARD_CAPABILITY || 'bjOvQgS4ydKvRkQTHb2ganM5skKPDoKAdUULsy-1qeI';
}
