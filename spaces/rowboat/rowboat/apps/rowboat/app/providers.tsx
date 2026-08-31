// app/providers.tsx
'use client'

import { HeroUIProvider } from "@heroui/react"
import { useRouter } from 'next/navigation'

export function Providers({ className, children }: { className: string, children: React.ReactNode }) {
  const router = useRouter();

  return (
    <HeroUIProvider className={className} navigate={router.push}>
      {children}
    </HeroUIProvider >
  )
}