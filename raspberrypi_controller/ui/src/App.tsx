import { ActionIcon, AppShell, Badge, Button, Center, Group, Loader, Stack, Tabs, Text, Title,
  useMantineColorScheme } from '@mantine/core';
import { lazy, Suspense, useEffect, useState } from 'react';

import { api, Board } from './api';
import { BluetoothTab } from './components/BluetoothTab';
import { BoardTab } from './components/BoardTab';
import { FirmwareTab } from './components/FirmwareTab';
import { HomeAssistantTab } from './components/HomeAssistantTab';
import { PersonalitiesTab } from './components/PersonalitiesTab';
import { usePoll } from './hooks';
import { fail } from './notify';

const HA_TAB = 'home_assistant';
// Swagger UI is large: load it only when the API tab is opened.
const ApiDocsTab = lazy(() => import('./components/ApiDocsTab').then((m) => ({ default: m.ApiDocsTab })));
const API_TAB = 'api';
const PERS_TAB = 'personalities';
const FW_TAB = 'firmware';
const BT_TAB = 'bluetooth';
const isExtra = (v: string | null) => v === HA_TAB || v === API_TAB || v === PERS_TAB || v === FW_TAB || v === BT_TAB;
const ROLE_COLOR = { droid: 'blue', beacon: 'grape' } as const;

function ThemeToggle() {
  const { colorScheme, setColorScheme } = useMantineColorScheme();
  return (
    <ActionIcon variant="default" aria-label="Toggle color scheme"
      onClick={() => setColorScheme(colorScheme === 'dark' ? 'light' : 'dark')}>
      {colorScheme === 'dark' ? '☀' : '☾'}
    </ActionIcon>
  );
}

export function App() {
  const { data: boards, error, loading, refresh } = usePoll(api.boards, 4000);
  const [scanning, setScanning] = useState(false);
  const [active, setActive] = useState<string | null>(null);

  // Remember the tab; fall back to the first board if it is gone.
  useEffect(() => {
    if (!boards?.length) return;
    if (isExtra(active)) return;
    if (!active || !boards.some((b) => b.device_id === active)) {
      let saved: string | null = null;
      try { saved = localStorage.getItem('activeBoard'); } catch { /* storage unavailable */ }
      setActive(boards.find((b) => b.device_id === saved)?.device_id ?? boards[0].device_id);
    }
  }, [boards, active]);

  const select = (v: string | null) => {
    setActive(v);
    try { if (v && !isExtra(v)) localStorage.setItem('activeBoard', v); } catch { /* ignore */ }
  };

  const scan = async () => {
    setScanning(true);
    try { await api.scan(); await refresh(); } catch (e) { fail('Scan failed', e); }
    setScanning(false);
  };

  return (
    <AppShell header={{ height: 56 }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Title order={3}>Astromech Controller</Title>
          <Group>
            {error && <Badge color="red">controller unreachable</Badge>}
            <Button variant="light" size="xs" loading={scanning} onClick={scan}>Scan for boards</Button>
            <ThemeToggle />
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Main>
        {loading && <Center h={200}><Loader /></Center>}
        {!loading && boards?.length === 0 && !isExtra(active) && (
          <Stack align="center" mt="xl">
            <Text c="dimmed">No boards found. Plug in an ESP32 board and scan; boards are also
              rediscovered automatically every few seconds.</Text>
            <Button onClick={scan} loading={scanning}>Scan for boards</Button>
            <Button variant="subtle" onClick={() => select(HA_TAB)}>Home Assistant settings</Button>
            <Button variant="subtle" onClick={() => select(API_TAB)}>API docs</Button>
            <Button variant="subtle" onClick={() => select(PERS_TAB)}>Personalities</Button>
            <Button variant="subtle" onClick={() => select(FW_TAB)}>Firmware</Button>
            <Button variant="subtle" onClick={() => select(BT_TAB)}>Bluetooth</Button>
          </Stack>
        )}
        {((boards && boards.length > 0) || isExtra(active)) && active && (
          <Tabs value={active} onChange={select} keepMounted={false}>
            <Tabs.List style={{ flexWrap: 'wrap' }}>
              {(boards ?? []).map((b: Board) => (
                <Tabs.Tab key={b.device_id} value={b.device_id}
                  leftSection={<Badge size="xs" circle color={b.online ? 'green' : 'gray'} />}
                  rightSection={<Badge size="xs" variant="light" color={ROLE_COLOR[b.role]}>{b.role}</Badge>}>
                  {b.name}
                </Tabs.Tab>
              ))}
              <Tabs.Tab value={FW_TAB} ml="auto">Firmware</Tabs.Tab>
              <Tabs.Tab value={BT_TAB}>Bluetooth</Tabs.Tab>
              <Tabs.Tab value={HA_TAB}>Home Assistant</Tabs.Tab>
              <Tabs.Tab value={API_TAB}>API</Tabs.Tab>
              <Tabs.Tab value={PERS_TAB}>Personalities</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value={FW_TAB} pt="md"><FirmwareTab boards={boards ?? []} /></Tabs.Panel>
            <Tabs.Panel value={BT_TAB} pt="md"><BluetoothTab /></Tabs.Panel>
            <Tabs.Panel value={HA_TAB} pt="md"><HomeAssistantTab /></Tabs.Panel>
            <Tabs.Panel value={API_TAB} pt="md"><Suspense fallback={<Loader />}><ApiDocsTab /></Suspense></Tabs.Panel>
            <Tabs.Panel value={PERS_TAB} pt="md"><PersonalitiesTab boards={boards ?? []} /></Tabs.Panel>
            {(boards ?? []).map((b: Board) => (
              <Tabs.Panel key={b.device_id} value={b.device_id} pt="md">
                <BoardTab board={b} onChanged={refresh} />
              </Tabs.Panel>
            ))}
          </Tabs>
        )}
      </AppShell.Main>
    </AppShell>
  );
}
