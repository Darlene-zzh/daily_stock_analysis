import type React from 'react';
import { Button } from '../../common/Button';
import type { ChannelConfig, ChannelTestState } from './types';
import { splitModels } from './utils';

interface ChannelTestPanelProps {
  channel: ChannelConfig;
  index: number;
  busy: boolean;
  testState?: ChannelTestState;
  onTest: (channel: ChannelConfig, index: number) => void;
}

export const ChannelTestPanel: React.FC<ChannelTestPanelProps> = ({
  channel,
  index,
  busy,
  testState,
  onTest,
}) => {
  const selectedModels = splitModels(channel.models);

  return (
    <div className="flex items-center gap-2 pt-1">
      <Button
        type="button"
        variant="settings-secondary"
        size="sm"
        className="px-3 text-[11px] shadow-none"
        disabled={busy}
        onClick={() => onTest(channel, index)}
      >
        {testState?.status === 'loading' ? '测试中...' : '测试连接'}
      </Button>
      {testState?.text ? (
        <div className="space-y-1">
          <span className={`block text-xs ${
            testState.status === 'success'
              ? 'text-success'
              : testState.status === 'error'
                ? 'text-danger'
                : 'text-muted-text'
          }`}
          >
            {testState.text}
          </span>
          {selectedModels[0] ? (
            <p className="text-[11px] text-secondary-text">
              基础连接测试默认使用模型列表首项：{selectedModels[0]}
            </p>
          ) : null}
          {testState.hint ? (
            <p className="text-[11px] text-secondary-text">
              {testState.hint}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};
