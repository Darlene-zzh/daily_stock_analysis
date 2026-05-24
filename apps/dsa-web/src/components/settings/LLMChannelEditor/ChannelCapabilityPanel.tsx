import type React from 'react';
import { Badge } from '../../common/Badge';
import { Button } from '../../common/Button';
import { Tooltip } from '../../common/Tooltip';
import type { LLMCapabilityCheck } from '../../../types/systemConfig';
import type { ChannelConfig, ChannelCapabilityState } from './types';
import {
  CAPABILITY_STATUS_LABELS,
  RUNTIME_CAPABILITY_OPTIONS,
} from './types';
import { getCapabilityResultVariant } from './utils';

interface ChannelCapabilityPanelProps {
  channel: ChannelConfig;
  busy: boolean;
  capabilityState?: ChannelCapabilityState;
  onToggleCapability: (channel: ChannelConfig, capability: LLMCapabilityCheck) => void;
  onCheckCapabilities: (channel: ChannelConfig) => void;
}

export const ChannelCapabilityPanel: React.FC<ChannelCapabilityPanelProps> = ({
  channel,
  busy,
  capabilityState,
  onToggleCapability,
  onCheckCapabilities,
}) => {
  const selectedCapabilities = capabilityState?.selected || [];
  const capabilityResults = capabilityState?.results || {};
  const capabilityBusy = capabilityState?.status === 'loading';

  return (
    <div className="space-y-3 rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface-hover)] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-[11px] font-medium text-muted-text">运行时能力检测（可选）</p>
          <p className="mt-0.5 text-[11px] text-secondary-text">
            仅在手动触发时发起真实 LLM 请求；多选可能需要 20-40 秒。
          </p>
        </div>
        <Button
          type="button"
          variant="settings-secondary"
          size="sm"
          className="px-3 text-[11px] shadow-none"
          disabled={busy || capabilityBusy || selectedCapabilities.length === 0}
          onClick={() => onCheckCapabilities(channel)}
        >
          {capabilityBusy ? '检测中...' : '检测能力'}
        </Button>
      </div>

      <div className="flex flex-wrap gap-2">
        {RUNTIME_CAPABILITY_OPTIONS.map((option) => (
          <Tooltip key={option.value} content={option.hint}>
            <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] px-2 py-1 text-[11px] text-secondary-text">
              <input
                type="checkbox"
                checked={selectedCapabilities.includes(option.value)}
                disabled={busy || capabilityBusy}
                onChange={() => onToggleCapability(channel, option.value)}
                className="settings-input-checkbox size-3.5 rounded border-border/70 bg-base"
              />
              <span>{option.label}</span>
            </label>
          </Tooltip>
        ))}
      </div>

      {capabilityState?.text ? (
        <div className="space-y-1">
          <p className={`text-xs ${
            capabilityState.status === 'success'
              ? 'text-success'
              : capabilityState.status === 'error'
                ? 'text-danger'
                : 'text-muted-text'
          }`}
          >
            {capabilityState.text}
          </p>
          {capabilityState.hint ? (
            <p className="text-[11px] text-secondary-text">{capabilityState.hint}</p>
          ) : null}
        </div>
      ) : null}

      {Object.keys(capabilityResults).length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {RUNTIME_CAPABILITY_OPTIONS.map((option) => {
            const result = capabilityResults[option.value];
            if (!result) return null;
            return (
              <Tooltip key={option.value} content={result.message}>
                <span className="inline-flex">
                  <Badge variant={getCapabilityResultVariant(result.status)}>
                    {option.label} {CAPABILITY_STATUS_LABELS[result.status]}
                  </Badge>
                </span>
              </Tooltip>
            );
          })}
        </div>
      ) : null}
    </div>
  );
};
