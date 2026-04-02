export interface UIMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
  attachmentName?: string;
}
