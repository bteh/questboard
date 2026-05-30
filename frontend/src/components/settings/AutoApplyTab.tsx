import { Rocket } from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export function AutoApplyTab() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Rocket className="h-4 w-4" />
          Auto-apply
          <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-600 uppercase">Coming soon</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-text-tertiary">
          Bulk-approve applications to top-scored Greenhouse and Lever jobs after a manual review step.
        </p>
      </CardContent>
    </Card>
  );
}
