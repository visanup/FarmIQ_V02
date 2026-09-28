type Outcome = 'resolved' | 'unassigned' | 'ambiguous' | 'override'

const counts: Record<Outcome, number> = {
  resolved: 0,
  unassigned: 0,
  ambiguous: 0,
  override: 0,
}

export function recordBatchContextResolution(outcome: Outcome): void {
  counts[outcome] += 1
}

export function renderBatchContextMetrics(): string {
  const rows = Object.entries(counts)
    .map(([outcome, count]) => `edge_weighvision_session_batch_context_resolution_total{outcome="${outcome}"} ${count}`)
  return [
    '# HELP edge_weighvision_session_batch_context_resolution_total Session batch-context resolution outcomes',
    '# TYPE edge_weighvision_session_batch_context_resolution_total counter',
    ...rows,
    '',
  ].join('\n')
}
