import { Wifi } from 'lucide-react';
import { ColorBadge } from './color-badge';

export function RemoteBadge() {
  return (
    <ColorBadge bg="#E3EDE7" text="#3F6B54" darkBg="#25382E" darkText="#8FC2A4">
      <Wifi className="h-3 w-3" />
      Remote
    </ColorBadge>
  );
}
