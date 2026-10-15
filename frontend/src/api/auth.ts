import { requestJson } from "./client";

export { ApiError } from "./client";

export interface SignupPayload {
  email: string;
  password: string;
  name: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface UserResponse {
  id: string;
  email: string;
  name: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export function signup(payload: SignupPayload): Promise<UserResponse> {
  return requestJson<UserResponse>("POST", "/auth/signup", payload);
}

export function login(payload: LoginPayload): Promise<TokenResponse> {
  return requestJson<TokenResponse>("POST", "/auth/login", payload);
}
