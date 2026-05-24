import type { ChannelProtocol } from '../llmProviderTemplates';
import type { LLMCapabilityCheck, LLMCapabilityCheckResult } from '../../../types/systemConfig';

// === UI option constants (from original LLMChannelEditor.tsx) ===

export const PROTOCOL_OPTIONS: Array<{ value: ChannelProtocol; label: string }> = [
  { value: 'openai', label: 'OpenAI Compatible' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'gemini', label: 'Gemini' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'vertex_ai', label: 'Vertex AI' },
  { value: 'ollama', label: 'Ollama' },
];

export const RUNTIME_CAPABILITY_OPTIONS: Array<{ value: LLMCapabilityCheck; label: string; hint: string }> = [
  { value: 'json', label: 'JSON', hint: '检测 response_format JSON 输出是否可用。' },
  { value: 'tools', label: 'Tools', hint: '检测 function/tool calling 是否可用。' },
  { value: 'stream', label: 'Stream', hint: '检测流式输出是否能返回有效 chunk。' },
  { value: 'vision', label: 'Vision', hint: '检测当前模型是否接受 image_url 输入。' },
];

export const CAPABILITY_STATUS_LABELS: Record<LLMCapabilityCheckResult['status'], string> = {
  passed: '通过',
  failed: '失败',
  skipped: '跳过',
};

// === Interfaces ===

export interface ChannelConfig {
  id: string;
  name: string;
  protocol: ChannelProtocol;
  baseUrl: string;
  apiKey: string;
  models: string;
  enabled: boolean;
}

export interface ChannelTestState {
  status: 'idle' | 'loading' | 'success' | 'error';
  text?: string;
  hint?: string;
}

export interface ChannelDiscoveryState {
  status: 'idle' | 'loading' | 'success' | 'error';
  text?: string;
  hint?: string;
  models: string[];
}

export interface ChannelCapabilityState {
  selected: LLMCapabilityCheck[];
  status: 'idle' | 'loading' | 'success' | 'error';
  text?: string;
  hint?: string;
  results: Partial<Record<LLMCapabilityCheck, LLMCapabilityCheckResult>>;
}

export interface RuntimeConfig {
  primaryModel: string;
  agentPrimaryModel: string;
  fallbackModels: string[];
  visionModel: string;
  temperature: string;
}

export interface LLMChannelEditorProps {
  items: Array<{ key: string; value: string }>;
  configVersion: string;
  maskToken: string;
  onSaved: (updatedItems: Array<{ key: string; value: string }>) => void | Promise<void>;
  disabled?: boolean;
}

export interface ChannelRowProps {
  channel: ChannelConfig;
  index: number;
  busy: boolean;
  visibleKey: boolean;
  expanded: boolean;
  testState?: ChannelTestState;
  discoveryState?: ChannelDiscoveryState;
  capabilityState?: ChannelCapabilityState;
  onUpdate: (index: number, field: keyof ChannelConfig, value: string | boolean) => void;
  onRemove: (index: number) => void;
  onToggleExpand: (index: number) => void;
  onToggleKeyVisibility: (index: number, nextVisible: boolean) => void;
  onTest: (channel: ChannelConfig, index: number) => void;
  onDiscoverModels: (channel: ChannelConfig) => void;
  onToggleCapability: (channel: ChannelConfig, capability: LLMCapabilityCheck) => void;
  onCheckCapabilities: (channel: ChannelConfig) => void;
}

export interface ParsedModelRef {
  name: string;
  provider: string;
  hasProvider: boolean;
}
