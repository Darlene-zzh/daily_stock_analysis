import type React from 'react';
import { useEffect, useRef, useState } from 'react';
import { Check, Monitor, Moon, Sun } from 'lucide-react';
import { useTheme } from 'next-themes';
import { cn } from '../../utils/cn';
import { Tooltip } from '../common/Tooltip';

type ThemeOption = 'light' | 'dark' | 'system';
type ThemeToggleVariant = 'default' | 'nav';

const THEME_OPTIONS: Array<{
  value: ThemeOption;
  label: string;
  icon: typeof Sun;
}> = [
  { value: 'light', label: '浅色', icon: Sun },
  { value: 'dark', label: '深色', icon: Moon },
  { value: 'system', label: '跟随系统', icon: Monitor },
];

function resolveThemeLabel(theme: string | undefined) {
  switch (theme) {
    case 'light':
      return '浅色';
    case 'dark':
      return '深色';
    default:
      return '跟随系统';
  }
}

interface ThemeToggleProps {
  variant?: ThemeToggleVariant;
  /** Accepted for API symmetry with the sidebar; the nav variant is icon-only in both states. */
  collapsed?: boolean;
}

export const ThemeToggle: React.FC<ThemeToggleProps> = ({ variant = 'default' }) => {
  const { theme, resolvedTheme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
    };
  }, [open]);

  const activeTheme = (theme as ThemeOption | undefined) ?? 'system';
  const visualTheme = resolvedTheme ?? 'dark';
  const TriggerIcon = visualTheme === 'light' ? Sun : Moon;
  const isNavVariant = variant === 'nav';

  const trigger = (
    <button
      type="button"
      onClick={() => setOpen((value) => !value)}
      data-state={open ? 'open' : 'closed'}
      className={cn(
        isNavVariant
          ? 'group relative flex size-9 select-none items-center justify-center rounded-xl text-muted-text transition-colors hover:bg-[var(--nav-hover-bg)] hover:text-foreground data-[state=open]:bg-[var(--nav-hover-bg)] data-[state=open]:text-foreground'
          : 'inline-flex h-10 items-center gap-2 rounded-xl border border-border/70 bg-card/80 px-3 text-sm text-secondary-text shadow-soft-card transition-colors hover:bg-hover hover:text-foreground'
      )}
      aria-haspopup="menu"
      aria-expanded={open}
      aria-label="切换主题"
    >
      <TriggerIcon className={cn('shrink-0', isNavVariant ? 'size-[18px]' : 'size-4')} />
      {isNavVariant ? null : (
        <span className="hidden sm:inline">{resolveThemeLabel(activeTheme)}</span>
      )}
    </button>
  );

  return (
    <div className="relative" ref={containerRef}>
      {isNavVariant ? (
        <Tooltip content="明暗模式" side="top" disabled={open}>
          {trigger}
        </Tooltip>
      ) : (
        trigger
      )}

      {open ? (
        <div
          role="menu"
          aria-label="主题模式"
          className={cn(
            'z-[100] min-w-[8rem] overflow-hidden rounded-2xl border border-border/70 bg-elevated p-1.5 shadow-[0_24px_48px_rgba(3,8,20,0.32)] backdrop-blur-xl',
            isNavVariant
              ? 'absolute bottom-full left-0 mb-2 w-max min-w-[9rem]'
              : 'absolute right-0 mt-2'
          )}
        >
          {THEME_OPTIONS.map(({ value, label, icon: Icon }) => {
            const isActive = activeTheme === value;
            return (
              <button
                key={value}
                type="button"
                role="menuitemradio"
                aria-checked={isActive}
                onClick={() => {
                  setTheme(value);
                  setOpen(false);
                }}
                className={cn(
                  'flex w-full items-center justify-between rounded-xl px-3 py-2 text-sm transition-colors',
                  isActive
                    ? 'bg-cyan/10 text-foreground'
                    : 'text-secondary-text hover:bg-hover hover:text-foreground'
                )}
              >
                <span className="flex items-center gap-2">
                  <Icon className="size-4" />
                  {label}
                </span>
                {isActive ? <Check className="size-4 text-cyan" /> : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
};
