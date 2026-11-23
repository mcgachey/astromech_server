import { Alert, Badge, Button, Card, Group, NumberInput, Select, Stack, Text, Textarea, Title } from '@mantine/core';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, Board } from '../api';
import { fail, ok } from '../notify';

/**
 * Catalogues a personality chip: plays every sound of every audio group and records how long
 * each one runs (measured by hand, as libastromech's discover_sounds.py does). The result is
 * YAML in the format of config/personalities/*.yml, for the user to copy to a permanent file.
 */

interface Clip { group: number; sound: number; ms: number }
type Phase = 'idle' | 'playing' | 'ask' | 'ready' | 'timing' | 'review' | 'done';

const MAX_SOUND = 99;   // sounds probed per group, as in discover_sounds.py
const STORAGE_KEY = 'personalityClips';

function loadClips(): Clip[] {
  try {
    const v = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]');
    return Array.isArray(v) ? v.filter((c) => [c.group, c.sound, c.ms].every(Number.isFinite)) : [];
  } catch { return []; }
}

/** Same layout as yaml.safe_dump({'sounds': [...]}) in discover_sounds.py. */
export function toYaml(clips: Clip[]): string {
  if (!clips.length) return 'sounds: []\n';
  return 'sounds:\n' + clips.map((c) => `- group: ${c.group}\n  ms: ${c.ms}\n  sound: ${c.sound}\n`).join('');
}

function copyText(text: string, field: HTMLTextAreaElement | null) {
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).then(() => ok('Copied'), () => fail('Copy failed', 'select the text and copy it'));
    return;
  }
  // navigator.clipboard needs HTTPS or localhost; the controller is usually plain http on the LAN.
  field?.select();
  if (document.execCommand('copy')) ok('Copied'); else fail('Copy failed', 'select the text and copy it');
}

export function PersonalitiesTab({ boards }: { boards: Board[] }) {
  const droids = useMemo(() => boards.filter((b) => b.role === 'droid'), [boards]);
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const [startGroup, setStartGroup] = useState<number | string>(0);
  const [endGroup, setEndGroup] = useState<number | string>(9);
  const [startSound, setStartSound] = useState<number | string>(0);
  const [clips, setClips] = useState<Clip[]>(loadClips);
  const [phase, setPhase] = useState<Phase>('idle');
  const [pos, setPos] = useState({ group: 0, sound: 0 });
  const [measured, setMeasured] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const t0 = useRef(0);
  const yamlField = useRef<HTMLTextAreaElement>(null);

  const selected = droids.find((b) => b.device_id === deviceId);
  useEffect(() => {
    if (!selected) setDeviceId((droids.find((b) => b.online) ?? droids[0])?.device_id ?? null);
  }, [droids, selected]);
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(clips)); } catch { /* storage unavailable */ }
  }, [clips]);

  const play = useCallback(async (group: number, sound: number) => {
    if (!deviceId) return false;
    try {
      await api.command(deviceId, 'play', { group, sound });
      return true;
    } catch (e) {
      fail(`Playing ${group}:${sound} failed`, e);
      return false;
    }
  }, [deviceId]);

  const probe = useCallback(async (group: number, sound: number) => {
    setPos({ group, sound });
    setPhase('playing');
    setPhase((await play(group, sound)) ? 'ask' : 'idle');
  }, [play]);

  /** Move on to the next sound, or the next group after the last sound. */
  const advance = (group: number, sound: number) => {
    if (sound >= MAX_SOUND) return nextGroup(group);
    probe(group, sound + 1);
  };
  const nextGroup = (group: number) => {
    if (group + 1 > Number(endGroup)) setPhase('done');
    else probe(group + 1, 0);
  };

  const startTiming = async () => {
    setPhase('playing');
    if (await play(pos.group, pos.sound)) {
      t0.current = performance.now();   // the clock starts once the board has the command
      setElapsed(0);
      setPhase('timing');
    } else {
      setPhase('ready');
    }
  };

  const stopTiming = useCallback(() => {
    setMeasured(Math.round(performance.now() - t0.current));
    setPhase('review');
  }, []);

  useEffect(() => {
    if (phase !== 'timing') return;
    const tick = setInterval(() => setElapsed(Math.round(performance.now() - t0.current)), 50);
    const key = (e: KeyboardEvent) => {
      if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); stopTiming(); }
    };
    window.addEventListener('keydown', key);
    return () => { clearInterval(tick); window.removeEventListener('keydown', key); };
  }, [phase, stopTiming]);

  const save = () => {
    const clip = { group: pos.group, sound: pos.sound, ms: measured };
    setClips((cs) => [...cs.filter((c) => c.group !== clip.group || c.sound !== clip.sound), clip]
      .sort((a, b) => a.group - b.group || a.sound - b.sound));
    advance(pos.group, pos.sound);
  };

  const start = () => {
    const g = Math.max(0, Math.min(255, Number(startGroup) || 0));
    const s = Math.max(0, Math.min(MAX_SOUND, Number(startSound) || 0));
    probe(g, s);
  };

  const yaml = toYaml(clips);
  const running = phase !== 'idle' && phase !== 'done';
  const busy = phase === 'playing';
  const label = `group ${pos.group}, sound ${pos.sound}`;

  return (
    <Stack gap="md" maw={900}>
      <Alert color="yellow">
        Plays every sound on the droid's personality chip, group by group, and times each one by hand.
        Sounds are played through the droid itself. Run it where the droid can be heard.
      </Alert>

      <Card withBorder>
        <Stack gap="sm">
          <Title order={5}>Droid</Title>
          {droids.length === 0 ? (
            <Text c="dimmed" size="sm">No droid boards found.</Text>
          ) : (
            <Group align="flex-end" wrap="wrap">
              <Select label="Droid" style={{ minWidth: 220 }} allowDeselect={false} disabled={running}
                data={droids.map((b) => ({ value: b.device_id, label: b.name + (b.online ? '' : ' (offline)') }))}
                value={deviceId} onChange={setDeviceId} />
              <NumberInput label="First group" w={110} min={0} max={255} value={startGroup} onChange={setStartGroup} disabled={running} />
              <NumberInput label="First sound" w={110} min={0} max={MAX_SOUND} value={startSound} onChange={setStartSound} disabled={running} />
              <NumberInput label="Last group" w={110} min={0} max={255} value={endGroup} onChange={setEndGroup} disabled={running} />
              <Button onClick={start} disabled={!selected?.online || running}>
                {phase === 'done' ? 'Start again' : 'Start'}
              </Button>
              {running && <Button variant="default" onClick={() => setPhase('idle')} disabled={busy}>Stop</Button>}
            </Group>
          )}
          {selected && !selected.online && <Alert color="gray">That droid's board is offline.</Alert>}
        </Stack>
      </Card>

      {phase !== 'idle' && (
        <Card withBorder>
          <Stack gap="sm">
            <Group justify="space-between">
              <Title order={5}>Now: {label}</Title>
              {busy && <Badge color="blue">sending…</Badge>}
            </Group>

            {phase === 'done' && <Text>Finished: no more groups to try.</Text>}

            {phase === 'ask' && (<>
              <Text>Did a sound play?</Text>
              <Group>
                <Button onClick={() => setPhase('ready')}>Yes</Button>
                <Button color="red" variant="light" onClick={() => nextGroup(pos.group)}>
                  No (end of group {pos.group})
                </Button>
                <Button variant="default" onClick={() => probe(pos.group, pos.sound)}>Play again</Button>
                <Button variant="subtle" onClick={() => advance(pos.group, pos.sound)}>Skip this sound</Button>
              </Group>
            </>)}

            {phase === 'ready' && (<>
              <Text>
                <b>Start timing</b> plays the sound again. Click <b>Sound ended</b> (or press Space/Enter) the
                moment it finishes.
              </Text>
              <Group>
                <Button onClick={startTiming}>Start timing</Button>
                <Button variant="subtle" onClick={() => advance(pos.group, pos.sound)}>Skip this sound</Button>
              </Group>
            </>)}

            {phase === 'timing' && (<>
              <Text size="xl" fw={700} ff="monospace">{(elapsed / 1000).toFixed(1)} s</Text>
              <Group>
                <Button size="lg" color="green" autoFocus onClick={stopTiming}>Sound ended</Button>
              </Group>
            </>)}

            {phase === 'review' && (<>
              <Text>{label} played for <b>{measured} ms</b>. Save it?</Text>
              <Group>
                <Button onClick={save}>Save</Button>
                <Button variant="light" onClick={() => setPhase('ready')}>Measure again</Button>
                <Button variant="subtle" onClick={() => advance(pos.group, pos.sound)}>Discard</Button>
              </Group>
            </>)}
          </Stack>
        </Card>
      )}

      <Card withBorder>
        <Stack gap="sm">
          <Group justify="space-between">
            <Title order={5}>Personality YAML ({clips.length} sounds)</Title>
            <Group gap="xs">
              <Button size="xs" variant="light" onClick={() => copyText(yaml, yamlField.current)}
                disabled={!clips.length}>Copy</Button>
              <Button size="xs" variant="subtle" color="red" disabled={!clips.length || running}
                onClick={() => { if (window.confirm('Discard all recorded timings?')) setClips([]); }}>Clear</Button>
            </Group>
          </Group>
          <Textarea ref={yamlField} readOnly autosize minRows={6} maxRows={24} value={yaml}
            styles={{ input: { fontFamily: 'monospace' } }} onFocus={(e) => e.currentTarget.select()} />
          <Text size="xs" c="dimmed">
            Copy this into a file such as config/personalities/&lt;name&gt;.yml. It is kept in this browser until
            cleared.
          </Text>
        </Stack>
      </Card>
    </Stack>
  );
}
