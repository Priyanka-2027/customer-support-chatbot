// components/SourceDocs.tsx
// ─────────────────────────────────────────────────────────────
// Responsibility:
//   Display every source chunk used to generate the bot's answer.
//   Each source shows:
//     - Document filename
//     - Page number
//     - The retrieved chunk text (expandable)
//
//   This panel is the transparency layer of the RAG system —
//   users and support managers can verify every claim the bot
//   makes by reading the exact passage it drew from.
// ─────────────────────────────────────────────────────────────

import { useState } from "react";
import type { SourceDocument } from "../types";

interface SourceDocsProps {
  sources: SourceDocument[];
}

export default function SourceDocs({ sources }: SourceDocsProps) {
  // Render nothing when there are no sources.
  // This happens when the bot replies "I don't know" —
  // there's no chunk text to show.
  if (!sources || sources.length === 0) return null;

  return (
    // ml-10 aligns with the bubble text (32px avatar + 8px gap).
    // mb-4 adds breathing room below the sources before the
    // next message.
    <div className="ml-10 mb-4 max-w-[75%]">

      {/* Section label */}
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
        Retrieved Sources ({sources.length})
      </p>

      {/* One card per source chunk */}
      <div className="space-y-2">
        {sources.map((source, index) => (
          <SourceChunkCard
            key={`${source.filename}-${source.page}-${source.chunk_index}`}
            source={source}
            // Display rank: "1 of 3", "2 of 3", etc.
            rank={index + 1}
            total={sources.length}
          />
        ))}
      </div>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// SourceChunkCard — private sub-component
// ─────────────────────────────────────────────────────────────
// One collapsible card for a single retrieved chunk.
// Keeps SourceDocs clean by extracting the per-item logic.

interface SourceChunkCardProps {
  source: SourceDocument;
  rank: number;
  total: number;
}

function SourceChunkCard({ source, rank, total }: SourceChunkCardProps) {

  // isExpanded controls whether the chunk text preview is visible.
  // Starts collapsed — the filename + page is always visible.
  // The user clicks to expand when they want to read the passage.
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="rounded-xl border border-indigo-100 bg-indigo-50/60 overflow-hidden">

      {/* ── Card header — always visible ────────────────────── */}
      {/* Clicking anywhere on the header toggles the chunk text. */}
      <button
        onClick={() => setIsExpanded((prev) => !prev)}
        className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left hover:bg-indigo-100/60 transition-colors"
        // aria-expanded tells screen readers whether the details
        // section is currently visible.
        aria-expanded={isExpanded}
        aria-controls={`chunk-${rank}`}
      >

        {/* Rank badge — "1" in a small indigo circle */}
        <span className="flex-shrink-0 w-5 h-5 rounded-full bg-indigo-600 text-white text-[10px] font-bold flex items-center justify-center">
          {rank}
        </span>

        {/* Document info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">

            {/* Filename — truncated with ellipsis if too long */}
            <span className="text-xs font-semibold text-indigo-800 truncate max-w-[160px]">
              {source.filename}
            </span>

            {/* Page badge */}
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-indigo-200/70 text-indigo-700 text-[10px] font-medium flex-shrink-0">
              {/* Tiny page icon */}
              <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              Page {source.page}
            </span>

            {/* Source rank indicator */}
            <span className="text-[10px] text-indigo-400 flex-shrink-0">
              {rank} of {total}
            </span>
          </div>
        </div>

        {/* Expand/collapse chevron — rotates 180° when expanded */}
        <svg
          className={`w-3.5 h-3.5 text-indigo-400 flex-shrink-0 transition-transform duration-200 ${
            isExpanded ? "rotate-180" : ""
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* ── Chunk text — only rendered when expanded ─────────── */}
      {/* The id matches aria-controls on the button above. */}
      {isExpanded && (
        <div
          id={`chunk-${rank}`}
          className="px-3 pb-3 pt-1 border-t border-indigo-100"
        >

          {/* "Retrieved passage" label */}
          <p className="text-[10px] font-semibold text-indigo-400 uppercase tracking-wide mb-1.5">
            Retrieved passage
          </p>

          {/* The chunk text itself.
              font-mono makes it clear this is raw extracted text,
              not a polished response. whitespace-pre-wrap preserves
              any intentional line breaks in the passage. */}
          <blockquote className="text-xs text-gray-700 leading-relaxed bg-white rounded-lg px-3 py-2.5 border-l-2 border-indigo-300 whitespace-pre-wrap font-mono">
            {source.chunk_text}
          </blockquote>

          {/* Chunk offset — shown as a fine-print detail for
              advanced users who want to locate the exact passage */}
          {source.chunk_index > 0 && (
            <p className="text-[10px] text-indigo-300 mt-1.5">
              Character offset: {source.chunk_index.toLocaleString()}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
