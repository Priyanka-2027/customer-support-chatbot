// components/MessageBubble.tsx
import ReactMarkdown from "react-markdown";
import type { Message } from "../types";

interface MessageBubbleProps {
  message: Message;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex w-full ${isUser ? "justify-end" : "justify-start"} mb-3`}>

      {!isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center mr-2 mt-1">
          <span className="text-white text-sm" role="img" aria-label="Bot">🤖</span>
        </div>
      )}

      <div className="max-w-[75%]">
        <div
          className={[
            "rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm",
            isUser
              ? "bg-indigo-600 text-white rounded-br-sm"
              : "bg-white text-gray-800 rounded-bl-sm border border-gray-100",
          ].join(" ")}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{message.text}</p>
          ) : (
            // Render bot responses as markdown so **bold**, * lists, etc. display correctly
            <div className="[&_strong]:font-semibold [&_ul]:list-disc [&_ul]:pl-4 [&_ul]:my-1 [&_ol]:list-decimal [&_ol]:pl-4 [&_ol]:my-1 [&_li]:my-0.5 [&_p]:my-1 [&_h1]:font-bold [&_h1]:text-base [&_h2]:font-bold [&_h2]:text-sm [&_h3]:font-semibold [&_h3]:text-sm [&_code]:bg-gray-100 [&_code]:px-1 [&_code]:rounded [&_code]:text-xs">
              <ReactMarkdown>{message.text}</ReactMarkdown>
            </div>
          )}
        </div>

        <p
          className={`text-xs text-gray-400 mt-1 ${isUser ? "text-right" : "text-left"}`}
        >
          {message.timestamp.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
      </div>

      {isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gray-300 flex items-center justify-center ml-2 mt-1">
          <span className="text-gray-600 text-sm" role="img" aria-label="You">👤</span>
        </div>
      )}
    </div>
  );
}
