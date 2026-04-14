export type Store = "googleplay" | "appstore";

export interface FeedbackItem {
  id: number;
  original: string;
  summary: string;
  category: string;
  priority: "High" | "Medium" | "Low";
  priority_reason: string;
  sentiment: "Positive" | "Neutral" | "Negative";
}

export interface Correction {
  id: number;
  field: string;
  old_value: string;
  new_value: string;
  reason: string;
}

export type ActionType = "bug" | "performance" | "feature" | "ux" | "pricing" | "other";

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
  feedbacks: string[];
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
}

export type AnalysisStep =
  | { type: "idle" }
  | { type: "scraping" }
  | { type: "categorization"; estimatedMs?: number; startedAt?: number; nFeedbacks?: number; scrapedCount?: number }
  | { type: "report" }
  | { type: "done"; result: AnalysisResult }
  | { type: "error"; message: string };

export interface AppEntry {
  id: number;
  name: string;
  category: string;
}
