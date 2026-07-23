/**
 * useChat.test.tsx — chat hook tests
 * Validates: Requirements 6.6–6.8
 */

import { renderHook, act, waitFor } from "@testing-library/react";
import { useChat } from "../hooks/useChat";

vi.mock("../api/chat", () => ({
  sendMessage: vi.fn(),
}));

import { sendMessage } from "../api/chat";

describe("useChat", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("handleSend adds user message immediately before API resolves (Req 6.6)", async () => {
    // Never-resolving promise simulates in-flight request
    vi.mocked(sendMessage).mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useChat());

    act(() => {
      result.current.handleSend("hello");
    });

    // User message should be added optimistically
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].role).toBe("user");
    expect(result.current.messages[0].text).toBe("hello");
  });

  it("on success adds bot message and sets conversationId (Req 6.7)", async () => {
    vi.mocked(sendMessage).mockResolvedValue({
      answer: "test answer",
      sources: [],
      conversation_id: "conv-1",
    });

    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.handleSend("question");
    });

    await waitFor(() => expect(result.current.messages).toHaveLength(2));

    const botMsg = result.current.messages[1];
    expect(botMsg.role).toBe("bot");
    expect(botMsg.text).toBe("test answer");
    expect(result.current.conversationId).toBe("conv-1");
  });

  it("clearMessages resets messages, error, and conversationId (Req 6.8)", async () => {
    vi.mocked(sendMessage).mockResolvedValue({
      answer: "reply", sources: [], conversation_id: "conv-1",
    });

    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.handleSend("hi");
    });

    await waitFor(() => expect(result.current.conversationId).toBe("conv-1"));

    act(() => result.current.clearMessages());

    expect(result.current.messages).toHaveLength(0);
    expect(result.current.error).toBeNull();
    expect(result.current.conversationId).toBeNull();
  });

  it("trims whitespace before sending (preserves behaviour)", async () => {
    vi.mocked(sendMessage).mockResolvedValue({
      answer: "ok", sources: [], conversation_id: "c1",
    });

    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.handleSend("  padded  ");
    });

    expect(result.current.messages[0].text).toBe("padded");
  });

  it("empty string does not trigger a send", () => {
    const { result } = renderHook(() => useChat());

    act(() => {
      result.current.handleSend("   ");
    });

    expect(sendMessage).not.toHaveBeenCalled();
    expect(result.current.messages).toHaveLength(0);
  });
});
