import type {
  BreakoutLogResponse,
  CreatorDetailResponse,
  CreatorsResponse,
  HomeResponse,
  PostDetail,
  PostsBoardResponse,
  SystemStatus,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

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

export function getPostsBoard(): Promise<PostsBoardResponse> {
  return request<PostsBoardResponse>("/api/posts");
}

export interface AgentChatRequest {
  session_id: string;
  message: string;
  selected_post_id?: string;
  // True for the auto-triggered opening line — see agent.py's ChatRequest.
  proactive?: boolean;
}

export interface AgentChatResponse {
  text: string;
  facts_used: Record<string, unknown>;
  llm_available: boolean;
}

// The API key lives only on the server; the browser never sees it.
export async function sendAgentMessage(body: AgentChatRequest): Promise<AgentChatResponse> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/api/agent/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Couldn't reach the server. Check your connection and try again.");
  }
  if (!response.ok) {
    throw new ApiError("Something went wrong asking the agent.", response.status);
  }
  return (await response.json()) as AgentChatResponse;
}

export async function endAgentSession(sessionId: string): Promise<void> {
  await fetch(`${BASE_URL}/api/agent/chat/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
}
