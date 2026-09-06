"use client";

import {
  type EvaluationMetrics,
  type EventStats,
} from "@/lib/api";

function percent(value: number | null) {
  return value === null ? "Not captured" : `${Math.round(value * 100)}%`;
}

/** Each metric takes its own cosmic accent, so a wall of identical cards reads
 *  as six distinct measures rather than one repeated block. */
const ACCENTS = [
  { line: "var(--green-on-dark)", wash: "rgb(103 227 196 / 0.07)" },
  { line: "var(--blue-on-dark)", wash: "rgb(144 170 255 / 0.07)" },
  { line: "var(--yellow-on-dark)", wash: "rgb(255 215 110 / 0.07)" },
  { line: "var(--pink-on-dark)", wash: "rgb(255 157 192 / 0.07)" },
  { line: "#b9a3ff", wash: "rgb(185 163 255 / 0.07)" },
  { line: "#7fd8ff", wash: "rgb(127 216 255 / 0.07)" },
];

function EvaluationCard({
  label,
  value,
  description,
  sample,
  tone,
  index = 0,
}: {
  label: string;
  value: string;
  description: string;
  sample?: string;
  tone?: string;
  index?: number;
}) {
  const accent = ACCENTS[index % ACCENTS.length];
  // A metric with nothing behind it should look dormant, not merely quiet.
  const captured = !/not captured/i.test(value);

  return (
    <div className="pixel-shadow h-full">
      <div
        className="pixel-card flex h-full min-h-[214px] flex-col px-6 py-5"
        style={{
          background: captured
            ? `linear-gradient(180deg, ${accent.wash}, transparent 60%), var(--surface)`
            : "var(--surface)",
          borderTop: `3px solid ${captured ? accent.line : "var(--border-strong)"}`,
        }}
      >
        <div className="label" style={{ color: captured ? accent.line : "var(--fg-faint)" }}>
          {label}
        </div>

        <div
          className={`${captured ? "num" : "pixel-type"} mt-3 leading-none tracking-tight`}
          style={{
            color: captured ? tone ?? accent.line : "var(--fg-faint)",
            fontSize: captured ? 40 : 26,
            fontWeight: captured ? 600 : undefined,
          }}
        >
          {value}
        </div>

        <div className="pixel-rule mt-4" style={{ color: accent.line }} />

        <p className="mt-3.5 text-[13.5px] leading-relaxed" style={{ color: "var(--fg-muted)" }}>
          {description}
        </p>

        {sample && (
          <div
            className="mt-auto pt-4 text-[12px] leading-relaxed"
            style={{ color: captured ? "var(--fg-faint)" : accent.line, opacity: captured ? 1 : 0.75 }}
          >
            {sample}
          </div>
        )}
      </div>
    </div>
  );
}

export function EvaluationView({
  evaluation,
  stats,
}: {
  evaluation: EvaluationMetrics | null;
  stats: EventStats | null;
}) {
  const schemaRate =
    evaluation?.schema_validation_rate ??
    stats?.llm_success_rate ??
    null;

  return (
    <div className="h-full overflow-auto p-6">
      <div className="mb-6">
        <h2 className="pixel-type text-[26px]">
          Agent performance
        </h2>

        <p
          className="mt-2 max-w-[900px] text-[14px] leading-relaxed"
          style={{ color: "var(--fg-muted)" }}
        >
          Measures recommendation quality, model reliability, tool execution,
          teardown safety, and financial accuracy across CloudCleaner runs.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <EvaluationCard
          index={0}
          label="Recommendation accuracy"
          value={percent(evaluation?.recommendation_accuracy ?? null)}
          description="How often CloudCleaner chooses the correct KEEP, STOP, RETIRE, or INVESTIGATE MORE verdict against an independently labelled benchmark."
          sample={
            evaluation?.recommendation_samples
              ? `${evaluation.recommendation_samples} labelled benchmark samples`
              : "Requires an independently labelled benchmark dataset"
          }
        />

        <EvaluationCard
          index={1}
          label="LLM output success"
          value={percent(schemaRate)}
          description="How often the model successfully returns a valid structured recommendation without CloudCleaner falling back to deterministic rules."
          sample={
            evaluation
              ? `${evaluation.schema_validation_samples} model assessments`
              : stats
                ? `${stats.assessments} model assessments`
                : "No assessments recorded"
          }
          tone={
            schemaRate !== null && schemaRate >= 0.9
              ? "var(--ok)"
              : undefined
          }
        />

        <EvaluationCard
          index={2}
          label="Token cost per run"
          value={
            evaluation?.avg_token_cost_usd === null ||
            evaluation?.avg_token_cost_usd === undefined
              ? "Not captured"
              : `$${evaluation.avg_token_cost_usd.toFixed(4)}`
          }
          description="Average LLM inference cost for one CloudCleaner investigation, calculated from prompt and completion token usage."
          sample={
            evaluation?.token_cost_samples
              ? `${evaluation.token_cost_samples} measured model runs`
              : "Token usage is not persisted yet"
          }
        />

        <EvaluationCard
          index={3}
          label="Tool-call success rate"
          value={percent(evaluation?.tool_call_success_rate ?? null)}
          description="How often instrumented external operations such as evidence retrieval, AWS execution, and owner notification complete successfully."
          sample={
            evaluation?.tool_call_attempts
              ? `${evaluation.tool_call_successes} of ${evaluation.tool_call_attempts} instrumented calls succeeded`
              : "No instrumented tool calls recorded yet"
          }
          tone={
            evaluation?.tool_call_success_rate !== null &&
            evaluation?.tool_call_success_rate !== undefined &&
            evaluation.tool_call_success_rate >= 0.9
              ? "var(--ok)"
              : undefined
          }
        />

        <EvaluationCard
          index={4}
          label="Teardown-plan correctness"
          value={percent(evaluation?.teardown_plan_correctness ?? null)}
          description="Whether retirement plans contain a valid dependency-safe action sequence and complete successfully when approved."
          sample={
            evaluation?.teardown_plan_samples
              ? `${evaluation.teardown_plan_correct} of ${evaluation.teardown_plan_samples} evaluated plans`
              : "No eligible retirement plans recorded yet"
          }
          tone={
            evaluation?.teardown_plan_correctness !== null &&
            evaluation?.teardown_plan_correctness !== undefined &&
            evaluation.teardown_plan_correctness >= 0.9
              ? "var(--ok)"
              : undefined
          }
        />

        <EvaluationCard
          index={5}
          label="Savings accuracy"
          value={percent(evaluation?.savings_accuracy ?? null)}
          description="How closely CloudCleaner's predicted monthly saving matches the independently calculable billed amount for the affected resource."
          sample={
            evaluation?.savings_accuracy_samples
              ? `${evaluation.savings_accuracy_samples} cost comparisons`
              : "No eligible cost comparisons recorded yet"
          }
          tone={
            evaluation?.savings_accuracy !== null &&
            evaluation?.savings_accuracy !== undefined &&
            evaluation.savings_accuracy >= 0.9
              ? "var(--ok)"
              : undefined
          }
        />
      </div>
    </div>
  );
}