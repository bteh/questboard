import { createClient } from '@supabase/supabase-js';
import { devHostedAuth } from '@/lib/dev-hosted-auth';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || '';
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || '';

export const hostedMode = import.meta.env.VITE_HOSTED_MODE === 'true';

export const supabase = hostedMode && !devHostedAuth && supabaseUrl && supabaseAnonKey
  ? createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    })
  : null;
