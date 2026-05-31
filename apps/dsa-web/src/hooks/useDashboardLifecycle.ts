import { useEffect, useRef } from 'react';
import type { TaskInfo } from '../types/analysis';
import { useTaskStream } from './useTaskStream';
import { reconcileActiveTasks } from './reconcileActiveTasks';
import { analysisApi } from '../api/analysis';

type UseDashboardLifecycleOptions = {
  loadInitialHistory: () => Promise<void>;
  refreshHistory: (silent?: boolean) => Promise<void>;
  syncTaskCreated: (task: TaskInfo) => void;
  syncTaskUpdated: (task: TaskInfo) => void;
  syncTaskCompleted: (task: TaskInfo) => void;
  syncTaskFailed: (task: TaskInfo) => void;
  removeTask: (taskId: string) => void;
  /**
   * Snapshot accessor for the current active-task list. When provided, a
   * background poll reconciles these tasks against backend ground truth so a
   * missed SSE `task_completed` event (connection dropped mid-analysis) no
   * longer strands a task in the "分析中" list. Optional for backward compat.
   */
  getActiveTasks?: () => TaskInfo[];
  enabled?: boolean;
};

/** How often the safety-net poll reconciles active tasks with the backend. */
const RECONCILE_INTERVAL_MS = 15_000;

export function useDashboardLifecycle({
  loadInitialHistory,
  refreshHistory,
  syncTaskCreated,
  syncTaskUpdated,
  syncTaskCompleted,
  syncTaskFailed,
  removeTask,
  getActiveTasks,
  enabled = true,
}: UseDashboardLifecycleOptions): void {
  const removalTimeoutsRef = useRef<number[]>([]);

  const scheduleTaskRemoval = (taskId: string, delayMs: number) => {
    const timeoutId = window.setTimeout(() => {
      removeTask(taskId);
      removalTimeoutsRef.current = removalTimeoutsRef.current.filter((item) => item !== timeoutId);
    }, delayMs);

    removalTimeoutsRef.current.push(timeoutId);
  };

  // Shared terminal-state handlers so the SSE path and the reconciliation poll
  // behave identically (auto-select report, refresh history, schedule removal).
  const handleCompleted = (task: TaskInfo) => {
    // syncTaskCompleted both updates the activeTasks list AND auto-selects the
    // just-finished report (including 24h cache-hit short-circuits) so the user
    // sees their result without having to click into history.
    syncTaskCompleted(task);
    void refreshHistory(true);
    scheduleTaskRemoval(task.taskId, 2_000);
  };
  const handleFailed = (task: TaskInfo) => {
    syncTaskFailed(task);
    scheduleTaskRemoval(task.taskId, 5_000);
  };

  // "Latest ref" so the reconcile interval always runs against fresh closures
  // (getActiveTasks / handlers) without re-creating the timer every render.
  // Assigned inside an effect (not during render) — mirrors the connectRef
  // pattern in useTaskStream and keeps react-hooks/refs happy.
  const reconcileRef = useRef<() => void>(() => {});
  useEffect(() => {
    reconcileRef.current = () => {
      if (!getActiveTasks) return;
      void reconcileActiveTasks(getActiveTasks(), {
        getStatus: analysisApi.getStatus,
        onCompleted: handleCompleted,
        onFailed: handleFailed,
        onProgress: syncTaskUpdated,
      });
    };
  });

  useEffect(() => {
    if (!enabled) {
      return;
    }

    void loadInitialHistory();
  }, [enabled, loadInitialHistory]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void refreshHistory(true);
    }, 30_000);

    return () => window.clearInterval(intervalId);
  }, [enabled, refreshHistory]);

  // Safety-net reconciliation: SSE has no event replay, so a connection drop
  // during a multi-minute analysis can lose `task_completed` and strand a task
  // in "分析中" forever. This poll asks the backend for ground truth and clears
  // such orphans on the next tick.
  useEffect(() => {
    if (!enabled) {
      return;
    }

    const intervalId = window.setInterval(() => {
      reconcileRef.current();
    }, RECONCILE_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, [enabled]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void refreshHistory(true);
        // Returning to the tab is a natural moment to reconcile any task whose
        // completion event was missed while the connection was backgrounded.
        reconcileRef.current();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [enabled, refreshHistory]);

  useEffect(() => {
    return () => {
      removalTimeoutsRef.current.forEach((timeoutId) => window.clearTimeout(timeoutId));
      removalTimeoutsRef.current = [];
    };
  }, []);

  useTaskStream({
    onTaskCreated: syncTaskCreated,
    onTaskStarted: syncTaskUpdated,
    onTaskProgress: syncTaskUpdated,
    onTaskCompleted: handleCompleted,
    onTaskFailed: handleFailed,
    onError: () => {
      console.warn('SSE connection disconnected, reconnecting...');
    },
    enabled,
  });
}

export default useDashboardLifecycle;
