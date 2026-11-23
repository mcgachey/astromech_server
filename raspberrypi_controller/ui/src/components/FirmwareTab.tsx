import { Alert, Badge, Button, Card, Group, Stack, Table, Text, Title, Tooltip } from '@mantine/core';
import { useState } from 'react';

import { Board, FirmwareImage, api } from '../api';
import { usePoll } from '../hooks';
import { fail, ok } from '../notify';

const ROLES = [
  { role: 'droid', title: 'Droid controller' },
  { role: 'beacon', title: 'Beacon' },
] as const;

const kb = (n: number) => `${Math.round(n / 1024)} KB`;

function ImageRow({ image, boards }: { image: FirmwareImage; boards: Board[] }) {
  const running = boards.filter(
    (b) => b.role === image.role && b.online && b.info?.firmware_version === image.version);
  return (
    <Table.Tr>
      <Table.Td fw={500}>{image.version}</Table.Td>
      <Table.Td><Text size="sm" ff="monospace">{image.build_id || '–'}</Text></Table.Td>
      <Table.Td>{image.created ? new Date(image.created).toLocaleString() : '–'}</Table.Td>
      <Table.Td>{kb(image.size)}</Table.Td>
      <Table.Td>
        {image.valid ? <Badge color="green" variant="light">valid</Badge> : (
          <Tooltip label={image.error} multiline w={300}>
            <Badge color="red" variant="light">invalid</Badge>
          </Tooltip>
        )}
      </Table.Td>
      <Table.Td>
        {running.length ? running.map((b) => b.name).join(', ') : <Text size="sm" c="dimmed">–</Text>}
      </Table.Td>
    </Table.Tr>
  );
}

export function FirmwareTab({ boards }: { boards: Board[] }) {
  const { data, error, refresh } = usePoll(api.firmware, 15000);
  const [scanning, setScanning] = useState(false);

  const scan = async () => {
    setScanning(true);
    try {
      const r = await api.scanFirmware();
      await refresh();
      ok('Firmware scanned', `${r.images.length} image${r.images.length === 1 ? '' : 's'} found`);
    } catch (e) {
      fail('Firmware scan failed', e);
    }
    setScanning(false);
  };

  const images = data?.images ?? [];
  return (
    <Stack>
      <Group justify="space-between">
        <Title order={4}>Firmware images</Title>
        <Group gap="xs">
          {data?.scanned_at && (
            <Text size="xs" c="dimmed">scanned {new Date(data.scanned_at * 1000).toLocaleTimeString()}</Text>
          )}
          <Button size="xs" variant="light" loading={scanning} onClick={scan}>Scan for new firmware</Button>
        </Group>
      </Group>
      {error && <Alert color="red">{error.message}</Alert>}
      <Text size="sm" c="dimmed">
        Images are built on the build machine and copied here with <code>make install</code> (in
        <code> esp32/</code>). Open a board's tab to install one on that board.
      </Text>
      {ROLES.map(({ role, title }) => {
        const list = images.filter((i) => i.role === role);
        return (
          <Card withBorder key={role}>
            <Title order={5} mb="xs">{title}</Title>
            {list.length === 0 ? (
              <Text size="sm" c="dimmed">No {role} firmware installed.</Text>
            ) : (
              <Table.ScrollContainer minWidth={520}>
                <Table verticalSpacing="xs">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Version</Table.Th><Table.Th>Build</Table.Th><Table.Th>Created</Table.Th>
                      <Table.Th>Size</Table.Th><Table.Th>Status</Table.Th><Table.Th>Running on</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {list.map((i) => <ImageRow key={i.version} image={i} boards={boards} />)}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            )}
          </Card>
        );
      })}
    </Stack>
  );
}
