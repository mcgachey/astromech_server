import { Alert, Text } from '@mantine/core';
import { useEffect, useRef } from 'react';
// @ts-expect-error - swagger-ui-dist ships no type declarations
import SwaggerUIBundle from 'swagger-ui-dist/swagger-ui-bundle.js';
// ?raw keeps the stylesheet out of PostCSS (postcss-simple-vars chokes on its `$` text)
// @ts-ignore - vite ?raw import
import css from 'swagger-ui-dist/swagger-ui.css?raw';

export function ApiDocsTab() {
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);
    return () => { style.remove(); };
  }, []);
  useEffect(() => {
    SwaggerUIBundle({ url: '/api/openapi.json', domNode: el.current, deepLinking: false,
      docExpansion: 'list', tryItOutEnabled: true });
  }, []);
  return (
    <>
      <Alert color="yellow" mb="sm">
        <Text size="sm">Requests sent from here are real: they beep droids, reconfigure and reboot boards.</Text>
      </Alert>
      <div ref={el} className="swagger-host" />
    </>
  );
}
