import camelcaseKeys from 'camelcase-keys';

/**
 * Paths kept in snake_case across every API response. Mirrors the contract in
 * `apps/dsa-web/src/types/analysis.ts:529-591` — the FactBundle wire body is
 * authored snake_case (basis_fact_id, display_value, applicable_strategies,
 * distance_pct_from_current, ...) and must remain so for Phase 4 components
 * (EvidenceRef, EvidenceExpansion, PriceMapCard, useFactBundle) to read it.
 *
 * The outer key `fact_bundle` itself still gets camelcased to `factBundle` —
 * `stopPaths` halts traversal AFTER the path resolves, not at the path key.
 */
const DEFAULT_STOP_PATHS: readonly string[] = [
    'dashboard.fact_bundle',
    'report.dashboard.fact_bundle',
];

/**
 * 将 snake_case 对象键转换为 camelCase
 * @param data API 响应数据 (snake_case)
 * @returns 转换后的 camelCase 对象
 */
export function toCamelCase<T>(data: unknown): T {
    if (data === null || data === undefined) {
        return data as T;
    }
    return camelcaseKeys(data as Record<string, unknown>, {
        deep: true,
        stopPaths: DEFAULT_STOP_PATHS,
    }) as T;
}
