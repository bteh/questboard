import { apiGet, apiPut } from '@/lib/api-client';
import type { ScheduleConfig, ScheduleUpdate } from '@/types/schedule';

export function getSchedule(profile: string): Promise<ScheduleConfig> {
  return apiGet<ScheduleConfig>('/schedule', { profile });
}

export function updateSchedule(body: ScheduleUpdate, profile: string): Promise<ScheduleConfig> {
  return apiPut<ScheduleConfig>(`/schedule?profile=${encodeURIComponent(profile)}`, body);
}
