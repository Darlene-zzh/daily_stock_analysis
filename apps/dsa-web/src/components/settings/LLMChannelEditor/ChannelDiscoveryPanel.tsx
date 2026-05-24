import type React from 'react';
import { Button } from '../../common/Button';
import { Input } from '../../common/Input';
import {
  MODEL_PLACEHOLDERS_BY_PROTOCOL,
  getProviderTemplate,
} from '../llmProviderTemplates';
import type { ChannelConfig, ChannelDiscoveryState } from './types';
import {
  areModelsEquivalent,
  splitModels,
  toggleModelSelection,
} from './utils';

interface ChannelDiscoveryPanelProps {
  channel: ChannelConfig;
  index: number;
  busy: boolean;
  discoveryState?: ChannelDiscoveryState;
  onDiscoverModels: (channel: ChannelConfig) => void;
  onUpdate: (index: number, field: keyof ChannelConfig, value: string | boolean) => void;
}

export const ChannelDiscoveryPanel: React.FC<ChannelDiscoveryPanelProps> = ({
  channel,
  index,
  busy,
  discoveryState,
  onDiscoverModels,
  onUpdate,
}) => {
  const preset = getProviderTemplate(channel.name);
  const selectedModels = splitModels(channel.models);
  const discoveredModels = discoveryState?.models || [];
  const manualOnlyModels = selectedModels.filter(
    (model) => !discoveredModels.some((discoveredModel) => areModelsEquivalent(model, discoveredModel, channel.protocol)),
  );

  return (
    <div className="space-y-3 rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface-hover)] p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="settings-secondary"
          size="sm"
          className="px-3 text-[11px] shadow-none"
          disabled={busy}
          onClick={() => onDiscoverModels(channel)}
        >
          {discoveryState?.status === 'loading' ? '获取中...' : '获取模型'}
        </Button>
        <span className={`text-xs ${
          discoveryState?.status === 'success'
            ? 'text-success'
            : discoveryState?.status === 'error'
              ? 'text-danger'
              : 'text-muted-text'
        }`}
        >
          {discoveryState?.text || '支持 `/models` 的 OpenAI Compatible 渠道可自动拉取模型。'}
        </span>
      </div>
      {discoveryState?.hint ? (
        <p className="text-[11px] text-secondary-text">
          {discoveryState.hint}
        </p>
      ) : null}

      {discoveredModels.length > 0 ? (
        <fieldset className="m-0 border-0 p-0">
          <legend className="mb-2 block text-sm font-medium text-foreground">可选模型（可多选）</legend>
          <div className="max-h-48 space-y-2 overflow-y-auto rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface)] p-3">
            {discoveredModels.map((model) => (
              <label key={model} className="flex items-center gap-2 text-sm text-secondary-text">
                <input
                  type="checkbox"
                  checked={selectedModels.some((selectedModel) => (
                    areModelsEquivalent(selectedModel, model, channel.protocol)
                  ))}
                  disabled={busy}
                  onChange={() => onUpdate(index, 'models', toggleModelSelection(channel.models, model, channel.protocol))}
                  className="settings-input-checkbox size-4 rounded border-border/70 bg-base"
                />
                <span>{model}</span>
              </label>
            ))}
          </div>
        </fieldset>
      ) : null}

      <Input
        label={discoveredModels.length > 0 ? '手动模型（逗号分隔）' : '模型（逗号分隔）'}
        value={channel.models}
        disabled={busy}
        onChange={(e) => onUpdate(index, 'models', e.target.value)}
        placeholder={preset?.placeholderModels || MODEL_PLACEHOLDERS_BY_PROTOCOL[channel.protocol]}
        hint={
          discoveredModels.length > 0
            ? '如有自定义模型名未出现在列表中，可继续手动补充，保存格式仍为逗号分隔。'
            : '若渠道不支持自动发现或请求失败，可直接手动填写模型列表。'
        }
      />

      {manualOnlyModels.length > 0 ? (
        <p className="text-[11px] text-secondary-text">
          额外手动模型：{manualOnlyModels.join('，')}
        </p>
      ) : null}
    </div>
  );
};
