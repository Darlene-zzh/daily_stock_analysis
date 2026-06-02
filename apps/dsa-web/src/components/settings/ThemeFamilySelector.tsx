import type React from 'react';
import { cn } from '../../utils/cn';
import { THEME_FAMILIES, type ThemeFamily } from '../theme/familyTheme';
import { useThemeFamily } from '../theme/useThemeFamily';

const META: Record<ThemeFamily, { label: string; desc: string; swatch: string }> = {
  premium: { label: '高级', desc: '墨·钢蓝·香槟金，沉稳专业', swatch: 'linear-gradient(135deg,#1e2533,#5b7a99 60%,#b08d57)' },
  cute: { label: '可爱', desc: '草莓奶昔粉，柔和甜美', swatch: 'linear-gradient(135deg,#ff7eb6,#ffd9e8)' },
  minimal: { label: '简约', desc: '纯黑白灰，克制留白', swatch: 'linear-gradient(135deg,#171717,#fafafa)' },
  classic: { label: '经典', desc: '青色科技玻璃拟态', swatch: 'linear-gradient(135deg,#00d4ff,#00a8cc)' },
};

export const ThemeFamilySelector: React.FC = () => {
  const { family, setFamily } = useThemeFamily();
  return (
    <div role="radiogroup" aria-label="主题风格" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {THEME_FAMILIES.map((f) => {
        const selected = f === family;
        return (
          <button
            key={f}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={META[f].label}
            onClick={() => setFamily(f)}
            className={cn(
              'flex flex-col gap-2 rounded-xl border p-3 text-left transition-all',
              selected ? 'border-accent-brand ring-2 ring-accent-brand/40' : 'border-border/70 hover:border-border'
            )}
          >
            <span className="h-12 w-full rounded-lg" style={{ background: META[f].swatch }} />
            <span className="text-sm font-semibold text-foreground">{META[f].label}</span>
            <span className="text-xs text-muted-text">{META[f].desc}</span>
          </button>
        );
      })}
    </div>
  );
};
