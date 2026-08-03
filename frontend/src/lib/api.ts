import type {
  BreakoutLogResponse,
  CreatorDetailResponse,
  CreatorsResponse,
  HomeResponse,
  PostDetail,
  SystemStatus,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8001";

export class ApiError extends Error {
  status: number | null;
  constructor(message: string, status: number | null = null) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`);
  } catch {
    throw new ApiError("Couldn't reach the server. Check your connection and try again.");
  }

  if (response.status === 404) {
    throw new ApiError("We couldn't find that.", 404);
  }
  if (!response.ok) {
    throw new ApiError("Something went wrong loading this data.", response.status);
  }

  return (await response.json()) as T;
}

export function getHome(): Promise<HomeResponse> {
  return request<HomeResponse>("/api/home");
}

export function getPostDetail(postId: string): Promise<PostDetail> {
  return request<PostDetail>(`/api/posts/${encodeURIComponent(postId)}`);
}

export function getCreators(): Promise<CreatorsResponse> {
  return request<CreatorsResponse>("/api/creators");
}

export function getCreatorDetail(creatorId: string): Promise<CreatorDetailResponse> {
  return request<CreatorDetailResponse>(`/api/creators/${encodeURIComponent(creatorId)}`);
}

export function getStatus(): Promise<SystemStatus> {
  return request<SystemStatus>("/api/status");
}

export function getBreakoutLog(): Promise<BreakoutLogResponse> {
  return request<BreakoutLogResponse>("/api/breakouts");
}
