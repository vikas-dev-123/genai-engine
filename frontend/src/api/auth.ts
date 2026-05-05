import apiClient from "./client";
import type { TokenResponse, User } from "../types";

export async function login(email: string, password: string): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>("/auth/login", {
    email,
    password,
  });
  return data;
}

export async function register(
  email: string,
  password: string,
  name: string,
): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>("/auth/register", {
    email,
    password,
    name,
  });
  return data;
}

export async function getMe(): Promise<User> {
  const { data } = await apiClient.get<User>("/auth/me");
  return data;
}

export async function refreshToken(token: string): Promise<{ access_token: string }> {
  const { data } = await apiClient.post<{ access_token: string }>("/auth/refresh", {
    refresh_token: token,
  });
  return data;
}
