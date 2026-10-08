import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { addWatchedPage, getWatchedPages, removeWatchedPage } from '@/api/watched-pages';

const WATCHED_PAGES_KEY = ['watched-pages'] as const;

export function useWatchedPages() {
  return useQuery({ queryKey: WATCHED_PAGES_KEY, queryFn: getWatchedPages });
}

export function useAddWatchedPage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (url: string) => addWatchedPage(url),
    onSuccess: (data) => queryClient.setQueryData(WATCHED_PAGES_KEY, data),
  });
}

export function useRemoveWatchedPage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => removeWatchedPage(id),
    onSuccess: (data) => queryClient.setQueryData(WATCHED_PAGES_KEY, data),
  });
}
