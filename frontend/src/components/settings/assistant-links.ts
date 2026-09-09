/** Where to get each assistant, for the "not found on this Mac" state. */
export function installUrlFor(clientId: string): string {
  switch (clientId) {
    case 'claude_desktop':
      return 'https://claude.ai/download';
    case 'codex':
      return 'https://chatgpt.com/codex';
    default:
      return 'https://claude.ai/code';
  }
}

/** One line per assistant on what it costs the person. */
export function assistantNote(clientId: string): string {
  switch (clientId) {
    case 'claude_desktop':
      return 'The Claude app. Works on a free Claude account; you paste a prompt.';
    case 'codex':
      return 'Needs a ChatGPT plan; you paste a prompt.';
    default:
      return 'Needs a Claude Pro or Max plan; runs from inside Questboard.';
  }
}
