export type Store = "googleplay" | "appstore";

export interface FeedbackItem {
  id: number;
  original: string;
  summary?: string;
  category?: string;
  priority?: "High" | "Medium" | "Low";
  priority_reason?: string;
  cluster_id?: number;
  cluster_label?: string;
  actionable?: boolean;
}

export interface Correction {
  id: number;
  field: string;
  old_value: string;
  new_value: string;
  reason: string;
}

export type ActionType = "bug" | "performance" | "feature" | "ux" | "pricing" | "ai_quality" | "other";

export interface SprintFeedback {
  text: string;
  translation?: string;
}

export interface RiceScore {
  reach: number;
  impact: 1 | 2 | 3;
  confidence: number;
  effort_label: "XS" | "S" | "M" | "L" | "XL";
  effort: number;
  score: number;
}

export interface UserStoryCard {
  action: string;
  action_type: ActionType;
  feedbacks: SprintFeedback[];
  rice: RiceScore;
  // bug / performance
  what_breaks?: string;
  done_when?: string;
  // feature
  user_story?: string;
  acceptance_criteria?: string[];
  // ux / pricing / other + bug / performance
  problem?: string;
  success_metric?: string;
  next_step?: string;
}

export interface AnalysisResult {
  items: FeedbackItem[];
  corrections: Correction[];
  used_fallback: boolean;
  report: string;
  report_fallback: boolean;
  user_story_cards: UserStoryCard[];
  non_actionable_items?: string[];
}

export type AnalysisStep =
  | { type: "idle" }
  | { type: "scraping" }
  | { type: "sift"; estimatedMs?: number; startedAt?: number }
  | { type: "categorization"; estimatedMs?: number; startedAt?: number; nFeedbacks?: number; scrapedCount?: number; usedFallback?: boolean }
  | { type: "clustering"; clusterCount?: number; estimatedMs?: number; startedAt?: number }
  | { type: "report"; estimatedMs?: number; startedAt?: number }
  | { type: "stella"; estimatedMs?: number; startedAt?: number }
  | { type: "done"; result: AnalysisResult }
  | { type: "error"; message: string };

export interface AppEntry {
  id: number;
  name: string;
  category: string;
}
