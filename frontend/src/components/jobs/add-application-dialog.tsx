import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { useCreateApplication } from '@/hooks/use-applications';
import { useProfile } from '@/contexts/profile-context';
import { toast } from 'sonner';
import { useState } from 'react';

const schema = z.object({
  job_title: z.string().min(1, 'Title is required'),
  company: z.string().min(1, 'Company is required'),
  location: z.string().optional(),
  job_url: z.string().optional(),
  description: z.string().optional(),
  is_remote: z.boolean().optional(),
  notes: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

export function AddApplicationDialog() {
  const [open, setOpen] = useState(false);
  const { profile } = useProfile();
  const createApp = useCreateApplication();

  const { register, handleSubmit, reset, formState: { errors }, setValue, watch } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { is_remote: false },
  });

  const isRemote = watch('is_remote');

  const onSubmit = (data: FormValues) => {
    createApp.mutate(
      { ...data, profile, source: 'manual' },
      {
        onSuccess: () => {
          toast.success('Application added');
          reset();
          setOpen(false);
        },
        onError: () => toast.error('Failed to add application'),
      }
    );
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" />}>
        <Plus className="h-4 w-4 mr-1" />
        Add Application
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Application</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <Label htmlFor="job_title">Job Title *</Label>
            <Input id="job_title" {...register('job_title')} placeholder="e.g. Senior Software Engineer" aria-invalid={!!errors.job_title} className={errors.job_title ? 'border-danger' : ''} />
            {errors.job_title && <p className="text-xs text-danger mt-1" role="alert">{errors.job_title.message}</p>}
          </div>
          <div>
            <Label htmlFor="company">Company *</Label>
            <Input id="company" {...register('company')} placeholder="e.g. Anthropic" aria-invalid={!!errors.company} className={errors.company ? 'border-danger' : ''} />
            {errors.company && <p className="text-xs text-danger mt-1" role="alert">{errors.company.message}</p>}
          </div>
          <div>
            <Label htmlFor="location">Location</Label>
            <Input id="location" {...register('location')} placeholder="e.g. San Francisco, CA" />
          </div>
          <div>
            <Label htmlFor="job_url">Job URL</Label>
            <Input id="job_url" {...register('job_url')} placeholder="https://..." />
          </div>
          <div>
            <Label htmlFor="description">Description</Label>
            <Textarea id="description" {...register('description')} rows={3} />
          </div>
          <div className="flex items-center gap-2">
            <Checkbox
              id="is_remote"
              checked={isRemote}
              onCheckedChange={(checked) => setValue('is_remote', !!checked)}
            />
            <Label htmlFor="is_remote" className="text-sm font-normal">Remote position</Label>
          </div>
          <div>
            <Label htmlFor="notes">Notes</Label>
            <Textarea id="notes" {...register('notes')} rows={2} />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={createApp.isPending}>
              {createApp.isPending ? 'Adding...' : 'Add'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
