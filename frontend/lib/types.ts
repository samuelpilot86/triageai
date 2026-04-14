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

export interface UserStory {
  title: string;
  acceptance_criteria: string[];
}

export interface UserStoryCard {
  action: string;
  feedbacks: string[];
  user_stories: UserStory[];
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
  | { type: "categorization" }
  | { type: "report" }
  | { type: "done"; result: AnalysisResult }
  | { type: "error"; message: string };

export interface AppEntry {
  id: number;
  name: string;
  category: string;
}
