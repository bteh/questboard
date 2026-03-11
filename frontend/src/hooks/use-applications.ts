import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getApplications, getApplication, createApplication, updateApplication, updateApplicationStatus, deleteApplication, deduplicateApplications } from '@/api/applications';
import type { ApplicationFilters, ApplicationCreate, ApplicationUpdate, StatusUpdate, ApplicationResponse, ApplicationListResponse } from '@/types/application';

export function useApplications(filters: ApplicationFilters = {}) {
  return useQuery({
    queryKey: ['applications', filters],
    queryFn: () => getApplications(filters),
  });
}

export function useApplication(id: number) {
  return useQuery({
    queryKey: ['applications', id],
    queryFn: () => getApplication(id),
    enabled: id > 0,
  });
}

export function useCreateApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ApplicationCreate) => createApplication(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['applications'] });
      queryClient.invalidateQueries({ queryKey: ['analytics'] });
    },
  });
}

export function useUpdateApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: ApplicationUpdate }) => updateApplication(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['applications'] });
    },
  });
}

export function useUpdateStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: StatusUpdate }) => updateApplicationStatus(id, data),
    onMutate: async ({ id, data }) => {
      await queryClient.cancelQueries({ queryKey: ['applications'] });
      const previousLists = queryClient.getQueriesData<ApplicationListResponse>({ queryKey: ['applications'] });
      queryClient.setQueriesData<ApplicationListResponse>(
        { queryKey: ['applications'] },
        (old) => {
          if (!old) return old;
          return {
            ...old,
            items: old.items.map((item: ApplicationResponse) =>
              item.id === id ? { ...item, status: data.status } : item
            ),
          };
        }
      );
      return { previousLists };
    },
    onError: (_err, _vars, context) => {
      if (context?.previousLists) {
        context.previousLists.forEach(([key, data]) => {
          queryClient.setQueryData(key, data);
        });
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['applications'] });
      queryClient.invalidateQueries({ queryKey: ['analytics'] });
    },
  });
}

export function useDeleteApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteApplication(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['applications'] });
      queryClient.invalidateQueries({ queryKey: ['analytics'] });
    },
  });
}

export function useDeduplicateApplications() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (profile?: string) => deduplicateApplications(profile),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['applications'] });
      queryClient.invalidateQueries({ queryKey: ['analytics'] });
    },
  });
}
