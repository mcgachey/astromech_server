import { Badge, Button, Card, Code, Group, ScrollArea, SegmentedControl, Stack, Switch, Text,
  Title } from '@mantine/core';
import { useEffect, useRef, useState } from 'react';
import { api, LogEntry } from '../api';
import { usePoll } from '../hooks';
import { fail } from '../notify';

const MAX_SHOWN = 1000;
const KIND_COLOR: Record<string, string> = {
  system: 'gray', event: 'cyan', log: 'gray', command: 'blue', response: 'teal', error: 'red',
};
const FILTERS = [
  { label: 'All', value: 'all' },
  { label: 'Commands', value: 'commands' },
  { label: 'Events', value: 'events' },
  { label: 'Errors', value: 'errors' },
];
const MATCH: Record<string, (e: LogEntry) => boolean> = {
  all: () => true,
  commands: (e) => e.kind === 'command' || e.kind === 'response' || e.kind === 'error',
  events: (e) => e.kind === 'event' || e.kind === 'log' || e.kind === 'system',
  errors: (e) => e.level !== 'info',
};

function time(ts: number) {
  const d = new Date(ts * 1000);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' +
    d.toLocaleTimeString(undefined, { hour12: false }) + '.' + String(d.getMilliseconds()).padStart(3, '0');
}

/** Live message log for one board; the controller keeps it on disk so it survives restarts. */
export function LogPanel({ deviceId }: { deviceId: string }) {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [filter, setFilter] = useState('all');
  const [follow, setFollow] = useState(true);
  const last = useRef(0);
  const viewport = useRef<HTMLDivElement>(null);

  const { refresh } = usePoll(async () => {
    const r = await api.logs(deviceId, last.current);
    if (r.last_seq < last.current) {   // log was cleared (or the controller reset it)
      last.current = 0;
      setEntries([]);
      return r;
    }
    last.current = r.last_seq;
    if (r.entries.length) setEntries((prev) => [...prev, ...r.entries].slice(-MAX_SHOWN));
    return r;
  }, 1500);

  const shown = entries.filter(MATCH[filter]);

  useEffect(() => {
    if (follow && viewport.current) {
      viewport.current.scrollTo({ top: viewport.current.scrollHeight });
    }
  }, [shown.length, follow]);

  const clear = async () => {
    if (!window.confirm('Delete the stored log for this board?')) return;
    try {
      await api.clearLogs(deviceId);
      last.current = 0;
      setEntries([]);
      await refresh();
    } catch (e) { fail('Could not clear log', e); }
  };

  const download = () => {
    const text = shown.map((e) => `${new Date(e.ts * 1000).toISOString()} [${e.kind}] ${e.message}` +
      (e.data ? ' ' + JSON.stringify(e.data) : '')).join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text + '\n'], { type: 'text/plain' }));
    a.download = `${deviceId}.log`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <Card withBorder>
      <Stack gap="xs">
        <Group justify="space-between">
          <Title order={5}>Messages</Title>
          <Group gap="xs">
            <Switch size="xs" label="Follow" checked={follow} onChange={(e) => setFollow(e.currentTarget.checked)} />
            <Button size="compact-xs" variant="default" onClick={download}>Download</Button>
            <Button size="compact-xs" variant="default" color="red" onClick={clear}>Clear</Button>
          </Group>
        </Group>
        <SegmentedControl size="xs" data={FILTERS} value={filter} onChange={setFilter} />
        <ScrollArea h={520} viewportRef={viewport} type="auto">
          <Stack gap={2} ff="monospace">
            {shown.length === 0 && <Text c="dimmed" size="sm">No messages yet.</Text>}
            {shown.map((e) => (
              <Group key={e.seq} gap="xs" wrap="nowrap" align="flex-start">
                <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>{time(e.ts)}</Text>
                <Badge size="xs" variant="light" w={78} color={e.level === 'error' ? 'red' : e.level === 'warning' ? 'orange' : KIND_COLOR[e.kind]}>
                  {e.kind}
                </Badge>
                <div style={{ minWidth: 0 }}>
                  <Text size="xs" style={{ wordBreak: 'break-word' }}>{e.message}</Text>
                  {e.data !== undefined && e.data !== null && (
                    <Code block fz={11} style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(e.data)}</Code>
                  )}
                </div>
              </Group>
            ))}
          </Stack>
        </ScrollArea>
      </Stack>
    </Card>
  );
}
