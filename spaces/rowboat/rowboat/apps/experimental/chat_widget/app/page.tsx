import { Suspense } from 'react';
import { App } from './app';

export const dynamic = 'force-dynamic';

export default function Page() {
  return <Suspense>
    <App apiUrl={`${process.env.ROWBOAT_HOST}/api/widget/v1`} />
  </Suspense>
}
