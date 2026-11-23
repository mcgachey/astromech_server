import { Badge, Button, Card, Group, Stack, Switch, Text, TextInput, Title } from '@mantine/core';
import { useEffect, useState } from 'react';
import { api, Board } from '../api';
import { fail, ok } from '../notify';

const ENTITY = /^[a-z_]+\.[a-z0-9_]+$/;

export function HomeAssistantSection({ board, onDone }: { board: Board; onDone: () => void }) {
  const [enabled, setEnabled] = useState(board.ha_enabled);
  const [entity, setEntity] = useState(board.ha_entity);
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const dirty = enabled !== board.ha_enabled || entity !== board.ha_entity;
  const entityOk = entity === '' || ENTITY.test(entity);
  const st = board.ha_status;

  // Follow changes made elsewhere, but not while the form has unsaved edits.
  useEffect(() => {
    if (!dirty) { setEnabled(board.ha_enabled); setEntity(board.ha_entity); }
  }, [board.ha_enabled, board.ha_entity]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    setSaving(true);
    try {
      await api.update(board.device_id, { ha_enabled: enabled, ha_entity: entity.trim() });
      ok('Saved');
    } catch (e) { fail('Could not save', e); }
    setSaving(false);
    onDone();
  };

  const sendNow = async () => {
    setSending(true);
    try {
      const r = await api.sendHa(board.device_id);
      ok('Update sent', `${r.entity} set to ${r.state}.`);
    } catch (e) { fail('Update failed', e); }
    setSending(false);
    onDone();
  };

  return (
    <Card withBorder>
      <Stack gap="xs">
        <Group justify="space-between">
          <Title order={5}>Home Assistant</Title>
          {st && (
            <Badge color={st.ok ? 'green' : 'red'} variant="light">
              {st.ok ? `sent: ${st.state}` : 'update failed'}
            </Badge>
          )}
        </Group>
        <Text size="xs" c="dimmed">
          Saved on the controller. Connection settings are on the Home Assistant tab, and must be enabled there too.
        </Text>
        <Switch label="Send availability updates for this droid" checked={enabled}
          onChange={(e) => setEnabled(e.currentTarget.checked)} />
        <TextInput label="Entity ID" placeholder="binary_sensor.r2_t2" value={entity}
          error={entityOk ? undefined : 'Expected something like binary_sensor.r2_t2'}
          onChange={(e) => setEntity(e.currentTarget.value.trim().toLowerCase())} />
        {st && !st.ok && <Text size="xs" c="red">{st.error}</Text>}
        {st?.ok && <Text size="xs" c="dimmed">Last update {new Date(st.ts * 1000).toLocaleTimeString()}.</Text>}
        <Group>
          <Button onClick={save} loading={saving}
            disabled={!dirty || !entityOk || (enabled && !entity)}>Save</Button>
          <Button variant="light" onClick={sendNow} loading={sending}
            disabled={dirty || !board.ha_entity}>Send update now</Button>
        </Group>
      </Stack>
    </Card>
  );
}
