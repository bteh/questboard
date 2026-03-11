import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getResumeStatus, uploadResume } from '@/api/resume';
import { useProfile } from '@/contexts/profile-context';

export function useResumeStatus() {
  const { profile } = useProfile();
  return useQuery({
    queryKey: ['resume', profile],
    queryFn: () => getResumeStatus(profile),
  });
}

export function useUploadResume() {
  const { profile } = useProfile();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => uploadResume(profile, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['resume'] });
      // Also invalidate profile preferences — the background analyzer
      // will update target_roles, keywords, and career_baseline from the new resume
      queryClient.invalidateQueries({ queryKey: ['settings', 'preferences'] });
    },
  });
}
