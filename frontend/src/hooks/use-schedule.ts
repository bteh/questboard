import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getSchedule, updateSchedule } from '@/api/schedule';
import type { ScheduleUpdate } from '@/types/schedule';

export function useSchedule(profile: string) {
  return useQuery({
    queryKey: ['schedule', profile],
    queryFn: () => getSchedule(profile),
    staleTime: 30_000,
  });
}

export function useUpdateSchedule(profile: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ScheduleUpdate) => updateSchedule(body, profile),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['schedule', profile] }),
  });
}
