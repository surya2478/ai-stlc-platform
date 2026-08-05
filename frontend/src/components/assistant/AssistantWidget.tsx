"use client";

import React, { useEffect, useState, useRef, useMemo } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import {
  X, Send, Trash2, Maximize2, Minimize2,
  ThumbsUp, ThumbsDown, Loader2, Shield,
} from "lucide-react";
import { api, projectsApi, type Project } from "@/lib/api";
import { cn } from "@/lib/utils";

// ── Types ──────────────────────────────────────────────────────────────────────

interface Message {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
  scope_classification?: string;
  confidence?: string;
  created_at: string;
}

interface Citation {
  type: string;
  id: string;
}

// ── Simple Markdown Renderer Component ──────────────────────────────────────────

interface MarkdownTextProps {
  text: string;
  projectId: number | null;
}

const MarkdownText: React.FC<MarkdownTextProps> = ({ text, projectId }) => {
  if (!text) return null;

  const lines = text.split("\n");
  const parsedElements = lines.map((line, idx) => {
    // 1. Code Block starts/ends
    if (line.trim().startsWith("```")) {
      return null; // Simplified code-block placeholder
    }

    // 2. Check for Headers
    if (line.startsWith("### ")) {
      return <h4 key={idx} className="text-xs font-bold text-gray-800 mt-3 mb-1.5">{line.replace("### ", "")}</h4>;
    }
    if (line.startsWith("## ")) {
      return <h3 key={idx} className="text-sm font-bold text-gray-900 mt-4 mb-2">{line.replace("## ", "")}</h3>;
    }
    if (line.startsWith("# ")) {
      return <h2 key={idx} className="text-base font-bold text-gray-950 mt-5 mb-2.5">{line.replace("# ", "")}</h2>;
    }

    // 3. Check for Bullets
    if (line.trim().startsWith("•") || line.trim().startsWith("-") || line.trim().startsWith("*")) {
      const content = line.replace(/^[•\-*]\s*/, "");
      return (
        <li key={idx} className="list-disc list-inside text-xs text-gray-600 ml-3.5 my-1 leading-relaxed">
          {renderInlineStyles(content, projectId)}
        </li>
      );
    }

    // 4. Regular Paragraph
    return (
      <p key={idx} className="text-xs text-gray-600 leading-relaxed my-2">
        {renderInlineStyles(line, projectId)}
      </p>
    );
  });

  return <div className="space-y-0.5">{parsedElements}</div>;
};

// Formats inline code (`) and bold (**) and deep links citations
function renderInlineStyles(text: string, projectId: number | null) {
  if (!text) return "";

  // Regex to extract citation keys
  const citationRegex = /((?:REQ|TC|DEF|RUN|APP|TP)-\d+)/g;
  const boldRegex = /\*\*(.*?)\*\*/g;
  const codeRegex = /`(.*?)`/g;

  // Split and map
  let parts: React.ReactNode[] = [text];

  // 1. Process Bold
  parts = parts.flatMap((part) => {
    if (typeof part !== "string") return part;
    const splitParts = part.split(boldRegex);
    return splitParts.map((sub, i) => (i % 2 === 1 ? <strong key={i} className="font-semibold text-gray-800">{sub}</strong> : sub));
  });

  // 2. Process Code
  parts = parts.flatMap((part) => {
    if (typeof part !== "string") return part;
    const splitParts = part.split(codeRegex);
    return splitParts.map((sub, i) => (i % 2 === 1 ? <code key={i} className="bg-gray-100 text-gray-800 rounded px-1 py-0.5 text-[10px] font-mono">{sub}</code> : sub));
  });

  // 3. Process Citations with Deep Links
  parts = parts.flatMap((part) => {
    if (typeof part !== "string") return part;
    
    const splitParts = part.split(citationRegex);
    return splitParts.map((sub, i) => {
      if (i % 2 === 1) {
        // Citation matching key
        const key = sub;
        const projectParam = projectId ? `?project=${projectId}` : "";
        let route = "/dashboard";

        if (key.startsWith("REQ-")) route = "/requirements";
        else if (key.startsWith("TC-")) route = "/test-cases";
        else if (key.startsWith("DEF-")) route = "/defects";
        else if (key.startsWith("RUN-")) route = "/execution";
        else if (key.startsWith("TP-") || key.startsWith("APP-")) route = "/test-planning";

        return (
          <a
            key={i}
            href={`${route}${projectParam}`}
            className="text-[#B71920] hover:underline font-bold inline-flex items-center gap-0.5 select-all"
          >
            {key}
          </a>
        );
      }
      return sub;
    });
  });

  return parts;
}


// ── Glyphs ─────────────────────────────────────────────────────────────────────
// Both are the reference's own SVGs: a speech bubble for the launcher and the
// empty thread, and a chip-with-rays mark for the header. They replace an
// illustrated headset avatar that shipped its own skin, blush and shirt
// colours — a palette that answered to nothing else in the app.

const ChatBubbleIcon: React.FC<{ className?: string }> = ({ className }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
    />
  </svg>
);

const AssistantGlyph: React.FC<{ className?: string }> = ({ className }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
    <rect x="7" y="7" width="10" height="10" rx="2" strokeWidth="2" />
    <path d="M12 3v3M12 21v-3M3 12h3M21 12h-3" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

// ── Main Assistant Widget ───────────────────────────────────────────────────────

export const AssistantWidget: React.FC = () => {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const projectId = useMemo(() => {
    const p = searchParams.get("project");
    return p ? parseInt(p) : null;
  }, [searchParams]);

  // Drawer States
  const [isOpen, setIsOpen] = useState(false);
  const [isWide, setIsWide] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectName, setActiveProjectName] = useState<string>("Loading...");

  const resolvedProjectId = useMemo(() => {
    if (projectId) return projectId;
    if (projects.length > 0) return projects[0].id;
    return null;
  }, [projectId, projects]);
  
  // Chat States
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMsg, setInputMsg] = useState("");
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [feedbackRatings, setFeedbackRatings] = useState<Record<number, "helpful" | "unhelpful">>({});

  const scrollRef = useRef<HTMLDivElement>(null);

  // Load project details
  useEffect(() => {
    if (!isOpen) return;

    projectsApi.list()
      .then((res) => {
        setProjects(res.data);
        const match = res.data.find(p => p.id === projectId);
        if (match) {
          setActiveProjectName(match.name);
        } else if (res.data.length > 0) {
          setActiveProjectName(res.data[0].name);
        } else {
          setActiveProjectName("None");
        }
      })
      .catch(() => setActiveProjectName("General Scope"));
  }, [isOpen, projectId]);

  // Load context-aware suggestions
  useEffect(() => {
    if (!isOpen) return;

    api.get<string[]>(`/assistant/suggestions?current_route=${pathname}`)
      .then((res) => setSuggestions(res.data))
      .catch(() => setSuggestions(["Summarize current project status", "Show blocked test cases"]));
  }, [isOpen, pathname]);

  // Load conversation list and fetch latest conversation on open
  useEffect(() => {
    if (!isOpen || !resolvedProjectId) return;

    api.get<any[]>((`/assistant/conversations?project_id=${resolvedProjectId}`))
      .then((res) => {
        if (res.data.length > 0) {
          const latest = res.data[0];
          setActiveConversationId(latest.id);
          // Fetch messages
          api.get<Message[]>(`/assistant/conversations/${latest.id}`)
            .then((msgRes) => setMessages(msgRes.data))
            .catch(() => {
              setMessages([]);
              setActiveConversationId(null);
            });
        } else {
          setMessages([]);
          setActiveConversationId(null);
        }
      })
      .catch(() => {
        setMessages([]);
        setActiveConversationId(null);
      });
  }, [isOpen, resolvedProjectId]);

  // Scroll to bottom with layout timeout
  useEffect(() => {
    if (scrollRef.current) {
      const scrollContainer = scrollRef.current;
      const timer = setTimeout(() => {
        scrollContainer.scrollTop = scrollContainer.scrollHeight;
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [messages, isLoading]);

  // Keyboard accessibility
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const handleSendMessage = async (textToSend: string) => {
    if (!textToSend.trim() || isLoading || !resolvedProjectId) return;

    setIsLoading(true);
    setInputMsg("");

    // Add user message locally
    const userTempMsg: Message = {
      id: Date.now(),
      role: "user",
      content: textToSend,
      created_at: new Date().toISOString()
    };
    setMessages((prev) => [...prev, userTempMsg]);

    try {
      // Called directly rather than through runAIAction: that helper throws a
      // full-screen processing modal over the app, which is right for a long
      // generation job you kick off and wait on, and wrong for a chat turn.
      // The panel already shows its own inline "thinking" indicator while
      // isLoading is set, and blocking the page hid the conversation you were
      // having.
      const res = await api.post("/assistant/chat", {
        message: textToSend,
        conversation_id: activeConversationId,
        current_route: pathname,
        project_id: resolvedProjectId
      });

      const data = res.data;
      setActiveConversationId(data.conversation_id);

      const assistantMsg: Message = {
        id: Date.now() + 1,
        role: "assistant",
        content: data.answer,
        scope_classification: data.scope,
        confidence: data.confidence,
        created_at: new Date().toISOString()
      };
      setMessages((prev) => [...prev, assistantMsg]);
      
      // Update suggestions dynamically if returned
      if (data.suggested_questions && data.suggested_questions.length > 0) {
        setSuggestions(data.suggested_questions);
      }
    } catch (err: any) {
      const errText = err?.response?.data?.detail || "Error connecting to the Platform Assistant. Please check if it's enabled.";
      const errorMsg: Message = {
        id: Date.now() + 2,
        role: "system",
        content: errText,
        created_at: new Date().toISOString()
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleClearConversation = async () => {
    if (!activeConversationId) return;
    if (confirm("Are you sure you want to clear this conversation?")) {
      try {
        await api.delete(`/assistant/conversations/${activeConversationId}`);
        setMessages([]);
        setActiveConversationId(null);
      } catch (err) {
        console.error("Failed to delete conversation:", err);
      }
    }
  };

  const submitFeedback = async (msgId: number, type: "helpful" | "unhelpful") => {
    if (!activeConversationId) return;
    try {
      await api.post("/assistant/feedback", {
        conversation_id: activeConversationId,
        message_id: msgId,
        feedback_type: type
      });
      setFeedbackRatings((prev) => ({ ...prev, [msgId]: type }));
    } catch (err) {
      console.error("Failed to submit feedback:", err);
    }
  };

  const activePageLabel = useMemo(() => {
    const segment = pathname.split("/").filter(Boolean)[0] || "dashboard";
    return segment.split("-").map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
  }, [pathname]);

  // Hide on login screen
  if (pathname === "/login") return null;

  return (
    <>
      {/* ── 1. Floating Launcher ── the reference's 56px circular button. */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-app-brand-600 text-white shadow-lg transition-all duration-200 hover:scale-110 hover:bg-app-brand-700"
          title="Open chat"
          aria-label="Open QAI Platform Assistant"
        >
          <ChatBubbleIcon className="h-6 w-6" />
        </button>
      )}

      {/* ── 2. Assistant Drawer Overlay (only when expanded to wide view) ── */}
      {isOpen && isWide && (
        <div 
          className="fixed inset-0 z-45 bg-black/20 backdrop-blur-xs transition-opacity duration-300"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* ── 3. Assistant Drawer Panel ── */}
      {isOpen && (
        <div
          className={cn(
            "fixed z-50 flex flex-col overflow-hidden bg-white shadow-2xl transition-all duration-300 focus:outline-none",
            isWide
              ? "inset-y-0 right-0 h-full w-full border-l border-gray-200 sm:max-w-xl md:max-w-2xl"
              : "bottom-6 right-6 h-[520px] max-h-[80vh] w-[calc(100vw-32px)] rounded-lg border border-gray-200 sm:w-96"
          )}
          role="dialog"
          aria-labelledby="assistant-title"
        >
          {/* Header — the reference's red gradient bar. The illustrated
              headset avatar is gone with it: a photoreal mascot at 40px was
              carrying its own palette (skin, blush, a cyan shirt) that no
              longer belongs to anything on screen. */}
          <div className="flex shrink-0 items-center justify-between bg-gradient-to-r from-app-brand-600 to-app-brand-700 p-4 text-white">
            <div className="flex min-w-0 items-center gap-2">
              <AssistantGlyph className="h-5 w-5 shrink-0" />
              <div className="min-w-0">
                <h2 id="assistant-title" className="text-lg font-semibold leading-tight">
                  AI Assistant
                </h2>
                <p className="truncate text-xs text-app-brand-100">
                  {isWide ? `${activeProjectName} · ${activePageLabel}` : activePageLabel}
                </p>
              </div>
            </div>

            <div className="flex shrink-0 items-center gap-1">
              {activeConversationId && (
                <button
                  onClick={handleClearConversation}
                  title="Clear current thread"
                  className="rounded-full p-1 text-white transition-colors hover:bg-app-brand-800"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
              <button
                onClick={() => setIsWide(!isWide)}
                title={isWide ? "Restore window size" : "Expand window size"}
                className="hidden rounded-full p-1 text-white transition-colors hover:bg-app-brand-800 sm:block"
              >
                {isWide ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
              </button>
              <button
                onClick={() => setIsOpen(false)}
                className="rounded-full p-1 text-white transition-colors hover:bg-app-brand-800"
                aria-label="Close chat"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>

          {/* Body — the reference's grey thread on white. */}
          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto bg-gray-50 p-4 scroll-smooth">
            {messages.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center px-4 text-center text-sm text-gray-400">
                <ChatBubbleIcon className="mx-auto mb-2 h-12 w-12 text-gray-300" />
                <p>Start a conversation</p>
                <p className="mt-1 text-xs">Ask me anything about {activePageLabel.toLowerCase()}</p>

                {suggestions.length > 0 && (
                  <div className="mt-6 w-full max-w-xs space-y-2">
                    {suggestions.map((sug, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleSendMessage(sug)}
                        disabled={isLoading}
                        className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-left text-sm text-gray-700 transition-colors hover:border-app-brand-500 hover:text-app-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {sug}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              messages.map((m, idx) => {
                const isUser = m.role === "user";
                const isSystem = m.role === "system";
                return (
                  <div key={m.id || idx} className={cn("flex", isUser ? "justify-end" : "justify-start")}>
                    <div
                      className={cn(
                        "rounded-lg px-4 py-2 text-sm shadow-sm",
                        isWide ? "max-w-md" : "max-w-xs",
                        isUser
                          ? "rounded-br-none bg-app-brand-600 text-white"
                          : isSystem
                            ? "rounded-bl-none border border-red-200 bg-red-100 text-red-700"
                            : "rounded-bl-none bg-gray-200 text-gray-900",
                      )}
                    >
                      {isUser ? (
                        <p className="whitespace-pre-wrap break-words">{m.content}</p>
                      ) : (
                        <MarkdownText text={m.content} projectId={resolvedProjectId} />
                      )}

                      <div className="mt-1 flex items-center gap-2">
                        <p className={cn("text-xs", isUser ? "text-app-brand-100" : "text-gray-500")}>
                          {new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </p>

                        {/* Kept from this widget: answers are scoped to the
                            caller's project and role, and can be rated. */}
                        {!isUser && !isSystem && (
                          <>
                            <span className="inline-flex items-center gap-1 text-xs text-gray-500">
                              <Shield className="h-3 w-3" />
                              Project-scoped
                            </span>
                            <span className="ml-auto flex items-center gap-1">
                              <button
                                onClick={() => submitFeedback(m.id, "helpful")}
                                disabled={feedbackRatings[m.id] !== undefined}
                                className={cn(
                                  "rounded p-0.5 transition-colors hover:bg-gray-300",
                                  feedbackRatings[m.id] === "helpful" ? "text-emerald-600" : "text-gray-500",
                                )}
                                title="Helpful"
                              >
                                <ThumbsUp className="h-3.5 w-3.5" />
                              </button>
                              <button
                                onClick={() => submitFeedback(m.id, "unhelpful")}
                                disabled={feedbackRatings[m.id] !== undefined}
                                className={cn(
                                  "rounded p-0.5 transition-colors hover:bg-gray-300",
                                  feedbackRatings[m.id] === "unhelpful" ? "text-red-600" : "text-gray-500",
                                )}
                                title="Not helpful"
                              >
                                <ThumbsDown className="h-3.5 w-3.5" />
                              </button>
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
            )}

            {/* The reference's three bouncing dots, not a spinner. */}
            {isLoading && (
              <div className="flex justify-start">
                <div className="rounded-lg rounded-bl-none bg-gray-200 px-4 py-2 text-gray-900">
                  <div className="flex space-x-2">
                    <div className="h-2 w-2 animate-bounce rounded-full bg-gray-500" />
                    <div className="h-2 w-2 animate-bounce rounded-full bg-gray-500" style={{ animationDelay: "0.2s" }} />
                    <div className="h-2 w-2 animate-bounce rounded-full bg-gray-500" style={{ animationDelay: "0.4s" }} />
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Suggestions stay reachable once a thread exists — this widget has
              them and the reference does not, so they borrow its button. */}
          {messages.length > 0 && suggestions.length > 0 && (
            <div className="flex shrink-0 flex-wrap gap-2 border-t border-gray-200 bg-gray-50 px-4 py-2">
              {suggestions.slice(0, 2).map((sug, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSendMessage(sug)}
                  disabled={isLoading}
                  className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs text-gray-700 transition-colors hover:border-app-brand-500 hover:text-app-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {sug}
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <div className="shrink-0 border-t border-gray-200 bg-white p-4">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSendMessage(inputMsg);
              }}
              className="flex gap-2"
            >
              <input
                type="text"
                value={inputMsg}
                onChange={(e) => setInputMsg(e.target.value)}
                placeholder="Type your message..."
                disabled={isLoading}
                className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none transition-colors focus:border-app-brand-500 focus:ring-1 focus:ring-app-brand-500 disabled:cursor-not-allowed disabled:bg-gray-100"
              />
              <button
                type="submit"
                disabled={isLoading || !inputMsg.trim()}
                className="rounded-lg bg-app-brand-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-app-brand-700 disabled:bg-gray-300"
                aria-label="Send message"
              >
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </button>
            </form>
          </div>
        </div>
      )}
    </>
  );
};
