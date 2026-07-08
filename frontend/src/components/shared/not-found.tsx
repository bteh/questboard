import { TextLink } from '@questboard/ui';

/* The 404, in voice and bare: no shell, one door back in. The plain href
   is deliberate; a full navigation to /board passes the app layout's
   beforeLoad, which counts the visit as entered. */
export function NotFoundPage() {
  return (
    <div
      className="qb-page"
      style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        padding: '0 24px',
      }}
    >
      <div style={{ textAlign: 'center' }}>
        <h1
          style={{
            fontFamily: 'var(--serif)',
            fontVariationSettings: "'opsz' 80",
            fontWeight: 560,
            fontSize: 33,
            letterSpacing: '-.012em',
            margin: '0 0 14px',
            textWrap: 'balance',
          }}
        >
          That page is not on the board.
        </h1>
        <TextLink href="/board">Go to the board</TextLink>
      </div>
    </div>
  );
}
