import { Wifi } from 'lucide-react';
import { ColorBadge } from './color-badge';

export function RemoteBadge() {
  return (
    <ColorBadge bg="#E0E7FF" text="#3730A3" darkBg="#312E81" darkText="#A5B4FC">
      <Wifi className="h-3 w-3" />
      Remote
    </ColorBadge>
  );
}
