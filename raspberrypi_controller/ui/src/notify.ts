import { notifications } from '@mantine/notifications';

export function fail(title: string, e: unknown) {
  notifications.show({ color: 'red', title, message: e instanceof Error ? e.message : String(e) });
}

export function ok(title: string, message?: string) {
  notifications.show({ color: 'teal', title, message: message ?? '' });
}
