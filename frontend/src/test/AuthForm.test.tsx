/**
 * AuthForm.test.tsx — AuthForm component tests
 * Validates: Requirements 8.1–8.4
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AuthForm from "../components/AuthForm";

const mockLogin = vi.fn();
const mockRegister = vi.fn();

function renderForm() {
  render(
    <AuthForm
      onLogin={mockLogin}
      onRegister={mockRegister}
      isLoading={false}
      error={null}
    />
  );
}

describe("AuthForm", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("shows error when submitted with empty fields (Req 8.1)", async () => {
    const user = userEvent.setup();
    renderForm();

    // Click the submit button (type=submit), not the tab button
    await user.click(screen.getByRole("button", { name: /sign in/i, hidden: false }));
    // There are two "Sign In" buttons — the tab and the submit. Click the form submit.
    const allSignInBtns = screen.getAllByRole("button", { name: /sign in/i });
    const submitBtn = allSignInBtns.find(b => b.getAttribute("type") === "submit");
    if (submitBtn) await user.click(submitBtn);

    expect(screen.getByText("Email and password are required.")).toBeInTheDocument();
  });

  it("shows error for short password in register mode (Req 8.2)", async () => {
    const user = userEvent.setup();
    renderForm();

    // Switch to register
    await user.click(screen.getByText("Register"));

    await user.type(screen.getByLabelText(/email/i), "user@example.com");
    await user.type(screen.getAllByLabelText(/^Password$/i)[0], "short");
    await user.type(screen.getByLabelText(/confirm password/i), "short");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(screen.getByText("Password must be at least 8 characters.")).toBeInTheDocument();
  });

  it("shows error when passwords don't match in register mode (Req 8.3)", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByText("Register"));

    await user.type(screen.getByLabelText(/email/i), "user@example.com");
    await user.type(screen.getAllByLabelText(/^Password$/i)[0], "password123");
    await user.type(screen.getByLabelText(/confirm password/i), "different123");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(screen.getByText("Passwords do not match.")).toBeInTheDocument();
  });

  it("calls onLogin with lowercased email and password on valid submit (Req 8.4)", async () => {
    const user = userEvent.setup();
    mockLogin.mockResolvedValue(undefined);
    renderForm();

    await user.type(screen.getByLabelText(/email/i), "USER@EXAMPLE.COM");
    await user.type(screen.getAllByLabelText(/^Password$/i)[0], "mypassword");
    // Click the submit button specifically
    const allSignInBtns = screen.getAllByRole("button", { name: /sign in/i });
    const submitBtn = allSignInBtns.find(b => b.getAttribute("type") === "submit")!;
    await user.click(submitBtn);

    expect(mockLogin).toHaveBeenCalledWith("user@example.com", "mypassword");
  });

  it("renders sign-in submit button by default", () => {
    renderForm();
    const allSignInBtns = screen.getAllByRole("button", { name: /sign in/i });
    const submitBtn = allSignInBtns.find(b => b.getAttribute("type") === "submit");
    expect(submitBtn).toBeTruthy();
  });

  it("shows server error when error prop is set", () => {
    render(
      <AuthForm
        onLogin={mockLogin}
        onRegister={mockRegister}
        isLoading={false}
        error="Invalid credentials"
      />
    );
    expect(screen.getByText("Invalid credentials")).toBeInTheDocument();
  });

  it("disables button when isLoading=true", () => {
    render(
      <AuthForm
        onLogin={mockLogin}
        onRegister={mockRegister}
        isLoading={true}
        error={null}
      />
    );
    expect(screen.getByRole("button", { name: /signing in/i })).toBeDisabled();
  });
});
