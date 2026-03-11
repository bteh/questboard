import { useMutation, useQueryClient } from '@tanstack/react-query';
import { prepareApplication, submitApplication } from '@/api/apply';
import type { SubmitRequest } from '@/api/apply';

export function usePrepareApplication() {
  return useMutation({
    mutationFn: (id: number) => prepareApplication(id),
  });
}

export function useSubmitApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data?: SubmitRequest }) =>
      submitApplication(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['applications'] });
      queryClient.invalidateQueries({ queryKey: ['analytics'] });
    },
  });
}
