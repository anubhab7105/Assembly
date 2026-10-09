'use client'

import { createClient } from '@/lib/supabase/client'
import { useRouter } from 'next/navigation'
import { LogOut } from 'lucide-react'
import { env } from '@/lib/env'

export function SignOutButton() {
  const router = useRouter()
  const supabase = createClient()

  const handleSignOut = async () => {
    if (env.NEXT_PUBLIC_APP_MODE === 'web') {
      await supabase.auth.signOut()
    }
    router.push('/login')
    router.refresh()
  }

  // Only show logout in web mode
  if (env.NEXT_PUBLIC_APP_MODE !== 'web') {
    return null
  }

  return (
    <button
      onClick={handleSignOut}
      className="flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:text-white transition-colors rounded-md hover:bg-white/5"
    >
      <LogOut size={16} />
      <span>Sign out</span>
    </button>
  )
}
