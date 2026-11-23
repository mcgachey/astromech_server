import { Button, Card, Checkbox, Group, NumberInput, SegmentedControl, Select, Stack, Text,
  TextInput, Title } from '@mantine/core';
import { useEffect, useRef, useState } from 'react';
import { api, Board, BoardState } from '../api';
import { fail, ok } from '../notify';

interface Props {
  board: Board;
  state?: BoardState;
  onDone: () => void;
}

/**
 * Calls `apply` whenever the board's values (`key`) change, unless the form has unsaved edits
 * (`dirty`). After a save the next poll brings the new values, which then refill the form.
 */
function useResync(key: string | undefined, dirty: boolean, apply: () => void) {
  const last = useRef<string>();
  const applyRef = useRef(apply);
  applyRef.current = apply;
  useEffect(() => {
    if (key === undefined || key === last.current) return;
    if (last.current !== undefined && dirty) return;
    last.current = key;
    applyRef.current();
  }, [key, dirty]);
}

const MAC = /^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$/;

function DroidConfig({ board, state, onDone }: Props) {
  const cfg = state?.config;
  const [alias, setAlias] = useState('');
  const [address, setAddress] = useState('');
  const [type, setType] = useState('r2');
  const [personality, setPersonality] = useState<string | null>(null);
  const [reboot, setReboot] = useState(true);
  const [saving, setSaving] = useState(false);

  // Follow the board's saved config, but never overwrite edits that haven't been saved yet.
  const key = cfg ? JSON.stringify([cfg.alias, cfg.address, cfg.type, cfg.personality]) : undefined;
  const dirty = !!cfg && (alias !== (cfg.alias ?? '') || address !== (cfg.address ?? '')
    || type !== (cfg.type ?? 'r2') || personality !== (cfg.personality ?? null));
  useResync(key, dirty, () => {
    setAlias(cfg!.alias ?? '');
    setAddress(cfg!.address ?? '');
    setType(cfg!.type ?? 'r2');
    setPersonality(cfg!.personality ?? null);
  });

  const addressOk = address === '' || MAC.test(address);
  const save = async () => {
    setSaving(true);
    try {
      await api.configure(board.device_id, { alias, address, type, personality, reboot });
      ok('Saved', reboot ? 'Board is rebooting.' : 'Takes effect after the next reboot.');
    } catch (e) { fail('Could not save', e); }
    setSaving(false);
    onDone();
  };

  return (
    <Stack gap="xs">
      <TextInput label="Droid alias" maxLength={32} value={alias} onChange={(e) => setAlias(e.currentTarget.value)} />
      <TextInput label="Droid BLE address" placeholder="AA:BB:CC:DD:EE:FF" value={address}
        error={addressOk ? undefined : 'Expected AA:BB:CC:DD:EE:FF'}
        onChange={(e) => setAddress(e.currentTarget.value.trim().toUpperCase())} />
      <div>
        <Text size="sm" fw={500} mb={4}>Type</Text>
        <SegmentedControl value={type} onChange={setType} data={[
          { label: 'R-series (r2)', value: 'r2' }, { label: 'BB unit', value: 'bb' }]} />
      </div>
      <Select label="Personality" data={cfg?.available_personalities ?? []} value={personality}
        onChange={setPersonality} searchable />
      <Checkbox label="Reboot the board to apply" checked={reboot} onChange={(e) => setReboot(e.currentTarget.checked)} />
      <Group>
        <Button onClick={save} loading={saving} disabled={!board.online || !addressOk || !address}>
          Save to board
        </Button>
      </Group>
    </Stack>
  );
}

function BeaconConfig({ board, state, onDone }: Props) {
  const status = state?.status;
  const [kind, setKind] = useState('silent');
  const [locationId, setLocationId] = useState<number | string>(0);
  const [persist, setPersist] = useState(true);
  const [saving, setSaving] = useState(false);

  const boardKind = status?.kind ?? 'silent';
  const boardLoc = status?.location_id ?? state?.config.location_id ?? 0;
  const key = status ? JSON.stringify([boardKind, boardLoc]) : undefined;
  const dirty = !!status && (kind !== boardKind || Number(locationId) !== Number(boardLoc));
  useResync(key, dirty, () => { setKind(boardKind); setLocationId(boardLoc); });

  const save = async () => {
    setSaving(true);
    try {
      await api.configure(board.device_id, { kind, location_id: locationId, persist });
      ok('Beacon updated');
    } catch (e) { fail('Could not save', e); }
    setSaving(false);
    onDone();
  };

  return (
    <Stack gap="xs">
      <div>
        <Text size="sm" fw={500} mb={4}>Beacon type</Text>
        <SegmentedControl value={kind} onChange={setKind} data={[
          { label: 'Silent (keep awake)', value: 'silent' }, { label: 'Location', value: 'location' }]} />
      </div>
      {kind === 'location' && (
        <NumberInput label="Location ID" min={0} max={255} allowDecimal={false} value={locationId}
          onChange={setLocationId} />
      )}
      <Checkbox label="Save for next power-on" checked={persist} onChange={(e) => setPersist(e.currentTarget.checked)} />
      <Group>
        <Button onClick={save} loading={saving} disabled={!board.online}>Apply</Button>
      </Group>
    </Stack>
  );
}

function BoardSettings({ board, onDone }: { board: Board; onDone: () => void }) {
  const [name, setName] = useState(board.name);
  const [notes, setNotes] = useState(board.notes);
  const [demo, setDemo] = useState<number | string>(board.demo_sound);
  const [saving, setSaving] = useState(false);
  const dirty = name !== board.name || notes !== board.notes || Number(demo) !== board.demo_sound;

  const save = async () => {
    setSaving(true);
    try {
      await api.update(board.device_id, { name, notes, demo_sound: Number(demo) || 0 });
      ok('Saved');
    } catch (e) { fail('Could not save', e); }
    setSaving(false);
    onDone();
  };

  const forget = async () => {
    if (!window.confirm(`Forget ${board.name}? Its stored log is deleted. A connected board reappears on the next scan.`)) return;
    try { await api.forget(board.device_id); } catch (e) { fail('Could not forget board', e); }
    onDone();
  };

  return (
    <Stack gap="xs">
      <TextInput label="Name" maxLength={40} value={name} onChange={(e) => setName(e.currentTarget.value)} />
      {board.role === 'droid' && (
        <NumberInput label="Demo sound (used by POST /demo and as the default beep)" min={0} allowDecimal={false}
          value={demo} onChange={setDemo} />
      )}
      <TextInput label="Notes" value={notes} onChange={(e) => setNotes(e.currentTarget.value)} />
      <Group>
        <Button onClick={save} loading={saving} disabled={!dirty || !name.trim()}>Save</Button>
        <Button variant="subtle" color="red" onClick={forget}>Forget board</Button>
      </Group>
    </Stack>
  );
}

export function Config(props: Props) {
  const { board } = props;
  return (
    <Stack>
      <Card withBorder>
        <Stack gap="xs">
          <Title order={5}>Configuration</Title>
          <Text size="xs" c="dimmed">Saved on the board (NVS).</Text>
          {board.role === 'droid' ? <DroidConfig {...props} /> : <BeaconConfig {...props} />}
        </Stack>
      </Card>
      <Card withBorder>
        <Stack gap="xs">
          <Title order={5}>Controller settings</Title>
          <Text size="xs" c="dimmed">Saved on the controller, not the board.</Text>
          <BoardSettings board={board} onDone={props.onDone} />
        </Stack>
      </Card>
    </Stack>
  );
}
