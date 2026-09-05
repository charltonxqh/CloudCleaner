"use client";

import {
  type EvaluationMetrics,
  type EventStats,
} from "@/lib/api";

function percent(value: number | null) {
  return value === null ? "Not captured" : `${Math.round(value * 100)}%`;
}

function EvaluationCard({
  label,
  value,
  description,
  sample,
  tone,
}: {
  label: string;
  value: string;
  description: string;
  sample?: string;
  tone?: string;
}) {
  return (
    <div
      className="min-h-[210px] px-6 py-6"
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
      }}
    >
      <div
        className="text-[14px] font-semibold uppercase tracking-[0.06em]"
        style={{ color: "var(--fg-muted)" }}
      >
        {label}
      </div>

      <div
        className="num mt-4 text-[36px] font-semibold leading-none tracking-tight"
        style={{ color: tone ?? "var(--fg)" }}
      >
        {value}
      </div>

      <p
        className="mt-4 text-[14px] leading-relaxed"
        style={{ color: "var(--fg-muted)" }}
      >
        {description}
      </p>

      {sample && (
        <div
          className="mt-4 text-[12px] leading-relaxed"
          style={{ color: "var(--fg-faint)" }}
        >
          {sample}
        </div>
      )}
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
        <h2 className="text-[20px] font-semibold">
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