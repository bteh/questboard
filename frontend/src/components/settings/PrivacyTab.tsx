import { useState } from 'react';
import type { useNavigate } from '@tanstack/react-router';
import { Loader2, ShieldCheck, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useEraseWorkspaceData } from '@/hooks/use-workspace';
import { erasePersonalBrowserState } from '@/lib/entry';

interface PrivacyTabProps {
  navigate: ReturnType<typeof useNavigate>;
}

export function PrivacyTab({ navigate }: PrivacyTabProps) {
  const eraseData = useEraseWorkspaceData();
  const [confirmation, setConfirmation] = useState('');
  const confirmed = confirmation.trim().toUpperCase() === 'ERASE';

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldCheck className="h-4 w-4" />
            Where your data lives
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-text-secondary">
          <p>
            The desktop app keeps your resume, search preferences, job history, and assistant consent on this machine.
            They are not bundled into copies of Questboard you give to other people.
          </p>
          <p>
            If you explicitly let a connected assistant read your resume, that assistant's provider may receive it as
            tool context. Side Quests never read your resume.
          </p>
        </CardContent>
      </Card>

      <Card className="border-destructive/30">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base text-destructive">
            <Trash2 className="h-4 w-4" />
            Erase my Questboard data
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-text-secondary">
            Permanently removes your resume and extracted text, saved searches, watched companies, job and Side Quest
            history, assistant access, local caches, and database backups. The installed app, public source definitions,
            and your sign-in account remain.
          </p>

          <label className="block space-y-1.5 text-sm font-medium text-text-primary" htmlFor="erase-confirmation">
            <span>Type ERASE to confirm</span>
            <input
              id="erase-confirmation"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              autoComplete="off"
              spellCheck={false}
              className="h-10 w-full rounded-lg border border-border-default bg-background px-3 font-mono text-sm outline-none focus:border-destructive focus:ring-2 focus:ring-destructive/15"
            />
          </label>

          <Button
            type="button"
            variant="destructive"
            disabled={!confirmed || eraseData.isPending}
            onClick={() => {
              eraseData.mutate(undefined, {
                onSuccess: (result) => {
                  erasePersonalBrowserState();
                  toast.success(result.message);
                  void navigate({ to: '/start', replace: true });
                },
                onError: (error) => {
                  toast.error(error instanceof Error ? error.message : 'Could not erase your data');
                },
              });
            }}
          >
            {eraseData.isPending ? <Loader2 className="animate-spin" /> : <Trash2 />}
            {eraseData.isPending ? 'Erasing...' : 'Erase everything'}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
