import type { TaskInfo, TaskStatus } from '../types/analysis';

export interface ReconcileDeps {
  /** Fetch ground-truth status for a task id (backend). */
  getStatus: (taskId: string) => Promise<TaskStatus>;
  /** Called when a task is actually completed (mirrors the SSE handler). */
  onCompleted: (task: TaskInfo) => void;
  /** Called when a task has actually failed. */
  onFailed: (task: TaskInfo) => void;
  /** Called to refresh a still-running task's progress/state. */
  onProgress: (task: TaskInfo) => void;
}

/**
 * Poll the backend for the real status of each active task and reconcile.
 *
 * `activeTasks` transitions normally ride on SSE `task_*` events, but SSE has
 * no replay: if the connection drops during a multi-minute analysis and the
 * `task_completed` event is missed on reconnect, the task is orphaned in the
 * "分析中" list forever — the 2s auto-removal in the SSE `onTaskCompleted`
 * handler never fires because the event never arrived. This poll is the safety
 * net: it asks the backend for ground truth and drives the SAME
 * completed/failed/progress callbacks the SSE path would have, so a stuck task
 * clears on the next tick instead of hanging until a page reload.
 *
 * Pure & dependency-injected so it can be unit-tested without a live SSE
 * connection, timers, or the zustand store (see repo-web-test-infra-gaps).
 * A per-task getStatus rejection is swallowed — the task is left untouched and
 * the next tick retries.
 */
export async function reconcileActiveTasks(
  tasks: readonly TaskInfo[],
  deps: ReconcileDeps,
): Promise<void> {
  const pending = tasks.filter(
    (t) => t.status === 'pending' || t.status === 'processing',
  );
  await Promise.all(
    pending.map(async (task) => {
      let status: TaskStatus;
      try {
        status = await deps.getStatus(task.taskId);
      } catch {
        return; // transient error — leave the task; next tick retries
      }
      const merged: TaskInfo = {
        ...task,
        status: status.status,
        progress: status.progress ?? task.progress,
        stockName: status.stockName ?? task.stockName,
        error: status.error ?? task.error,
        result: status.result ?? task.result,
      };
      if (status.status === 'completed') {
        deps.onCompleted(merged);
      } else if (status.status === 'failed') {
        deps.onFailed(merged);
      } else {
        deps.onProgress(merged);
      }
    }),
  );
}
