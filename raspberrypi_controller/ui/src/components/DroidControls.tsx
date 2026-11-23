import { Alert, Button, Card, Checkbox, Code, Divider, Group, NumberInput, Select, Slider, Stack,
  Text, Title } from '@mantine/core';
import { useMemo, useState } from 'react';
import { Board, BoardState } from '../api';
import { useCommand } from './useAction';

interface Props {
  board: Board;
  state?: BoardState;
  onDone: () => void;
}

export function DroidControls({ board, state, onDone }: Props) {
  const { busy, run } = useCommand(board.device_id, onDone);
  const sounds = state?.sounds ?? [];
  const isBB = state?.status.type === 'bb';
  const [sound, setSound] = useState<string | null>(null);
  const [turnHead, setTurnHead] = useState(false);
  const [volume, setVolume] = useState(20);
  const [diagnosis, setDiagnosis] = useState<Record<string, unknown>>();
  const disabled = !board.online || !state?.status.configured;

  const options = useMemo(() => sounds.map((s) => ({
    value: String(s.index),
    label: `#${s.index}  (group ${s.group}, sound ${s.sound}, ${(s.ms / 1000).toFixed(1)} s)`,
  })), [sounds]);
  const selected = sound ?? String(board.demo_sound);
  const hasOptions = options.length > 0;
  const btn = (cmd: string, label: string, args: Record<string, unknown> = {}, extra = {}) => (
    <Button size="xs" variant="light" disabled={disabled || (busy !== null && busy !== cmd)}
      loading={busy === cmd} onClick={() => run(cmd, args)} {...extra}>{label}</Button>
  );

  return (
    <Card withBorder>
      <Stack gap="sm">
        <Title order={5}>Controls</Title>
        {!board.online && <Alert color="gray">Board offline.</Alert>}
        {board.online && state && !state.status.configured && (
          <Alert color="yellow">No droid address saved yet. Set one in Configuration.</Alert>
        )}

        <Text size="sm" fw={500}>Sound</Text>
        <Group align="flex-end" wrap="wrap">
          {hasOptions ? (
            <Select style={{ flex: 1, minWidth: 220 }} data={options} value={selected}
              onChange={setSound} allowDeselect={false} searchable disabled={disabled} />
          ) : (
            <NumberInput style={{ flex: 1, minWidth: 120 }} min={0} value={Number(selected)}
              onChange={(v) => setSound(String(v))} disabled={disabled} />
          )}
          <Checkbox label="Turn head" checked={turnHead && !isBB} disabled={disabled || isBB}
            onChange={(e) => setTurnHead(e.currentTarget.checked)} />
          <Button size="xs" disabled={disabled || (busy !== null && busy !== 'beep')} loading={busy === 'beep'}
            onClick={() => run('beep', { sound: Number(selected), turn_head: turnHead && !isBB, wait: true })}>
            Beep
          </Button>
        </Group>

        <Text size="sm" fw={500}>Volume ({volume})</Text>
        <Group wrap="nowrap">
          <Slider style={{ flex: 1 }} min={0} max={31} value={volume} onChange={setVolume} disabled={disabled} />
          <Button size="xs" variant="light" disabled={disabled} loading={busy === 'volume'}
            onClick={() => run('volume', { level: volume })}>Set</Button>
        </Group>

        <Text size="sm" fw={500}>Head</Text>
        <Group gap="xs">
          {btn('center_head', 'Center head', {}, { disabled: disabled || isBB })}
          {btn('look_around', 'Look around', {}, { disabled: disabled || isBB })}
          {btn('demo', 'Run demo', {}, { disabled: disabled || isBB })}
        </Group>
        {isBB && <Text size="xs" c="dimmed">Head commands aren't available on BB units.</Text>}

        <Divider />
        <Text size="sm" fw={500}>Connection</Text>
        <Group gap="xs">
          {btn('connect', 'Connect')}
          {btn('disconnect', 'Disconnect')}
          {btn('check', 'Check')}
          <Button size="xs" variant="light" disabled={!board.online || (busy !== null && busy !== 'diagnose')}
            loading={busy === 'diagnose'}
            onClick={async () => setDiagnosis(await run('diagnose'))}>Diagnose</Button>
        </Group>
        {diagnosis && <Code block fz={12}>{JSON.stringify(diagnosis, null, 2)}</Code>}
      </Stack>
    </Card>
  );
}
