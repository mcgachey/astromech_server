import { Alert, Button, Card, Group, Progress, Select, Stack, Text, Title } from '@mantine/core';
import { useEffect, useRef, useState } from 'react';

import { Board, api } from '../api';
import { usePoll } from '../hooks';
import { fail, ok } from '../notify';

const cmp = (a: string, b: string) => {
  const [x, y] = [a, b].map((v) => v.split('.').map(Number));
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    if ((x[i] ?? 0) !== (y[i] ?? 0)) return (x[i] ?? 0) - (y[i] ?? 0);
  }
  return 0;
};

/** Install a firmware version (full image) on one board. Works while the board is offline too. */
export function FirmwareSection({ board, onChanged }: { board: Board; onChanged: () => void }) {
  const active = board.flash?.active ?? false;
  const { data, error, refresh } = usePoll(() => api.boardFirmware(board.device_id), active ? 1000 : 15000);
  const [version, setVersion] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const running = board.online ? board.info?.firmware_version : undefined;
  const images = (data?.images ?? []).filter((i) => i.valid);
  const flash = data?.flash ?? board.flash ?? null;
  const flashing = active || (flash?.active ?? false);

  // Preselect the newest valid image.
  useEffect(() => {
    if (!version && images.length) setVersion(images[0].version);
  }, [images, version]);

  // Report the outcome once when a flash that we saw running ends.
  const wasActive = useRef(false);
  useEffect(() => {
    if (flashing) { wasActive.current = true; return; }
    if (!wasActive.current || !flash) return;
    wasActive.current = false;
    if (flash.stage === 'done') ok('Firmware installed', `${board.name} now runs ${flash.version}`);
    else if (flash.stage === 'failed') fail('Firmware install failed', new Error(flash.error ?? 'unknown error'));
    onChanged();
  }, [flashing, flash, board.name, onChanged]);

  const label = (v: string, build: string) => {
    const tag = running === undefined ? '' : cmp(v, running) === 0 ? ' (running)' :
      cmp(v, running) < 0 ? ' (older)' : ' (newer)';
    return `${v}${build ? ` · ${build}` : ''}${tag}`;
  };

  const install = async () => {
    if (!version) return;
    const downgrade = running !== undefined && cmp(version, running) < 0;
    const msg = `Write ${board.role} firmware ${version} to "${board.name}"?\n\n` +
      'The bootloader, partition table and app are rewritten; saved settings are kept. ' +
      'The board is disconnected for about half a minute.' +
      (downgrade ? `\n\nNote: this is OLDER than the running ${running}.` : '');
    if (!window.confirm(msg)) return;
    setStarting(true);
    try {
      await api.flash(board.device_id, version);
      await refresh();
      onChanged();
    } catch (e) {
      fail('Could not start the install', e);
    }
    setStarting(false);
  };

  return (
    <Card withBorder>
      <Stack gap="xs">
        <Title order={5}>Firmware</Title>
        <Text size="sm">
          Running: <b>{running ?? 'unknown (board offline)'}</b>
        </Text>
        {error && <Alert color="red">{error.message}</Alert>}
        {images.length === 0 ? (
          <Text size="sm" c="dimmed">
            No {board.role} firmware installed on the controller. Run <code>make install</code> on
            the build machine, then scan on the Firmware tab.
          </Text>
        ) : (
          <Group align="flex-end">
            <Select label="Version" w={280} allowDeselect={false} value={version}
              onChange={setVersion} disabled={flashing}
              data={images.map((i) => ({ value: i.version, label: label(i.version, i.build_id) }))} />
            <Button color="orange" disabled={!version || flashing} loading={starting || flashing}
              onClick={install}>
              Install
            </Button>
          </Group>
        )}
        {flashing && flash && (
          <Stack gap={4}>
            <Progress value={flash.stage === 'writing' ? flash.percent : 100}
              animated={flash.stage !== 'writing'} />
            <Text size="xs" c="dimmed">
              Installing {flash.version}: {flash.stage}
              {flash.stage === 'writing' ? ` ${Math.round(flash.percent)}%` : '…'}. Don't unplug the board.
            </Text>
          </Stack>
        )}
        {!flashing && flash?.stage === 'failed' && (
          <Alert color="red" title={`Installing ${flash.version} failed`}>{flash.error}</Alert>
        )}
        {!flashing && flash?.stage === 'done' && (
          <Alert color="teal">Installed {flash.version}.</Alert>
        )}
      </Stack>
    </Card>
  );
}
