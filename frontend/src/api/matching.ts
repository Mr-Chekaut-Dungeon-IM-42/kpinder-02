import { requestJson } from "./client";

export interface Candidate {
  id: string;
  name: string;
  age: number | null;
  bio: string | null;
  photo_url: string | null;
  interests: string[];
}

export interface SwipeResult {
  matched: boolean;
  match_id: string | null;
}

export interface MatchUser {
  id: string;
  name: string;
  photo_url: string | null;
}

export interface Match {
  match_id: string;
  created_at: string;
  other_user: MatchUser;
}

export interface MatchesPage {
  items: Match[];
  next_cursor: string | null;
}

export function getFeed(token: string): Promise<Candidate[]> {
  return requestJson<Candidate[]>("GET", "/matching/feed", undefined, token);
}

export function swipe(
  token: string,
  targetId: string,
  decision: "like" | "pass",
): Promise<SwipeResult> {
  return requestJson<SwipeResult>(
    "POST",
    "/matching/swipe",
    { target_id: targetId, decision },
    token,
  );
}

export function getMatches(
  token: string,
  cursor?: string | null,
): Promise<MatchesPage> {
  const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return requestJson<MatchesPage>(
    "GET",
    `/matching/matches${query}`,
    undefined,
    token,
  );
}
