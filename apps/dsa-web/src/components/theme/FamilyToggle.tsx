import type React from 'react';
import { useEffect, useRef, useState } from 'react';
import { Check, Palette } from 'lucide-react';
import { cn } from '../../utils/cn';
import { THEME_FAMILIES, type ThemeFamily } from './familyTheme';
import { useThemeFamily } from './useThemeFamily';

type FamilyToggleVariant = 'default' | 'nav';

const FAMILY_LABELS: Record<ThemeFamily, string> = {
  premium: '高级',
  cute: '可爱',
  minimal: '简约',
  classic: '经典',
};

interface FamilyToggleProps {
  variant?: FamilyToggleVariant;
  collapsed?: boolean;
}

export const FamilyToggle: React.FC<FamilyToggleProps> = ({
  variant = 'default',
  collapsed = false,
}) => {
  const { family, setFamily } = useThemeFamily();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);
  const isNav = variant === 'nav';

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
        data-state={open ? 'open' : 'closed'}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="主题风格"
        className={cn(
          isNav
            ? cn(
                'group relative flex h-[var(--nav-item-height)] w-full select-none items-center gap-3 border-y border-x-0 border-transparent text-sm text-secondary-text transition-all hover:bg-[var(--nav-hover-bg)] hover:text-foreground data-[state=open]:bg-[var(--nav-hover-bg)] data-[state=open]:text-foreground',
                collapsed ? 'justify-center px-0' : 'px-[var(--nav-item-padding-x)]'
              )
            : 'inline-flex h-10 items-center gap-2 rounded-xl border border-border/70 bg-card/80 px-3 text-sm text-secondary-text shadow-soft-card transition-colors hover:bg-hover hover:text-foreground'
        )}
      >
        <Palette className={cn('shrink-0', isNav ? 'ml-1 size-5' : 'size-4')} />
        {isNav ? (
          collapsed ? null : <span className="truncate">主题风格</span>
        ) : (
          <span>{FAMILY_LABELS[family]}</span>
        )}
      </button>
      {open && (
        <div
          role="menu"
          aria-label="主题风格"
          className={cn(
            'z-[100] min-w-[8rem] overflow-hidden rounded-2xl border border-border/70 bg-elevated p-1.5 shadow-[0_24px_48px_rgba(3,8,20,0.32)] backdrop-blur-xl',
            isNav ? 'absolute bottom-full left-0 mb-2 w-max min-w-[9rem]' : 'absolute right-0 mt-2'
          )}
        >
          {THEME_FAMILIES.map((f) => {
            const isActive = f === family;
            return (
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
                  'flex w-full items-center justify-between gap-6 rounded-xl px-3 py-2 text-sm transition-colors',
                  isActive ? 'bg-cyan/10 text-foreground' : 'text-secondary-text hover:bg-hover hover:text-foreground'
                )}
              >
                <span>{FAMILY_LABELS[f]}</span>
                {isActive && <Check className="size-4 text-cyan" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};
