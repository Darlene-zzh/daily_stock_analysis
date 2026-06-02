import type React from 'react';
import { useEffect, useRef, useState } from 'react';
import { Check, Palette } from 'lucide-react';
import { cn } from '../../utils/cn';
import { THEME_FAMILIES, type ThemeFamily } from './familyTheme';
import { useThemeFamily } from './useThemeFamily';

const FAMILY_LABELS: Record<ThemeFamily, string> = {
  premium: '高级',
  cute: '可爱',
  minimal: '简约',
  classic: '经典',
};

export const FamilyToggle: React.FC = () => {
  const { family, setFamily } = useThemeFamily();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="主题风格"
        className="inline-flex h-10 items-center gap-2 rounded-xl border border-border/70 bg-card/80 px-3 text-sm text-secondary-text shadow-soft-card transition-colors hover:bg-hover hover:text-foreground"
      >
        <Palette className="h-4 w-4" />
        <span>{FAMILY_LABELS[family]}</span>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-2 w-36 rounded-xl border border-border/70 bg-popover p-1 shadow-soft-card-strong"
        >
          {THEME_FAMILIES.map((f) => (
            <button
              key={f}
              type="button"
              role="menuitem"
              aria-label={FAMILY_LABELS[f]}
              onClick={() => {
                setFamily(f);
                setOpen(false);
              }}
              className={cn(
                'flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors hover:bg-hover',
                f === family ? 'text-foreground' : 'text-secondary-text'
              )}
            >
              <span>{FAMILY_LABELS[f]}</span>
              {f === family && <Check className="h-4 w-4" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
