import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getWatchlist, addWatchlistCompany, removeWatchlistCompany } from '@/api/watchlist';
import { useProfile } from '@/contexts/profile-context';

export function useWatchlist() {
  const { profile } = useProfile();
  return useQuery({
    queryKey: ['watchlist', profile],
    queryFn: () => getWatchlist(profile),
  });
}

export function useAddCompany() {
  const { profile } = useProfile();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => addWatchlistCompany(profile, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist', profile] });
    },
  });
}

export function useRemoveCompany() {
  const { profile } = useProfile();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => removeWatchlistCompany(profile, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist', profile] });
    },
  });
}
