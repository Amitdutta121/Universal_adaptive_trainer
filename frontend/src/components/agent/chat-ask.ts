import { createContext, useContext } from "react";

/**
 * Sends a message as the professor would. Provided by the course chat (`agent-panel.tsx`), so a
 * card rendered inside the chat can ask for a follow-up without importing the panel.
 */
export const ChatAskContext = createContext<((question: string) => void) | null>(null);

export function useChatAsk(): ((question: string) => void) | null {
  return useContext(ChatAskContext);
}
