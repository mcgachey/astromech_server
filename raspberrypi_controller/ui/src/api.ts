export interface BoardInfo {
  role: 'droid' | 'beacon';
  firmware_version: string;
  protocol: number;
  device_id: string;
  uptime_ms: number;
  build: string;
}

export interface FirmwareFile {
  name: string;
  offset: string;
  size: number;
}

export interface FirmwareImage {
  role: 'droid' | 'beacon';
  version: string;
  build_id: string;
  created: string;
  size: number;
  valid: boolean;
  error: string;
  files: FirmwareFile[];
}

export interface FlashStatus {
  version: string;
  stage: 'starting' | 'releasing port' | 'writing' | 'restarting' | 'done' | 'failed';
  active: boolean;
  percent: number;
  error: string | null;
  started: number;
  finished: number | null;
}

export interface FirmwareList {
  images: FirmwareImage[];
  scanned_at: number | null;
}

export interface BoardFirmware {
  role: 'droid' | 'beacon';
  running: { version: string; build: string } | null;
  flash: FlashStatus | null;
  images: FirmwareImage[];
}

export interface Board {
  device_id: string;
  role: 'droid' | 'beacon';
  name: string;
  notes: string;
  demo_sound: number;
  port?: string;
  first_seen?: number;
  last_seen?: number;
  online: boolean;
  info?: BoardInfo;
  error?: string;
  flash?: FlashStatus;
  ha_entity: string;
  ha_enabled: boolean;
  ha_status?: { state: 'on' | 'off'; ok: boolean; ts: number; error: string | null } | null;
}

export interface HaSettings {
  enabled: boolean;
  url: string;
  token_set: boolean;
  verify_tls: boolean;
  interval: number;
  timeout: number;
}

export interface HaSettingsUpdate extends Partial<Omit<HaSettings, 'token_set'>> {
  token?: string;
  clear_token?: boolean;
}

export interface BluetoothDevice {
  name: string;
  address: string;
  rssi: number | null;
  droid: boolean;
}

export interface BluetoothScan {
  devices: BluetoothDevice[];
  scanned_at: number;
}

export interface Sound {
  index: number;
  group: number;
  sound: number;
  ms: number;
}

export interface BoardState {
  status: Record<string, any>;
  config: Record<string, any>;
  sounds?: Sound[];
}

export interface LogEntry {
  seq: number;
  ts: number;
  kind: 'system' | 'event' | 'log' | 'command' | 'response' | 'error';
  level: 'info' | 'warning' | 'error';
  message: string;
  data?: unknown;
}

export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch('/api' + path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(data.error ?? 'error', data.message ?? res.statusText, res.status);
  return data as T;
}

const id = encodeURIComponent;

export const api = {
  boards: () => request<Board[]>('GET', '/boards'),
  ha: () => request<HaSettings>('GET', '/home_assistant'),
  saveHa: (f: HaSettingsUpdate) => request<HaSettings>('PUT', '/home_assistant', f),
  testHa: (f: HaSettingsUpdate) =>
    request<{ ok: true; location_name?: string; version?: string }>('POST', '/home_assistant/test', f),
  sendHa: (d: string) =>
    request<{ ok: true; entity: string; state: 'on' | 'off' }>('POST', `/boards/${id(d)}/home_assistant/send`),
  scan: () => request<Board[]>('POST', '/boards/scan'),
  update: (d: string, fields: Partial<Pick<Board, 'name' | 'notes' | 'demo_sound' | 'ha_entity' | 'ha_enabled'>>) =>
    request<Board>('PATCH', `/boards/${id(d)}`, fields),
  forget: (d: string) => request<{ ok: true }>('DELETE', `/boards/${id(d)}`),
  state: (d: string) => request<BoardState>('GET', `/boards/${id(d)}/state`),
  configure: (d: string, body: Record<string, unknown>) =>
    request<Record<string, any>>('PUT', `/boards/${id(d)}/config`, body),
  command: (d: string, cmd: string, args: Record<string, unknown> = {}) =>
    request<Record<string, any>>('POST', `/boards/${id(d)}/commands/${cmd}`, args),
  logs: (d: string, since: number) =>
    request<{ entries: LogEntry[]; last_seq: number }>('GET', `/boards/${id(d)}/logs?since=${since}`),
  scanBluetooth: (all = false, timeout = 5) =>
    request<BluetoothScan>('POST', '/bluetooth/scan', { all, timeout }),
  firmware: () => request<FirmwareList>('GET', '/firmware'),
  scanFirmware: () => request<FirmwareList>('POST', '/firmware/scan'),
  boardFirmware: (d: string) => request<BoardFirmware>('GET', `/boards/${id(d)}/firmware`),
  flash: (d: string, version: string) => request<FlashStatus>('POST', `/boards/${id(d)}/firmware`, { version }),
  clearLogs: (d: string) => request<{ ok: true }>('DELETE', `/boards/${id(d)}/logs`),
};
