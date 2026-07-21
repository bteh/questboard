import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getApplications,
  getApplication,
  createApplication,
  updateApplication,
  updateApplicationStatus,
  updateApplicationFeedback,
  deleteApplication,
  deduplicateApplications,
  type FeedbackUpdate,
} from '@/api/applications';
import type { ApplicationFilters, ApplicationCreate, ApplicationUpdate, StatusUpdate, ApplicationResponse, ApplicationListResponse } from '@/types/application';

export function useApplications(filters: ApplicationFilters = {}) {
  return useQuery({
    queryKey: ['applications', filters],
    queryFn: () => getApplications(filters),
  });
}

/**
 * Every query-key family that caches application lists. The log trio shares
 * ['applications', filters]; the Find Work board's career lane caches under
 * ['profile-work', filters] (board.tsx). A status edit must land in both.
 */
export const APPLICATION_LIST_KEYS = [['applications'], ['profile-work']] as const;

/**
 * Write one row's fields into EVERY cached application list at once.
 *
 * This is the shared-cache contract the log trio and the Find Work board
 * ride on: they all read list keys from the one QueryClient, so an
 * optimistic status edit made anywhere shows everywhere instantly, before
 * the server round-trip settles. Returns the touched entries so a
 * mutation's onError can roll them back.
 */
export function patchApplicationLists(
  queryClient: ReturnType<typeof useQueryClient>,
  id: number,
  patch: Partial<ApplicationResponse>,
): [readonly unknown[], ApplicationListResponse | undefined][] {
  const previousLists = APPLICATION_LIST_KEYS.flatMap((queryKey) =>
    queryClient.getQueriesData<ApplicationListResponse>({ queryKey }),
  );
  for (const queryKey of APPLICATION_LIST_KEYS) {
    queryClient.setQueriesData<ApplicationListResponse>(
      { queryKey },
      (old) => {
        if (!old || !Array.isArray(old.items)) return old;
        return {
          ...old,
          items: old.items.map((item: ApplicationResponse) =>
            item.id === id ? { ...item, ...patch } : item,
          ),
        };
      },
    );
  }
  return previousLists;
}

export function useApplication(id: number) {
  return useQuery({
    // single-record namespace: list patchers map over ['applications']-prefixed
    // entries and must never meet a record-shaped one
    queryKey: ['application', id],
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
      await queryClient.cancelQueries({ queryKey: ['profile-work'] });
      const previousLists = patchApplicationLists(queryClient, id, { status: data.status });
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
      queryClient.invalidateQueries({ queryKey: ['profile-work'] });
      queryClient.invalidateQueries({ queryKey: ['analytics'] });
    },
  });
}

/**
 * The log's status edits: mark done (optionally with the paid figure the
 * user typed, carried in quest_json), shelve, reopen. Writes through
 * PATCH /applications/{id} and patches every cached list optimistically,
 * so the Done ledger below and the full ledger page reflect the edit
 * before the request settles.
 */
export function useLogEdit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: ApplicationUpdate }) => updateApplication(id, data),
    onMutate: async ({ id, data }) => {
      await queryClient.cancelQueries({ queryKey: ['applications'] });
      await queryClient.cancelQueries({ queryKey: ['profile-work'] });
      const patch: Partial<ApplicationResponse> = {
        // The list sorts on updated_at; mirror the server's touch so the
        // optimistic row keeps its place honestly.
        updated_at: new Date().toISOString(),
      };
      if (data.status !== undefined) patch.status = data.status;
      if (data.quest_json !== undefined) {
        patch.quest_json = data.quest_json;
        try {
          patch.quest = JSON.parse(data.quest_json) as Record<string, unknown>;
        } catch {
          /* server-side validation rejects malformed JSON; leave quest as-is */
        }
      }
      const previousLists = patchApplicationLists(queryClient, id, patch);
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
      queryClient.invalidateQueries({ queryKey: ['profile-work'] });
      queryClient.invalidateQueries({ queryKey: ['analytics'] });
    },
  });
}

export function useUpdateFeedback() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: FeedbackUpdate }) => updateApplicationFeedback(id, data),
    onMutate: async ({ id, data }) => {
      await queryClient.cancelQueries({ queryKey: ['applications'] });
      const previousLists = queryClient.getQueriesData<ApplicationListResponse>({ queryKey: ['applications'] });
      queryClient.setQueriesData<ApplicationListResponse>(
        { queryKey: ['applications'] },
        (old) => {
          if (!old || !Array.isArray(old.items)) return old;
          return {
            ...old,
            items: old.items.map((item: ApplicationResponse) =>
              item.id === id ? { ...item, user_feedback: data.feedback } : item
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
