import { requestJson, requestMultipart } from "./client";

export type Gender = "male" | "female" | "other";
export type Seeking = "male" | "female" | "everyone";

export interface Interest {
  id: string;
  name: string;
}

export interface Profile {
  id: string;
  email: string;
  name: string;
  bio: string | null;
  age: number | null;
  gender: Gender | null;
  seeking: Seeking | null;
  age_min: number | null;
  age_max: number | null;
  photo_url: string | null;
  interests: string[];
  has_location: boolean;
  location_label: string | null;
}

export interface ProfileUpdatePayload {
  bio: string | null;
  age: number | null;
  gender: Gender | null;
  seeking: Seeking | null;
  age_min: number | null;
  age_max: number | null;
  interests: string[];
  latitude?: number | null;
  longitude?: number | null;
  location_label?: string | null;
}

export function getInterests(): Promise<Interest[]> {
  return requestJson<Interest[]>("GET", "/auth/interests");
}

export function getProfile(token: string): Promise<Profile> {
  return requestJson<Profile>("GET", "/auth/me", undefined, token);
}

export function updateProfile(
  token: string,
  payload: ProfileUpdatePayload,
): Promise<Profile> {
  return requestJson<Profile>("PATCH", "/auth/update_profile", payload, token);
}

export function uploadPhoto(
  token: string,
  file: File,
): Promise<{ photo_url: string }> {
  const formData = new FormData();
  formData.append("file", file);
  return requestMultipart<{ photo_url: string }>(
    "/auth/upload_photo",
    formData,
    token,
  );
}
