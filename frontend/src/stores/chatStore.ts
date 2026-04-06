"use client";
import { create } from "zustand";
import type { ChatMessage } from "@/lib/types";
import { v4 as uuidv4 } from "uuid";

interface ChatState {
  messages: ChatMessage[];
  isTyping: boolean;
  addUserMessage: (content: string) => string;
  addAgentMessage: (content: string, type?: "text" | "cell_ref" | "action", cellId?: string) => void;
  setTyping: (typing: boolean) => void;
  clear: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  isTyping: false,
  addUserMessage: (content) => {
    const id = uuidv4();
    const msg: ChatMessage = { id, role: "user", content, type: "text", timestamp: new Date().toISOString() };
    set((s) => ({ messages: [...s.messages, msg] }));
    return id;
  },
  addAgentMessage: (content, type = "text", cellId) => {
    const msg: ChatMessage = { id: uuidv4(), role: "agent", content, type, cell_id: cellId, timestamp: new Date().toISOString() };
    set((s) => ({ messages: [...s.messages, msg], isTyping: false }));
  },
  setTyping: (isTyping) => set({ isTyping }),
  clear: () => set({ messages: [], isTyping: false }),
}));
