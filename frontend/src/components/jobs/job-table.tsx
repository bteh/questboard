import { useMemo } from 'react';
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { ExternalLink } from 'lucide-react';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Progress } from '@/components/ui/progress';
import { RecommendationBadge } from '@/components/badges/recommendation-badge';
import { StatusBadge } from '@/components/badges/status-badge';
import { CompanyTypeBadge } from '@/components/badges/company-type-badge';
import { WorkTypeBadge } from '@/components/badges/work-type-badge';
import { resolveSourceLabel } from '@/hooks/use-scrapers';
import { formatDate } from '@/utils/format';
import type { ApplicationResponse } from '@/types/application';

interface JobTableProps {
  data: ApplicationResponse[];
  onRowClick?: (app: ApplicationResponse) => void;
}

const columnHelper = createColumnHelper<ApplicationResponse>();

export function JobTable({ data, onRowClick }: JobTableProps) {
  const columns = useMemo(() => [
    columnHelper.accessor('company', {
      header: 'Company',
      cell: (info) => <span className="font-medium text-text-primary">{info.getValue()}</span>,
    }),
    columnHelper.accessor('job_title', {
      header: 'Title',
      cell: (info) => <span className="text-text-secondary truncate max-w-[200px] block">{info.getValue()}</span>,
    }),
    columnHelper.accessor('company_type', {
      header: 'Type',
      cell: (info) => <CompanyTypeBadge companyType={info.getValue()} />,
    }),
    columnHelper.accessor('overall_score', {
      header: 'Score',
      cell: (info) => {
        const score = info.getValue();
        if (score == null) return <span className="text-text-muted">—</span>;
        return (
          <div className="flex items-center gap-2">
            <Progress value={score} className="w-16 h-1.5" />
            <span className="text-xs font-medium w-6">{Math.round(score)}</span>
          </div>
        );
      },
    }),
    columnHelper.accessor('recommendation', {
      header: 'Match',
      cell: (info) => <RecommendationBadge recommendation={info.getValue()} />,
    }),
    columnHelper.accessor('status', {
      header: 'Status',
      cell: (info) => <StatusBadge status={info.getValue()} />,
    }),
    columnHelper.accessor('work_type', {
      header: 'Work Type',
      cell: (info) => <WorkTypeBadge workType={info.getValue()} isRemote={info.row.original.is_remote} />,
    }),
    columnHelper.accessor('source', {
      header: 'Source',
      cell: (info) => <span className="text-xs text-text-tertiary">{resolveSourceLabel(info.getValue())}</span>,
    }),
    columnHelper.accessor('date_found', {
      header: 'Found',
      cell: (info) => <span className="text-xs text-text-muted">{formatDate(info.getValue(), 'short')}</span>,
    }),
    columnHelper.accessor('job_url', {
      header: '',
      cell: (info) => {
        const url = info.getValue();
        if (!url) return null;
        return (
          <a href={url} target="_blank" rel="noopener noreferrer" className="text-brand hover:text-brand-hover" onClick={(e) => e.stopPropagation()}>
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        );
      },
    }),
  ], []);

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="rounded-lg border border-border-default overflow-hidden">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <TableHead key={header.id} className="text-xs font-medium text-text-tertiary">
                  {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.map((row) => (
            <TableRow
              key={row.id}
              className="cursor-pointer hover:bg-bg-subtle"
              onClick={() => onRowClick?.(row.original)}
            >
              {row.getVisibleCells().map((cell) => (
                <TableCell key={cell.id} className="text-sm py-2.5">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
