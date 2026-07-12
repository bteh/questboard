import { useMutation } from '@tanstack/react-query';
import { prepareApplication } from '@/api/apply';

export function usePrepareApplication() {
  return useMutation({
    mutationFn: (id: number) => prepareApplication(id),
  });
}
