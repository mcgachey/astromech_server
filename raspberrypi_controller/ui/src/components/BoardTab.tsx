import { Alert, Badge, Button, Card, Grid, Group, Menu, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { Board, api } from '../api';
import { usePoll } from '../hooks';
import { Config } from './Config';
import { DroidControls } from './DroidControls';
import { FirmwareSection } from './FirmwareSection';
import { HomeAssistantSection } from './HomeAssistantSection';
import { LogPanel } from './LogPanel';
import { useCommand } from './useAction';

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <Text size="xs" c="dimmed">{label}</Text>
      <Text size="sm" fw={500}>{value ?? '–'}</Text>
    </div>
  );
}

function duration(ms?: number | null) {
  if (ms === undefined || ms === null) return '–';
  const s = Math.floor(ms / 1000);
  const [d, h, m] = [Math.floor(s / 86400), Math.floor(s / 3600) % 24, Math.floor(s / 60) % 60];
  return (d ? `${d}d ` : '') + (h || d ? `${h}h ` : '') + `${m}m ${s % 60}s`;
}

export function BoardTab({ board, onChanged }: { board: Board; onChanged: () => void }) {
  const { data: state, error, refresh } = usePoll(() => api.state(board.device_id), 5000, board.online);
  const { busy, run } = useCommand(board.device_id, () => { refresh(); onChanged(); });
  const s = state?.status;

  const confirmRun = (cmd: string, what: string) => {
    if (window.confirm(what)) run(cmd);
  };

  return (
    <Grid>
      <Grid.Col span={{ base: 12, lg: 7 }}>
        <Stack>
          <Card withBorder>
            <Group justify="space-between" mb="sm">
              <Group gap="xs">
                <Title order={4}>{board.name}</Title>
                <Badge color={board.online ? 'green' : 'gray'}>{board.online ? 'online' : 'offline'}</Badge>
                {board.role === 'droid' && board.online && s?.configured && (
                  <Badge variant="light" color={s.connected ? 'green' : 'orange'}>
                    droid {s.connected ? 'connected' : 'not connected'}
                  </Badge>
                )}
                {board.role === 'beacon' && board.online && s && (
                  <Badge variant="light" color={s.advertising ? 'green' : 'orange'}>
                    {s.advertising ? 'advertising' : 'not advertising'}
                  </Badge>
                )}
              </Group>
              <Menu position="bottom-end">
                <Menu.Target><Button size="xs" variant="default" disabled={!board.online}>Board ▾</Button></Menu.Target>
                <Menu.Dropdown>
                  <Menu.Item disabled={busy !== null} onClick={() => run('ping')}>Ping</Menu.Item>
                  <Menu.Item disabled={busy !== null}
                    onClick={() => confirmRun('reboot', 'Reboot this board?')}>Reboot</Menu.Item>
                  <Menu.Divider />
                  <Menu.Item color="red" disabled={busy !== null}
                    onClick={() => confirmRun('factory_reset', 'Erase ALL saved settings on this board and restart it?')}>
                    Factory reset…
                  </Menu.Item>
                </Menu.Dropdown>
              </Menu>
            </Group>

            {board.error && !board.online && <Alert color="orange" mb="sm">{board.error}</Alert>}
            {error && board.online && <Alert color="red" mb="sm">{error.message}</Alert>}

            <SimpleGrid cols={{ base: 2, sm: 4 }}>
              <Fact label="Device ID" value={board.device_id} />
              <Fact label="Port" value={board.port} />
              <Fact label="Firmware" value={board.info?.firmware_version} />
              <Fact label="Uptime" value={duration(board.info?.uptime_ms)} />
              {board.role === 'droid' && s?.configured && <>
                <Fact label="Droid" value={`${s.alias} (${s.type})`} />
                <Fact label="Address" value={s.address} />
                <Fact label="Personality" value={s.personality} />
                <Fact label="Last seen" value={s.last_seen_ms_ago == null ? 'never' : duration(s.last_seen_ms_ago) + ' ago'} />
              </>}
              {board.role === 'beacon' && s && <>
                <Fact label="Kind" value={s.kind} />
                <Fact label="Location ID" value={s.kind === 'location' ? s.location_id : '–'} />
                <Fact label="Running" value={duration(s.running_ms)} />
                <Fact label="Watchdog restarts" value={s.watchdog_restarts} />
                {s.stopped_by_master && <Fact label="State" value="stopped by master" />}
              </>}
            </SimpleGrid>
            {board.last_seen && !board.online && (
              <Text size="xs" c="dimmed" mt="sm">Last seen {new Date(board.last_seen * 1000).toLocaleString()}</Text>
            )}
          </Card>

          {board.role === 'droid' ? (
            <DroidControls board={board} state={state} onDone={refresh} />
          ) : (
            <Card withBorder>
              <Stack gap="xs">
                <Title order={5}>Controls</Title>
                <Group>
                  <Button size="xs" variant="light" disabled={!board.online || s?.advertising}
                    loading={busy === 'start'} onClick={() => run('start')}>Start beacon</Button>
                  <Button size="xs" variant="light" color="orange" disabled={!board.online || !s?.advertising}
                    loading={busy === 'stop'} onClick={() => run('stop')}>Stop beacon</Button>
                </Group>
                <Text size="xs" c="dimmed">A stopped beacon stays off (the watchdog won't restart it) until started or rebooted.</Text>
              </Stack>
            </Card>
          )}

          {board.role === 'droid' && <HomeAssistantSection board={board} onDone={onChanged} />}

          <FirmwareSection board={board} onChanged={onChanged} />

          <Config board={board} state={state} onDone={() => { refresh(); onChanged(); }} />
        </Stack>
      </Grid.Col>
      <Grid.Col span={{ base: 12, lg: 5 }}>
        <LogPanel deviceId={board.device_id} />
      </Grid.Col>
    </Grid>
  );
}
