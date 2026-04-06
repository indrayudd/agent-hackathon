import { create } from "zustand";
import type { StorySection } from "@/lib/types";

interface StoryState {
  title: string;
  executiveSummary: string;
  sections: StorySection[];
  generatedAt: string;
  loading: boolean;
  error: string | null;
  setStory: (story: {
    title: string;
    executive_summary: string;
    sections: StorySection[];
    generated_at: string;
  }) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clear: () => void;
}

export const useStoryStore = create<StoryState>((set) => ({
  title: "",
  executiveSummary: "",
  sections: [],
  generatedAt: "",
  loading: false,
  error: null,
  setStory: (story) =>
    set({
      title: story.title,
      executiveSummary: story.executive_summary,
      sections: story.sections,
      generatedAt: story.generated_at,
      loading: false,
      error: null,
    }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error, loading: false }),
  clear: () =>
    set({
      title: "",
      executiveSummary: "",
      sections: [],
      generatedAt: "",
      loading: false,
      error: null,
    }),
}));
