import { Alert, Badge, Button, Card, Checkbox, Group, Stack, Table, Text, Title } from '@mantine/core';
import { useState } from 'react';

import { api, BluetoothScan } from '../api';

export function BluetoothTab() {
  const [result, setResult] = useState<BluetoothScan>();
  const [showAll, setShowAll] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string>();

  const scan = async () => {
    setScanning(true);
    setError(undefined);
    try {
      setResult(await api.scanBluetooth(showAll));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setScanning(false);
  };

  const devices = result?.devices ?? [];
  return (
    <Stack>
      <Group justify="space-between">
        <Title order={4}>Bluetooth</Title>
        <Group gap="sm">
          {result && <Text size="xs" c="dimmed">scanned {new Date(result.scanned_at * 1000).toLocaleTimeString()}</Text>}
          <Checkbox size="xs" label="Show all devices" checked={showAll}
            onChange={(e) => setShowAll(e.currentTarget.checked)} />
          <Button size="xs" variant="light" loading={scanning} onClick={scan}>Scan for new droids</Button>
        </Group>
      </Group>
      <Text size="sm" c="dimmed">
        Scans with the Raspberry Pi's Bluetooth adapter for droids (devices advertising the name
        <code> DROID</code>). A scan takes about five seconds.
      </Text>
      {error && <Alert color="red">{error}</Alert>}
      <Card withBorder>
        {!result ? (
          <Text size="sm" c="dimmed">No scan yet.</Text>
        ) : devices.length === 0 ? (
          <Text size="sm" c="dimmed">No {showAll ? 'Bluetooth devices' : 'droids'} found. Make sure the droid is powered on and in range.</Text>
        ) : (
          <Table.ScrollContainer minWidth={420}>
            <Table verticalSpacing="xs">
              <Table.Thead>
                <Table.Tr><Table.Th>Name</Table.Th><Table.Th>Address</Table.Th><Table.Th>Signal</Table.Th></Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {devices.map((d) => (
                  <Table.Tr key={d.address}>
                    <Table.Td>
                      {d.name || <Text span c="dimmed">(unnamed)</Text>}{' '}
                      {d.droid && <Badge size="xs" variant="light" color="blue">droid</Badge>}
                    </Table.Td>
                    <Table.Td><Text size="sm" ff="monospace">{d.address}</Text></Table.Td>
                    <Table.Td>{d.rssi != null ? `${d.rssi} dBm` : '–'}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Card>
    </Stack>
  );
}
