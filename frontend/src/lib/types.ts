export interface Session {
  session_id: string;
  original_filename: string;
  source_format: string;
  created_at: string;
  row_count: number;
  col_count: number;
}

export interface CellOutput {
  output_type: "stream" | "execute_result" | "display_data" | "error";
  text?: string;
  data?: Record<string, string>;
  ename?: string;
  evalue?: string;
  traceback?: string[];
}

export interface Cell {
  id: string;
  cell_type: "code" | "markdown";
  source: string;
  outputs: CellOutput[];
  execution_count: number | null;
  baselineOutputs?: CellOutput[];
  executing?: boolean;
  error?: string | null;
  thinking?: string | null;
}

export interface StorySection {
  phase: string;
  title: string;
  content: string;
  plots: string[];
  insights: InsightCard[];
  cell_ids?: string[];
}

export interface InsightCard {
  type: string;
  description: string;
  phase: string;
  rule: number;
  confidence?: number;
  mini_chart?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "agent";
  content: string;
  type: "text" | "cell_ref" | "action";
  cell_id?: string;
  timestamp: string;
}

export interface Version {
  version_id: number;
  trigger: string;
  timestamp: string;
}
