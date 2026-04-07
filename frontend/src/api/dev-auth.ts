import { apiGet, apiPost } from '@/lib/api-client';
import type { DevHostedLoginResponse, DevHostedPersona, DevHostedRegisterResponse } from '@/types/workspace';

export function getDevHostedPersonas(): Promise<DevHostedPersona[]> {
  return apiGet<DevHostedPersona[]>('/dev/auth/personas');
}

export function signInAsDevHostedPersona(personaId: string, reset = false): Promise<DevHostedLoginResponse> {
  return apiPost<DevHostedLoginResponse>('/dev/auth/login', {
    persona_id: personaId,
    reset,
  });
}

export function registerDevHostedAccount(email: string, fullName: string, reset = false): Promise<DevHostedRegisterResponse> {
  return apiPost<DevHostedRegisterResponse>('/dev/auth/register', {
    email,
    full_name: fullName,
    reset,
  });
}
