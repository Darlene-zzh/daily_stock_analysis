/**
 * Investment Committee persona display strings.
 *
 * SOURCE OF TRUTH: `src/agent/agents/master_personas/__init__.py` (`PERSONA_DISPLAY`).
 * This file MUST stay byte-equivalent (display_en / display_zh / avatar_initials /
 * avatar_color) with the Python registry. When backend persona strings change,
 * update this mirror in the same PR.
 *
 * Product safety rule (spec §7): the UI never claims to channel the real person.
 * All copy uses the "inspired lens" framing — e.g. "Buffett-inspired value lens".
 */

import type { CommitteePersonaId } from '../types/analysis';

export interface PersonaDisplay {
  /** English "inspired lens" name (first-line title). */
  displayEn: string;
  /** Chinese parenthetical used on first mention in zh mode. */
  displayZh: string;
  /** Two-letter avatar initials (WB / MB / CW / NT). */
  avatarInitials: string;
  /**
   * Avatar background colour (locked decision §13 #2): WB amber / MB red /
   * CW indigo / NT slate. Hex matches the Python source so the Markdown
   * renderer, push notification, and Web UI all show the same palette.
   */
  avatarColor: string;
}

export const PERSONA_DISPLAY: Record<CommitteePersonaId, PersonaDisplay> = {
  warren_buffett: {
    displayEn: 'Buffett-inspired value lens',
    displayZh: '巴菲特式价值视角',
    avatarInitials: 'WB',
    avatarColor: '#D97706', // amber-600
  },
  michael_burry: {
    displayEn: 'Burry-inspired contrarian lens',
    displayZh: 'Burry 式逆向视角',
    avatarInitials: 'MB',
    avatarColor: '#B91C1C', // red-700
  },
  cathie_wood: {
    displayEn: 'Cathie Wood-inspired innovation lens',
    displayZh: 'Cathie Wood 式创新成长视角',
    avatarInitials: 'CW',
    avatarColor: '#4338CA', // indigo-700
  },
  nassim_taleb: {
    displayEn: 'Taleb-inspired tail-risk lens',
    displayZh: 'Taleb 式尾部风险视角',
    avatarInitials: 'NT',
    avatarColor: '#475569', // slate-600
  },
};

/** Deterministic display order — matches `DEFAULT_PERSONA_ORDER` in Python. */
export const DEFAULT_PERSONA_ORDER: CommitteePersonaId[] = [
  'warren_buffett',
  'michael_burry',
  'cathie_wood',
  'nassim_taleb',
];

/**
 * Get a persona's display info, falling back to an "unknown lens" placeholder
 * if the backend returns a persona id we don't recognise (e.g. forward-compat
 * during a deploy window).
 */
export const getPersonaDisplay = (
  persona: CommitteePersonaId | string | undefined,
): PersonaDisplay | null => {
  if (!persona) return null;
  return PERSONA_DISPLAY[persona as CommitteePersonaId] ?? null;
};
