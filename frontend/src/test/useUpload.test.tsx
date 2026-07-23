/**
 * useUpload.test.tsx — upload hook tests
 * Validates: Requirements 6.9–6.11
 */

import { renderHook, act } from "@testing-library/react";
import { useUpload } from "../hooks/useUpload";

vi.mock("../api/chat", () => ({
  uploadDocuments: vi.fn(),
}));

import { uploadDocuments } from "../api/chat";

function makeFile(name: string, type: string, size = 100): File {
  const content = new Uint8Array(size);
  return new File([content], name, { type });
}

describe("useUpload", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("addFiles with non-PDF adds entry with status=error (Req 6.9)", () => {
    const { result } = renderHook(() => useUpload());

    act(() => {
      result.current.addFiles([makeFile("doc.txt", "text/plain")]);
    });

    expect(result.current.fileStates).toHaveLength(1);
    expect(result.current.fileStates[0].status).toBe("error");
    expect(result.current.fileStates[0].error).toBeTruthy();
  });

  it("addFiles with PDF > 20MB adds entry with status=error mentioning size (Req 6.10)", () => {
    const { result } = renderHook(() => useUpload());
    const bigSizeBytes = 21 * 1024 * 1024; // 21 MB

    act(() => {
      result.current.addFiles([makeFile("big.pdf", "application/pdf", bigSizeBytes)]);
    });

    expect(result.current.fileStates[0].status).toBe("error");
    expect(result.current.fileStates[0].error).toMatch(/max|MB|size/i);
  });

  it("addFiles with valid PDF adds pending entry", () => {
    const { result } = renderHook(() => useUpload());

    act(() => {
      result.current.addFiles([makeFile("valid.pdf", "application/pdf")]);
    });

    expect(result.current.fileStates[0].status).toBe("pending");
    expect(result.current.fileStates[0].error).toBeUndefined();
  });

  it("uploadAll on success sets status=success and isDone=true (Req 6.11)", async () => {
    vi.mocked(uploadDocuments).mockResolvedValue({
      total_files: 1,
      successful: 1,
      failed: 0,
      total_chunks_created: 5,
      results: [{ filename: "valid.pdf", success: true, chunks_created: 5, error: null }],
    });

    const { result } = renderHook(() => useUpload());

    act(() => {
      result.current.addFiles([makeFile("valid.pdf", "application/pdf")]);
    });

    await act(async () => {
      await result.current.uploadAll();
    });

    expect(result.current.fileStates[0].status).toBe("success");
    expect(result.current.isDone).toBe(true);
  });

  it("uploadAll on per-file error sets status=error for that file (Req 6.11)", async () => {
    vi.mocked(uploadDocuments).mockResolvedValue({
      total_files: 1,
      successful: 0,
      failed: 1,
      total_chunks_created: 0,
      results: [{ filename: "bad.pdf", success: false, chunks_created: 0, error: "Processing failed" }],
    });

    const { result } = renderHook(() => useUpload());

    act(() => {
      result.current.addFiles([makeFile("bad.pdf", "application/pdf")]);
    });

    await act(async () => {
      await result.current.uploadAll();
    });

    expect(result.current.fileStates[0].status).toBe("error");
    expect(result.current.isDone).toBe(true);
  });
});
