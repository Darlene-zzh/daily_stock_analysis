// @vitest-environment node

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { beforeEach, describe, expect, it } from 'vitest';

describe('index.html theme bootstrap', () => {
  let scriptSrc: string;

  beforeEach(() => {
    const indexHtml = readFileSync(resolve(__dirname, '..', 'index.html'), 'utf8');
    // Extract the inline <script> block from <head>
    const match = /<script>([\s\S]*?)<\/script>/.exec(indexHtml);
    if (!match) throw new Error('No inline script found in index.html');
    scriptSrc = match[1];
  });

  it('reads light/dark mode from localStorage and defaults to dark', () => {
    expect(scriptSrc).toContain("localStorage.getItem('theme')");
    expect(scriptSrc).toContain("storedTheme === 'light' || storedTheme === 'dark' ? storedTheme : 'dark'");
    expect(scriptSrc).toContain("root.classList.remove('light', 'dark')");
    expect(scriptSrc).toContain('root.classList.add(theme)');
    expect(scriptSrc).toContain('root.style.colorScheme = theme');
  });

  it('reads theme family from localStorage and defaults to premium', () => {
    expect(scriptSrc).toContain("localStorage.getItem('dsa-theme-family')");
    expect(scriptSrc).toContain("'classic', 'cute', 'minimal', 'premium'");
    expect(scriptSrc).toContain("'premium'");
    expect(scriptSrc).toContain("root.setAttribute('data-theme', family)");
  });

  it('applies dark class and premium data-theme when localStorage is empty', () => {
    // Simulate the script in a minimal DOM-like environment using Function constructor
    const root = {
      _classes: new Set<string>(),
      _dataTheme: '',
      _colorScheme: '',
      classList: {
        _self: null as unknown as typeof root,
        remove(...names: string[]) { names.forEach(n => root._classes.delete(n)); },
        add(...names: string[]) { names.forEach(n => root._classes.add(n)); },
      },
      get style() { return { set colorScheme(v: string) { root._colorScheme = v; } }; },
      setAttribute(attr: string, val: string) { if (attr === 'data-theme') root._dataTheme = val; },
    };

    const localStorage = { getItem: (() => null) as (key: string) => null };
    const fn = new Function('document', 'localStorage', `
      const documentElement = document.documentElement;
      ${scriptSrc.replace(/document\.documentElement/g, 'documentElement')}
    `);
    fn({ documentElement: root }, localStorage);

    expect(root._classes.has('dark')).toBe(true);
    expect(root._classes.has('light')).toBe(false);
    expect(root._colorScheme).toBe('dark');
    expect(root._dataTheme).toBe('premium');
  });

  it('applies light class when localStorage theme is light', () => {
    const root = {
      _classes: new Set<string>(),
      _dataTheme: '',
      _colorScheme: '',
      classList: {
        remove(...names: string[]) { names.forEach(n => root._classes.delete(n)); },
        add(...names: string[]) { names.forEach(n => root._classes.add(n)); },
      },
      get style() { return { set colorScheme(v: string) { root._colorScheme = v; } }; },
      setAttribute(attr: string, val: string) { if (attr === 'data-theme') root._dataTheme = val; },
    };

    const storage: Record<string, string> = { theme: 'light' };
    const localStorage = { getItem: (k: string) => storage[k] ?? null };
    const fn = new Function('document', 'localStorage', `
      const documentElement = document.documentElement;
      ${scriptSrc.replace(/document\.documentElement/g, 'documentElement')}
    `);
    fn({ documentElement: root }, localStorage);

    expect(root._classes.has('light')).toBe(true);
    expect(root._classes.has('dark')).toBe(false);
    expect(root._colorScheme).toBe('light');
    expect(root._dataTheme).toBe('premium');
  });

  it('applies stored family when it is a valid value', () => {
    const root = {
      _classes: new Set<string>(),
      _dataTheme: '',
      _colorScheme: '',
      classList: {
        remove(...names: string[]) { names.forEach(n => root._classes.delete(n)); },
        add(...names: string[]) { names.forEach(n => root._classes.add(n)); },
      },
      get style() { return { set colorScheme(v: string) { root._colorScheme = v; } }; },
      setAttribute(attr: string, val: string) { if (attr === 'data-theme') root._dataTheme = val; },
    };

    const storage: Record<string, string> = { 'dsa-theme-family': 'cute' };
    const localStorage = { getItem: (k: string) => storage[k] ?? null };
    const fn = new Function('document', 'localStorage', `
      const documentElement = document.documentElement;
      ${scriptSrc.replace(/document\.documentElement/g, 'documentElement')}
    `);
    fn({ documentElement: root }, localStorage);

    expect(root._dataTheme).toBe('cute');
    expect(root._classes.has('dark')).toBe(true);
  });

  it('falls back to premium for an unrecognised family value', () => {
    const root = {
      _classes: new Set<string>(),
      _dataTheme: '',
      _colorScheme: '',
      classList: {
        remove(...names: string[]) { names.forEach(n => root._classes.delete(n)); },
        add(...names: string[]) { names.forEach(n => root._classes.add(n)); },
      },
      get style() { return { set colorScheme(v: string) { root._colorScheme = v; } }; },
      setAttribute(attr: string, val: string) { if (attr === 'data-theme') root._dataTheme = val; },
    };

    const storage: Record<string, string> = { 'dsa-theme-family': 'unknown-theme' };
    const localStorage = { getItem: (k: string) => storage[k] ?? null };
    const fn = new Function('document', 'localStorage', `
      const documentElement = document.documentElement;
      ${scriptSrc.replace(/document\.documentElement/g, 'documentElement')}
    `);
    fn({ documentElement: root }, localStorage);

    expect(root._dataTheme).toBe('premium');
  });
});
