import { useCallback, useState } from 'react';
import { api } from '../api';
import { fail } from '../notify';

/** Sends board commands, tracking which one is in flight (for button spinners). */
export function useCommand(deviceId: string, onDone?: () => void) {
  const [busy, setBusy] = useState<string | null>(null);
  const run = useCallback(async (cmd: string, args: Record<string, unknown> = {}) => {
    setBusy(cmd);
    try {
      return await api.command(deviceId, cmd, args);
    } catch (e) {
      fail(`${cmd} failed`, e);
    } finally {
      setBusy(null);
      onDone?.();
    }
  }, [deviceId, onDone]);
  return { busy, run };
}
