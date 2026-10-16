import React, { useState, useEffect, useCallback } from "react";
import {
  SparklesIcon,
  AlertTriangleIcon,
  CheckCircle2Icon,
  InfoIcon,
  RefreshIcon,
  LayersIcon,
} from "./DashboardIcons";
import {
  AgentMessageRequest,
  AgentMessageResponse,
  AgentStatusResponse,
} from "@/types/api";
import { sendAgentMessage, getAgentStatus, ApiError } from "@/lib/api";

interface RecyclingAgentPanelProps {
  canQuery?: boolean;
}

const PRESET_QUESTIONS = [
  "Which bins are approaching their configured capacity?",
  "What material types have recently been confirmed?",
  "Which batch items need manual review?",
  "What should the operator prioritize next?",
  "Guidance for battery disposal",
];

export const RecyclingAgentPanel: React.FC<RecyclingAgentPanelProps> = ({
  canQuery = true,
}) => {
  const [inputMessage, setInputMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<AgentMessageResponse | null>(null);
  const [agentStatus, setAgentStatus] = useState<AgentStatusResponse | null>(null);
  const [showEvidence, setShowEvidence] = useState(false);
  const [lastQuery, setLastQuery] = useState<string | null>(null);

  // Load agent status on mount
  useEffect(() => {
    let active = true;
    getAgentStatus()
      .then((status) => {
        if (active) setAgentStatus(status);
      })
      .catch(() => {
        if (active) {
          setAgentStatus({
            enabled: false,
            agent_mode: "deterministic_fallback",
            provider_configured: false,
            model: null,
            base_url: null,
            available_tools: [
              "get_digital_twin_snapshot",
              "get_bin_status",
              "get_recent_events",
              "get_batch_review_summary",
              "get_material_guidance",
            ],
          });
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const handleSendMessage = useCallback(
    async (messageToSend?: string) => {
      const q = (messageToSend ?? inputMessage).trim();
      if (!q || isLoading || !canQuery) return;

      setIsLoading(true);
      setError(null);
      setLastQuery(q);

      try {
        const payload: AgentMessageRequest = { message: q };
        const res = await sendAgentMessage(payload);
        setResponse(res);
        if (!messageToSend) {
          setInputMessage("");
        }
      } catch (err) {
        setError(
          err instanceof ApiError
            ? err.message
            : "Failed to communicate with the Recycling Intelligence Agent."
        );
      } finally {
        setIsLoading(false);
      }
    },
    [inputMessage, isLoading, canQuery]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSendMessage();
    }
  };

  const isLiveLLM = response?.agent_mode === "live_llm" || agentStatus?.agent_mode === "live_llm";

  return (
    <section aria-labelledby="agent-title" className="space-y-3">
      {/* Header bar */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <SparklesIcon className="w-4 h-4 text-brand-600 dark:text-brand-400" />
          <h2
            id="agent-title"
            className="text-sm font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400"
          >
            Recycling Intelligence Agent
          </h2>
        </div>

        {/* Operational Mode Badge */}
        <div>
          {isLiveLLM ? (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Live GenAI
            </span>
          ) : (
            <span
              className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border border-slate-200 dark:border-slate-700"
              title="Provider unconfigured; grounded deterministic operational rules active."
            >
              <InfoIcon className="w-3 h-3 text-slate-500" />
              Deterministic Fallback
            </span>
          )}
        </div>
      </div>

      {/* Main Agent Card */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl p-4 border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
        {/* Preset Prompt Suggestions */}
        <div className="space-y-1.5">
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            Quick Queries
          </p>
          <div className="flex flex-wrap gap-1.5">
            {PRESET_QUESTIONS.map((question) => (
              <button
                key={question}
                type="button"
                onClick={() => {
                  setInputMessage(question);
                  void handleSendMessage(question);
                }}
                disabled={isLoading || !canQuery}
                className="text-left text-[11px] px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {question}
              </button>
            ))}
          </div>
        </div>

        {/* Input & Submit Bar */}
        <div className="flex gap-2">
          <input
            type="text"
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about bin capacities, confirmed flow, batch reviews..."
            disabled={isLoading || !canQuery}
            className="flex-1 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-950 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
          />
          <button
            type="button"
            onClick={() => handleSendMessage()}
            disabled={!inputMessage.trim() || isLoading || !canQuery}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold shadow-xs disabled:opacity-50 disabled:cursor-not-allowed transition-all active:scale-98 shrink-0"
          >
            {isLoading ? (
              <>
                <RefreshIcon className="w-3.5 h-3.5 animate-spin" />
                <span>Querying...</span>
              </>
            ) : (
              <>
                <SparklesIcon className="w-3.5 h-3.5" />
                <span>Ask Agent</span>
              </>
            )}
          </button>
        </div>

        {/* Provider transparency banner when running in fallback */}
        {!agentStatus?.provider_configured && (
          <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-800 text-[11px] text-slate-500 dark:text-slate-400 flex items-start gap-2">
            <InfoIcon className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
            <p>
              GenAI provider is not configured. The agent operates using grounded deterministic
              operational rules backed by live database state.
            </p>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div
            role="alert"
            className="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/50 border border-rose-200 dark:border-rose-900 text-rose-800 dark:text-rose-200 text-xs flex items-start justify-between gap-2"
          >
            <div className="flex items-start gap-2">
              <AlertTriangleIcon className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold">Query Failed</p>
                <p className="text-[11px] mt-0.5 text-rose-700 dark:text-rose-300">{error}</p>
              </div>
            </div>
            {lastQuery && (
              <button
                type="button"
                onClick={() => void handleSendMessage(lastQuery)}
                className="px-2 py-1 rounded bg-rose-600 text-white text-[10px] font-semibold hover:bg-rose-500 shrink-0"
              >
                Retry
              </button>
            )}
          </div>
        )}

        {/* Loading State Skeleton */}
        {isLoading && (
          <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-100 dark:border-slate-800 animate-pulse space-y-2">
            <div className="h-3 bg-slate-200 dark:bg-slate-800 rounded w-1/3" />
            <div className="h-2.5 bg-slate-200 dark:bg-slate-800 rounded w-full" />
            <div className="h-2.5 bg-slate-200 dark:bg-slate-800 rounded w-4/5" />
          </div>
        )}

        {/* Response Display */}
        {response && !isLoading && (
          <div className="space-y-3 pt-2 border-t border-slate-100 dark:border-slate-800">
            {/* Answer Body */}
            <div className="text-xs text-slate-800 dark:text-slate-200 leading-relaxed whitespace-pre-line">
              {response.answer}
            </div>

            {/* Recommended Action Box */}
            {response.recommended_action && (
              <div className="p-3 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 text-amber-900 dark:text-amber-200 text-xs flex items-start gap-2.5">
                <CheckCircle2Icon className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                <div className="space-y-0.5">
                  <span className="font-bold uppercase tracking-wider text-[10px] text-amber-700 dark:text-amber-300">
                    Recommended Operator Action (Advisory Only)
                  </span>
                  <p className="text-xs leading-normal">{response.recommended_action}</p>
                </div>
              </div>
            )}

            {/* Tool Evidence Section */}
            {response.tool_calls && response.tool_calls.length > 0 && (
              <div className="pt-2 border-t border-slate-100 dark:border-slate-800/60 text-[11px] space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-400 flex items-center gap-1">
                    <LayersIcon className="w-3 h-3 text-slate-400" />
                    Queried Tools ({response.tool_calls.length})
                  </span>
                  <button
                    type="button"
                    onClick={() => setShowEvidence((prev) => !prev)}
                    className="text-[10px] font-semibold text-brand-600 dark:text-brand-400 hover:underline"
                  >
                    {showEvidence ? "Hide Details" : "Show Evidence"}
                  </button>
                </div>

                {/* Evidence Pills */}
                <div className="flex flex-wrap gap-1">
                  {response.tool_calls.map((tc, idx) => (
                    <span
                      key={idx}
                      className="px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 font-mono text-[10px] text-slate-600 dark:text-slate-300"
                    >
                      {tc.tool_name}
                    </span>
                  ))}
                </div>

                {/* Expanded Evidence Details */}
                {showEvidence && (
                  <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 space-y-2 text-[10px] text-slate-600 dark:text-slate-300">
                    {response.tool_calls.map((tc, idx) => (
                      <div key={idx} className="space-y-0.5">
                        <span className="font-bold text-slate-900 dark:text-slate-100 font-mono">
                          {tc.tool_name}
                        </span>
                        <p className="text-slate-500 dark:text-slate-400">{tc.summary}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Metadata Footer */}
            <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono pt-1">
              <span>
                Source: {response.is_fallback ? "Deterministic Fallback" : response.model_identifier || "Live LLM"}
              </span>
              <span>{new Date(response.timestamp).toLocaleTimeString()}</span>
            </div>
          </div>
        )}

        {/* Empty State */}
        {!response && !isLoading && !error && (
          <div className="text-center py-4 text-slate-400 space-y-1">
            <SparklesIcon className="w-6 h-6 mx-auto text-slate-300 dark:text-slate-600" />
            <p className="text-xs font-semibold text-slate-600 dark:text-slate-300">
              Operational Assistant Ready
            </p>
            <p className="text-[11px] max-w-xs mx-auto">
              Select a quick query above or type a question to inspect bin capacity, verified flow, or batch review queues.
            </p>
          </div>
        )}
      </div>
    </section>
  );
};
