import { apiGet } from '@/lib/api-client';

export interface ScraperSource {
  name: string;
  display_name: string;
  url: string;
  description: string;
  category: string;
  enabled_by_default: boolean;
}

export function getScraperSources(): Promise<ScraperSource[]> {
  return apiGet<ScraperSource[]>('/scrapers/sources');
}
