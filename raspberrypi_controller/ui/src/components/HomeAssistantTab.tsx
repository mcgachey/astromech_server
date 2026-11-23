import { Alert, Button, Card, Checkbox, Group, NumberInput, PasswordInput, Stack, Switch, Text,
  TextInput, Title } from '@mantine/core';
import { useEffect, useState } from 'react';
import { api, HaSettings } from '../api';
import { fail, ok } from '../notify';

export function HomeAssistantTab() {
  const [saved, setSaved] = useState<HaSettings>();
  const [enabled, setEnabled] = useState(false);
  const [url, setUrl] = useState('');
  const [token, setToken] = useState('');
  const [verifyTls, setVerifyTls] = useState(true);
  const [interval, setInterval_] = useState<number | string>(30);
  const [timeout, setTimeout_] = useState<number | string>(10);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string }>();
  const [loadError, setLoadError] = useState<string>();

  const fill = (s: HaSettings) => {
    setSaved(s);
    setEnabled(s.enabled);
    setUrl(s.url);
    setVerifyTls(s.verify_tls);
    setInterval_(s.interval);
    setTimeout_(s.timeout);
    setToken('');
  };

  useEffect(() => {
    api.ha().then(fill).catch((e) => setLoadError(e.message));
  }, []);

  const form = () => ({
    enabled, url, verify_tls: verifyTls, interval: Number(interval), timeout: Number(timeout),
    ...(token ? { token } : {}),
  });

  const save = async () => {
    setSaving(true);
    try {
      fill(await api.saveHa(form()));
      ok('Saved', 'Home Assistant settings updated.');
    } catch (e) { fail('Could not save', e); }
    setSaving(false);
  };

  const test = async () => {
    setTesting(true);
    setResult(undefined);
    try {
      const r = await api.testHa({ url, verify_tls: verifyTls, timeout: Number(timeout), ...(token ? { token } : {}) });
      const detail = [r.location_name, r.version && `version ${r.version}`].filter(Boolean).join(', ');
      setResult({ ok: true, text: 'Connected' + (detail ? ` (${detail})` : '') + '.' });
    } catch (e) {
      setResult({ ok: false, text: e instanceof Error ? e.message : String(e) });
    }
    setTesting(false);
  };

  const dirty = !!saved && (enabled !== saved.enabled || url !== saved.url || verifyTls !== saved.verify_tls
    || Number(interval) !== saved.interval || Number(timeout) !== saved.timeout || token !== '');
  const needsToken = !saved?.token_set && !token;

  return (
    <Card withBorder maw={640}>
      <Stack gap="sm">
        <Title order={4}>Home Assistant</Title>
        <Text size="sm" c="dimmed">
          When enabled, the controller posts each droid's availability (<code>on</code> when its board is
          online and the droid is connected, otherwise <code>off</code>) to the entity set on the droid's tab.
        </Text>
        {loadError && <Alert color="red">{loadError}</Alert>}
        <Switch label="Send updates to Home Assistant" checked={enabled}
          onChange={(e) => setEnabled(e.currentTarget.checked)} />
        <TextInput label="URL" placeholder="http://homeassistant.local:8123" value={url}
          onChange={(e) => setUrl(e.currentTarget.value)} />
        <PasswordInput label="Long-lived access token" autoComplete="off"
          description="Create one under your Home Assistant profile > Security. It is stored on the controller and never sent back to this page."
          placeholder={saved?.token_set ? '•••••••• (saved; leave blank to keep)' : 'paste token'}
          value={token} onChange={(e) => setToken(e.currentTarget.value)} />
        <Group grow align="flex-start">
          <NumberInput label="Resend every (seconds)" description="Changes are sent immediately." min={5} max={3600}
            allowDecimal={false} value={interval} onChange={setInterval_} />
          <NumberInput label="Request timeout (seconds)" min={1} max={60} allowDecimal={false}
            value={timeout} onChange={setTimeout_} />
        </Group>
        <Checkbox label="Verify HTTPS certificate" checked={verifyTls}
          onChange={(e) => setVerifyTls(e.currentTarget.checked)} />
        <Group>
          <Button onClick={save} loading={saving} disabled={!dirty || (enabled && (!url.trim() || needsToken))}>
            Save
          </Button>
          <Button variant="light" onClick={test} loading={testing} disabled={!url.trim() || needsToken}>
            Test connection
          </Button>
        </Group>
        {result && <Alert color={result.ok ? 'green' : 'red'}>{result.text}</Alert>}
        <Text size="xs" c="dimmed">The test uses the values in this form, saved or not.</Text>
      </Stack>
    </Card>
  );
}
