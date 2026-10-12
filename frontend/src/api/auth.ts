const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new ApiError(
      response.status,
      data?.detail ?? "Something went wrong. Please try again.",
    );
  }

  return response.json() as Promise<T>;
}

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
  return request<UserResponse>("/auth/signup", payload);
}

export function login(payload: LoginPayload): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/login", payload);
}
