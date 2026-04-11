/**
 * Frontend mirror of the backend's error taxonomy (error_translator.py).
 *
 * Backend returns `error: { code, title, message, next_action }` on the
 * LLM status payload. This module provides typed access plus helpers
 * for rendering the error and dispatching the follow-up action.
 */

export type AiErrorCode =
  | 'invalid_key'
  | 'quota_exceeded'
  | 'rate_limited'
  | 'proxy_expired'
  | 'network'
  | 'provider_down'
  | 'model_not_found'
  | 'ollama_not_running'
  | 'unknown';

export type NextActionKind =
  | 'reconnect'
  | 'switch_provider'
  | 'retry'
  | 'open_quick_start'
  | 'open_settings'
  | 'open_diagnostic'
  | 'open_search';

export interface NextAction {
  kind: NextActionKind;
  label: string;
  provider?: string;
}

export interface TranslatedError {
  code: AiErrorCode;
  title: string;
  message: string;
  next_action: NextAction;
}

/** Icon hint per error code (renders as emoji or icon color). */
export const ERROR_VARIANTS: Record<AiErrorCode, 'warning' | 'error' | 'info'> = {
  invalid_key: 'error',
  quota_exceeded: 'warning',
  rate_limited: 'info',
  proxy_expired: 'warning',
  network: 'warning',
  provider_down: 'warning',
  model_not_found: 'error',
  ollama_not_running: 'warning',
  unknown: 'warning',
};
