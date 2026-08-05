"use client";

import React, { useEffect, useState, useRef, useMemo } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { 
  MessageSquare, X, Send, Trash2, Maximize2, Minimize2, 
  ThumbsUp, ThumbsDown, HelpCircle, ArrowRight, Check, 
  Loader2, Info, ChevronRight, CheckCircle2, Shield
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
      return <h4 key={idx} className="text-xs font-bold text-slate-800 mt-3 mb-1.5">{line.replace("### ", "")}</h4>;
    }
    if (line.startsWith("## ")) {
      return <h3 key={idx} className="text-sm font-bold text-slate-900 mt-4 mb-2">{line.replace("## ", "")}</h3>;
    }
    if (line.startsWith("# ")) {
      return <h2 key={idx} className="text-base font-bold text-slate-950 mt-5 mb-2.5">{line.replace("# ", "")}</h2>;
    }

    // 3. Check for Bullets
    if (line.trim().startsWith("•") || line.trim().startsWith("-") || line.trim().startsWith("*")) {
      const content = line.replace(/^[•\-*]\s*/, "");
      return (
        <li key={idx} className="list-disc list-inside text-xs text-slate-600 ml-3.5 my-1 leading-relaxed">
          {renderInlineStyles(content, projectId)}
        </li>
      );
    }

    // 4. Regular Paragraph
    return (
      <p key={idx} className="text-xs text-slate-600 leading-relaxed my-2">
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
    return splitParts.map((sub, i) => (i % 2 === 1 ? <strong key={i} className="font-semibold text-slate-800">{sub}</strong> : sub));
  });

  // 2. Process Code
  parts = parts.flatMap((part) => {
    if (typeof part !== "string") return part;
    const splitParts = part.split(codeRegex);
    return splitParts.map((sub, i) => (i % 2 === 1 ? <code key={i} className="bg-slate-100 text-slate-800 rounded px-1 py-0.5 text-[10px] font-mono">{sub}</code> : sub));
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
            className="text-[#1b59f8] hover:underline font-bold inline-flex items-center gap-0.5 select-all"
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
      {/* ── 1. Floating Launcher (Etisalat Need Help pill brand styling) ── */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 z-40 flex items-center gap-3.5 rounded-full bg-gradient-to-r from-[#43c7df] via-[#56aceb] to-[#7485f3] hover:from-[#2fb4d0] hover:via-[#459de2] hover:to-[#6676e8] text-white px-5 py-3 shadow-2xl shadow-[#56aceb]/25 transition-all duration-300 transform hover:scale-105 active:scale-95 shrink-0 select-none border border-white/20"
          aria-label="Open QAI Platform Assistant"
        >
          {/* AI Assistant Text */}
          <span className="text-sm font-bold tracking-wide pl-1 select-none">AI Assistant</span>

          {/* Divider */}
          <div className="w-px h-7 bg-white/30 shrink-0" />

          {/* Text */}
          <span className="text-sm font-bold tracking-wide pr-1">Need Help</span>
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
            "fixed z-50 bg-white shadow-2xl transition-all duration-300 flex flex-col focus:outline-none select-none",
            isWide 
              ? "inset-y-0 right-0 h-full w-full sm:max-w-xl md:max-w-2xl border-l border-slate-100" 
              : "bottom-6 right-6 w-[calc(100vw-32px)] sm:w-[380px] h-[580px] max-h-[calc(100vh-48px)] rounded-2xl border border-slate-200/80"
          )}
          role="dialog"
          aria-labelledby="assistant-title"
        >
          {/* Drawer Header (Sales Advisor Help themed) */}
          <div className={cn(
            "flex items-center justify-between border-b border-[#56aceb]/20 p-4 shrink-0 bg-gradient-to-r from-[#43c7df] via-[#56aceb] to-[#7485f3] text-white",
            !isWide && "rounded-t-2xl"
          )}>
            <div className="flex items-center gap-3 min-w-0">
              {/* Sales Advisor Avatar with Headset (High Fidelity SVG) */}
              <div className="shrink-0 relative">
                <svg viewBox="0 0 100 100" className="w-10 h-10 rounded-full bg-[#111] overflow-hidden border-2 border-white/20 shadow-sm">
                  {/* Hair (Back) */}
                  <path d="M20,60 C20,25 80,25 80,60" fill="#222" />
                  
                  {/* Face/Neck */}
                  <path d="M50,80 L50,60" stroke="#ffd9b3" strokeWidth="10" strokeLinecap="round" />
                  <circle cx="50" cy="45" r="22" fill="#ffd9b3" />
                  
                  {/* Face features */}
                  <circle cx="43" cy="43" r="2" fill="#333" />
                  <circle cx="57" cy="43" r="2" fill="#333" />
                  <circle cx="39" cy="49" r="2.5" fill="#ffa6a6" opacity="0.6" />
                  <circle cx="61" cy="49" r="2.5" fill="#ffa6a6" opacity="0.6" />
                  <path d="M46,52 Q50,55 54,52" stroke="#e07b7b" strokeWidth="1.5" strokeLinecap="round" fill="none" />

                  {/* Hair (Front/Bangs) */}
                  <path d="M28,45 C28,30 45,30 48,38 C49,40 50,45 50,50 L46,50 C44,45 36,45 28,45 Z" fill="#111" />
                  <path d="M72,45 C72,30 55,30 52,38 C51,40 50,45 50,50 L54,50 C56,45 64,45 72,45 Z" fill="#111" />
                  <path d="M25,43 C23,55 25,65 30,72 C33,76 33,80 33,80 L40,80 C36,70 34,60 34,43 Z" fill="#111" />
                  <path d="M75,43 C77,55 75,65 70,72 C67,76 67,80 67,80 L60,80 C64,70 66,60 66,43 Z" fill="#111" />

                  {/* Red Shirt */}
                  <path d="M20,95 C20,75 35,70 50,70 C65,70 80,75 80,95 Z" fill="#56aceb" />

                  {/* Headset */}
                  <path d="M28,43 C28,18 72,18 72,43" stroke="#e2e8f0" strokeWidth="4" fill="none" strokeLinecap="round" />
                  <rect x="25" y="38" width="6" height="12" rx="3" fill="#e2e8f0" />
                  <rect x="69" y="38" width="6" height="12" rx="3" fill="#e2e8f0" />
                  <path d="M69,45 L58,58" stroke="#e2e8f0" strokeWidth="2.5" strokeLinecap="round" />
                  <circle cx="58" cy="58" r="2.5" fill="#e2e8f0" />
                </svg>
                <span className="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full bg-emerald-500 border border-white" />
              </div>

              <div className="flex flex-col min-w-0">
                <h2 id="assistant-title" className="text-sm font-extrabold text-white leading-tight flex items-center gap-1.5">
                  <span>AI Assistance Help</span>
                </h2>
                <span className="text-[10px] text-white/80 font-medium">Replies instantly</span>
                
                {/* Show active context metadata only in wide expanded view */}
                {isWide && (
                  <div className="flex flex-wrap items-center gap-1 mt-1.5">
                    <span className="inline-flex items-center gap-1 bg-white/10 text-white px-2 py-0.5 rounded-md text-[9px] font-medium leading-none max-w-[130px] truncate">
                      <span className="h-1 w-1 rounded-full bg-white/60 shrink-0" />
                      Project: {activeProjectName}
                    </span>
                    <span className="inline-flex items-center gap-1 bg-white/20 text-white px-2 py-0.5 rounded-md text-[9px] font-medium leading-none">
                      <span className="h-1 w-1 rounded-full bg-emerald-400 shrink-0 animate-pulse" />
                      Page: {activePageLabel}
                    </span>
                  </div>
                )}
              </div>
            </div>
            
            <div className="flex items-center gap-1">
              {activeConversationId && (
                <button
                  onClick={handleClearConversation}
                  title="Clear current thread"
                  className="rounded-lg p-1.5 text-white/80 hover:bg-white/10 hover:text-white transition-colors"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
              <button
                onClick={() => setIsWide(!isWide)}
                title={isWide ? "Restore window size" : "Expand window size"}
                className="rounded-lg p-1.5 text-white/80 hover:bg-white/10 hover:text-white transition-colors hidden sm:block"
              >
                {isWide ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
              </button>
              <button
                onClick={() => setIsOpen(false)}
                className="rounded-lg p-1.5 text-white/80 hover:bg-white/10 hover:text-white transition-colors"
                aria-label="Close Assistant"
              >
                <X className="h-4.5 w-4.5" />
              </button>
            </div>
          </div>

          {/* Drawer Body - Scrollable chat thread */}
          <div 
            ref={scrollRef}
            className="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-50/30 scroll-smooth"
          >
            {/* Empty state suggestions */}
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center text-center py-10 px-4 space-y-4">
                <div className="h-12 w-12 rounded-2xl bg-gradient-to-tr from-[#43c7df] via-[#56aceb] to-[#7485f3] flex items-center justify-center shadow-lg shadow-[#56aceb]/25">
                  <MessageSquare className="h-6 w-6 text-white" />
                </div>
                <div className="space-y-1">
                  <h3 className="text-xs font-bold text-slate-800">Ask QAI anything</h3>
                  <p className="text-[10px] text-slate-400 max-w-xs leading-normal">
                    Ask questions about your STLC execution metrics, requirements review state, test case coverage, or platform workflows.
                  </p>
                </div>
                
                <div className="w-full space-y-2.5 mt-4 px-2">
                  <p className="text-[9px] font-extrabold text-slate-400 uppercase tracking-widest text-center">Suggested prompts for {activePageLabel}</p>
                  <div className="flex flex-col gap-2 w-full max-w-[320px] mx-auto">
                    {suggestions.map((s, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleSendMessage(s)}
                        disabled={isLoading}
                        className="w-full text-center text-[10px] bg-white border-2 border-black hover:bg-slate-50 disabled:bg-slate-50 disabled:text-slate-400 text-black rounded-full py-3.5 px-4 font-bold uppercase tracking-wider transition-all duration-200 shadow-sm"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Messages */}
            {messages.map((m, idx) => {
              const isUser = m.role === "user";
              const isSystem = m.role === "system";
              return (
                <div
                  key={m.id || idx}
                  className={cn(
                    "flex w-full mb-1",
                    isUser ? "justify-end" : "justify-start"
                  )}
                >
                  <div className={cn("flex items-start gap-2 max-w-[85%]", isUser && "flex-row-reverse")}>
                    {/* Small Assistant Avatar on Left */}
                    {!isUser && !isSystem && (
                      <div className="shrink-0 mt-0.5">
                        <svg viewBox="0 0 100 100" className="w-7 h-7 rounded-full bg-[#111] overflow-hidden border border-white/20 shadow-sm">
                          {/* Hair (Back) */}
                          <path d="M20,60 C20,25 80,25 80,60" fill="#222" />
                          
                          {/* Face/Neck */}
                          <path d="M50,80 L50,60" stroke="#ffd9b3" strokeWidth="10" strokeLinecap="round" />
                          <circle cx="50" cy="45" r="22" fill="#ffd9b3" />
                          
                          {/* Face features */}
                          <circle cx="43" cy="43" r="2" fill="#333" />
                          <circle cx="57" cy="43" r="2" fill="#333" />
                          <circle cx="39" cy="49" r="2.5" fill="#ffa6a6" opacity="0.6" />
                          <circle cx="61" cy="49" r="2.5" fill="#ffa6a6" opacity="0.6" />
                          <path d="M46,52 Q50,55 54,52" stroke="#e07b7b" strokeWidth="1.5" strokeLinecap="round" fill="none" />

                          {/* Hair (Front/Bangs) */}
                          <path d="M28,45 C28,30 45,30 48,38 C49,40 50,45 50,50 L46,50 C44,45 36,45 28,45 Z" fill="#111" />
                          <path d="M72,45 C72,30 55,30 52,38 C51,40 50,45 50,50 L54,50 C56,45 64,45 72,45 Z" fill="#111" />
                          <path d="M25,43 C23,55 25,65 30,72 C33,76 33,80 33,80 L40,80 C36,70 34,60 34,43 Z" fill="#111" />
                          <path d="M75,43 C77,55 75,65 70,72 C67,76 67,80 67,80 L60,80 C64,70 66,60 66,43 Z" fill="#111" />

                          {/* Red Shirt */}
                          <path d="M20,95 C20,75 35,70 50,70 C65,70 80,75 80,95 Z" fill="#56aceb" />

                          {/* Headset */}
                          <path d="M28,43 C28,18 72,18 72,43" stroke="#e2e8f0" strokeWidth="4" fill="none" strokeLinecap="round" />
                          <rect x="25" y="38" width="6" height="12" rx="3" fill="#e2e8f0" />
                          <rect x="69" y="38" width="6" height="12" rx="3" fill="#e2e8f0" />
                          <path d="M69,45 L58,58" stroke="#e2e8f0" strokeWidth="2.5" strokeLinecap="round" />
                          <circle cx="58" cy="58" r="2.5" fill="#e2e8f0" />
                        </svg>
                      </div>
                    )}

                    <div className="flex flex-col">
                      <div
                        className={cn(
                          "rounded-2xl px-3.5 py-2.5 text-xs shadow-xs leading-relaxed transition-all",
                          isUser 
                            ? "bg-[#1b59f8] text-white rounded-tr-none font-medium"
                            : isSystem
                              ? "bg-red-50 text-red-700 border border-red-100 rounded-tl-none font-medium"
                              : "bg-white text-slate-800 border border-slate-100 rounded-tl-none"
                        )}
                      >
                        {isUser ? (
                          <p className="whitespace-pre-wrap">{m.content}</p>
                        ) : (
                          <MarkdownText text={m.content} projectId={resolvedProjectId} />
                        )}
                      </div>

                      {/* Assistant footer & ratings */}
                      {!isUser && !isSystem && (
                        <div className="flex items-center justify-between w-full mt-1.5 px-1 text-[9px] text-slate-400 select-none gap-2">
                          <span className="inline-flex items-center gap-1 font-medium text-slate-300">
                            <Shield className="h-3 w-3 text-slate-300" />
                            Project-scoped & role-aware
                          </span>
                          <div className="flex items-center gap-1.5 ml-auto">
                            <button
                              onClick={() => submitFeedback(m.id, "helpful")}
                              disabled={feedbackRatings[m.id] !== undefined}
                              className={cn(
                                "p-0.5 rounded transition-colors hover:bg-slate-100",
                                feedbackRatings[m.id] === "helpful" ? "text-emerald-600 bg-emerald-50 hover:bg-emerald-50" : "text-slate-400"
                              )}
                              title="Helpful"
                            >
                              <ThumbsUp className="h-3.5 w-3.5" />
                            </button>
                            <button
                              onClick={() => submitFeedback(m.id, "unhelpful")}
                              disabled={feedbackRatings[m.id] !== undefined}
                              className={cn(
                                "p-0.5 rounded transition-colors hover:bg-slate-100",
                                feedbackRatings[m.id] === "unhelpful" ? "text-rose-600 bg-rose-50 hover:bg-rose-50" : "text-slate-400"
                              )}
                              title="Not helpful"
                            >
                              <ThumbsDown className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}

            {/* Loading bubble */}
            {isLoading && (
              <div className="flex w-full mb-1 justify-start">
                <div className="flex items-start gap-2 max-w-[85%]">
                  <div className="shrink-0 mt-0.5">
                    <svg viewBox="0 0 100 100" className="w-7 h-7 rounded-full bg-[#111] overflow-hidden border border-white/20 shadow-sm animate-pulse">
                      {/* Hair (Back) */}
                      <path d="M20,60 C20,25 80,25 80,60" fill="#222" />
                      
                      {/* Face/Neck */}
                      <path d="M50,80 L50,60" stroke="#ffd9b3" strokeWidth="10" strokeLinecap="round" />
                      <circle cx="50" cy="45" r="22" fill="#ffd9b3" />
                      
                      {/* Face features */}
                      <circle cx="43" cy="43" r="2" fill="#333" />
                      <circle cx="57" cy="43" r="2" fill="#333" />
                      <circle cx="39" cy="49" r="2.5" fill="#ffa6a6" opacity="0.6" />
                      <circle cx="61" cy="49" r="2.5" fill="#ffa6a6" opacity="0.6" />
                      <path d="M46,52 Q50,55 54,52" stroke="#e07b7b" strokeWidth="1.5" strokeLinecap="round" fill="none" />

                      {/* Hair (Front/Bangs) */}
                      <path d="M28,45 C28,30 45,30 48,38 C49,40 50,45 50,50 L46,50 C44,45 36,45 28,45 Z" fill="#111" />
                      <path d="M72,45 C72,30 55,30 52,38 C51,40 50,45 50,50 L54,50 C56,45 64,45 72,45 Z" fill="#111" />
                      <path d="M25,43 C23,55 25,65 30,72 C33,76 33,80 33,80 L40,80 C36,70 34,60 34,43 Z" fill="#111" />
                      <path d="M75,43 C77,55 75,65 70,72 C67,76 67,80 67,80 L60,80 C64,70 66,60 66,43 Z" fill="#111" />

                      {/* Red Shirt */}
                      <path d="M20,95 C20,75 35,70 50,70 C65,70 80,75 80,95 Z" fill="#56aceb" />

                      {/* Headset */}
                      <path d="M28,43 C28,18 72,18 72,43" stroke="#e2e8f0" strokeWidth="4" fill="none" strokeLinecap="round" />
                      <rect x="25" y="38" width="6" height="12" rx="3" fill="#e2e8f0" />
                      <rect x="69" y="38" width="6" height="12" rx="3" fill="#e2e8f0" />
                      <path d="M69,45 L58,58" stroke="#e2e8f0" strokeWidth="2.5" strokeLinecap="round" />
                      <circle cx="58" cy="58" r="2.5" fill="#e2e8f0" />
                    </svg>
                  </div>
                  <div className="rounded-2xl rounded-tl-none bg-white border border-slate-100 px-4 py-3 shadow-xs flex items-center gap-2">
                    <Loader2 className="h-4 w-4 text-[#1b59f8] animate-spin" />
                    <span className="text-[10px] font-medium text-slate-400">QAI is thinking...</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Dynamic suggestion chips list when drawer has content (Vertically Stacked, Etisalat styled) */}
          {messages.length > 0 && suggestions.length > 0 && (
            <div className="px-4 py-3 bg-slate-50 border-t border-slate-100/80 shrink-0 select-none flex flex-col gap-2">
              {suggestions.slice(0, 2).map((s, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSendMessage(s)}
                  disabled={isLoading}
                  className="w-full text-center text-[10px] bg-white border-2 border-black hover:bg-slate-50 disabled:bg-slate-50 disabled:text-slate-400 text-black rounded-full py-2.5 px-4 font-bold uppercase tracking-wider transition-all duration-200 shadow-sm"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {/* Drawer Footer - Message Input */}
          <div className={cn(
            "border-t border-slate-100 p-4 shrink-0 bg-white flex items-center gap-2",
            !isWide && "rounded-b-2xl"
          )}>
            <input
              type="text"
              value={inputMsg}
              onChange={(e) => setInputMsg(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSendMessage(inputMsg);
              }}
              placeholder="Type your question about QAI..."
              className="flex-1 rounded-xl border border-slate-200 hover:border-slate-300 focus:border-[#1b59f8] focus:ring-2 focus:ring-blue-100/30 text-xs px-3.5 py-2.5 focus:outline-none transition-all placeholder:text-slate-400"
              disabled={isLoading}
            />
            <button
              onClick={() => handleSendMessage(inputMsg)}
              disabled={!inputMsg.trim() || isLoading}
              className="h-9 w-9 flex items-center justify-center rounded-xl bg-[#1b59f8] hover:bg-blue-700 disabled:bg-slate-100 text-white disabled:text-slate-300 shadow-md transition-colors"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </>
  );
};
