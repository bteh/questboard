import { describe, expect, it } from 'vitest';

import { PROPOSE_ROLES_PROMPT, canRunHeadless, panelState, pickAssistant, suggestButtonLabel } from './suggest-roles-logic';

const claude = { id: 'claude', name: 'Claude Code', installed: true, connected: true, restart_required: false };
const codexOff = { id: 'codex', name: 'Codex', installed: true, connected: false, restart_required: false };
const desktop = { id: 'claude_desktop', name: 'Claude Desktop', installed: true, connected: true, restart_required: false };

describe('panelState', () => {
  it('is hidden on the web, where no headless run exists', () => {
    expect(panelState({ desktop: false, clients: [claude], resumeExists: true })).toBe('hidden');
  });

  it('asks to connect an assistant before anything else', () => {
    expect(panelState({ desktop: true, clients: [codexOff], resumeExists: true })).toBe('connect');
  });

  it('asks for a resume once an assistant is connected', () => {
    expect(panelState({ desktop: true, clients: [claude], resumeExists: false })).toBe('resume');
  });

  it('is ready with a connected assistant and a resume', () => {
    expect(panelState({ desktop: true, clients: [claude], resumeExists: true })).toBe('ready');
  });
});

describe('pickAssistant', () => {
  it('uses the first connected assistant, not merely an installed one', () => {
    expect(pickAssistant([codexOff, claude])?.id).toBe('claude');
    expect(pickAssistant([codexOff])).toBeNull();
  });
});

describe('suggestButtonLabel', () => {
  it('names the assistant and says what the click does', () => {
    expect(suggestButtonLabel({ assistantName: 'Claude Code', consentGranted: true, running: false })).toBe(
      'Suggest roles and keywords from my resume with Claude Code',
    );
  });

  it('says the click also grants resume access when it does', () => {
    expect(suggestButtonLabel({ assistantName: 'Claude Code', consentGranted: false, running: false })).toBe(
      'Allow resume access and suggest roles and keywords',
    );
  });

  it('shows who it is waiting on while running', () => {
    expect(suggestButtonLabel({ assistantName: 'Codex', consentGranted: true, running: true })).toBe('Asking Codex…');
  });
});

describe('Claude Desktop', () => {
  it('is picked when it is the only connected assistant, but cannot run headless', () => {
    const picked = pickAssistant([desktop, codexOff]);
    expect(picked?.id).toBe('claude_desktop');
    expect(canRunHeadless(picked!)).toBe(false);
  });

  it('loses to Claude Code when both are connected, since that one runs in-app', () => {
    expect(pickAssistant([desktop, claude])?.id).toBe('claude');
  });

  it('gets a paste prompt that proposes and never saves', () => {
    expect(PROPOSE_ROLES_PROMPT).toContain('propose_career_preferences');
    expect(PROPOSE_ROLES_PROMPT).toContain('Do not save anything');
    expect(PROPOSE_ROLES_PROMPT).toContain('breaking in');
  });
});
