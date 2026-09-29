import { NativeSelect as CarbonNativeSelect } from "@/components/ui/native-select";
import type { ReactNode, SelectHTMLAttributes } from 'react';
import { useTranslation } from 'react-i18next';
export function useRoutingText() {
  const { i18n } = useTranslation();
  return (zh: string, en: string) => i18n.language.startsWith('zh') ? zh : en;
}
export function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="grid min-w-0 gap-2 text-sm"><span className="font-medium">{label}</span>{children}</label>;
}
export function NativeSelect(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <CarbonNativeSelect {...props} />;
}
export const percent = (bps: number) => `${(bps / 100).toFixed(2).replace(/\.00$/, '')}%`;
export const share = (count: number, total: number) => total > 0 ? `${(count / total * 100).toFixed(2)}%` : '—';
