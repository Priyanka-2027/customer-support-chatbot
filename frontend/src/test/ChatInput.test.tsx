/**
 * ChatInput.test.tsx — ChatInput component tests
 * Validates: Requirements 8.5–8.6
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ChatInput from "../components/ChatInput";

describe("ChatInput", () => {
  it("calls onSend with trimmed text and clears input on Enter (Req 8.5)", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} isLoading={false} />);

    const textarea = screen.getByRole("textbox");
    await user.type(textarea, "  hello world  ");
    await user.keyboard("{Enter}");

    expect(onSend).toHaveBeenCalledWith("hello world");
    expect(textarea).toHaveValue("");
  });

  it("Shift+Enter inserts newline instead of submitting", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} isLoading={false} />);

    const textarea = screen.getByRole("textbox");
    await user.type(textarea, "line1");
    await user.keyboard("{Shift>}{Enter}{/Shift}");

    expect(onSend).not.toHaveBeenCalled();
  });

  it("textarea and submit button are disabled when isLoading=true (Req 8.6)", () => {
    render(<ChatInput onSend={vi.fn()} isLoading={true} />);

    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });

  it("empty input does not call onSend", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} isLoading={false} />);

    await user.keyboard("{Enter}");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("send button is disabled when input is empty", () => {
    render(<ChatInput onSend={vi.fn()} isLoading={false} />);
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });
});
