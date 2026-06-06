export function Info({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return <div className="info-item"><span>{label}</span><strong className={mono ? 'mono' : ''}>{value}</strong></div>;
}
