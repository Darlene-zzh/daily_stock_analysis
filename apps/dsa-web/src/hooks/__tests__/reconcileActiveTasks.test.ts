import { describe, it, expect, vi } from 'vitest';
import { reconcileActiveTasks } from '../reconcileActiveTasks';
import type { TaskInfo, TaskStatus } from '../../types/analysis';

function task(id: string, status: TaskInfo['status'], progress = 0): TaskInfo {
  return {
    taskId: id,
    stockCode: 'MSFT',
    status,
    progress,
    reportType: 'full',
    createdAt: '2026-05-31T03:50:00Z',
  };
}

function deps(getStatus: (id: string) => Promise<TaskStatus>) {
  return {
    getStatus,
    onCompleted: vi.fn(),
    onFailed: vi.fn(),
    onProgress: vi.fn(),
  };
}

describe('reconcileActiveTasks', () => {
  it('completes a task the backend reports done (missed SSE event)', async () => {
    const d = deps(async (id) => ({
      taskId: id,
      status: 'completed',
      progress: 100,
      result: { report: { code: 'MSFT' } } as never,
    }));
    await reconcileActiveTasks([task('t1', 'processing', 58)], d);
    expect(d.onCompleted).toHaveBeenCalledTimes(1);
    const arg = d.onCompleted.mock.calls[0][0];
    expect(arg.status).toBe('completed');
    expect(arg.result).toBeTruthy();
    expect(d.onProgress).not.toHaveBeenCalled();
    expect(d.onFailed).not.toHaveBeenCalled();
  });

  it('fails a task the backend reports failed', async () => {
    const d = deps(async (id) => ({ taskId: id, status: 'failed', error: 'boom' }));
    await reconcileActiveTasks([task('t1', 'processing', 30)], d);
    expect(d.onFailed).toHaveBeenCalledTimes(1);
    expect(d.onFailed.mock.calls[0][0].error).toBe('boom');
    expect(d.onCompleted).not.toHaveBeenCalled();
  });

  it('refreshes progress for a still-running task', async () => {
    const d = deps(async (id) => ({ taskId: id, status: 'processing', progress: 72 }));
    await reconcileActiveTasks([task('t1', 'processing', 58)], d);
    expect(d.onProgress).toHaveBeenCalledTimes(1);
    expect(d.onProgress.mock.calls[0][0].progress).toBe(72);
    expect(d.onCompleted).not.toHaveBeenCalled();
  });

  it('ignores already-terminal tasks (only polls pending/processing)', async () => {
    const getStatus = vi.fn(async (id: string) => ({ taskId: id, status: 'completed' as const }));
    const d = { getStatus, onCompleted: vi.fn(), onFailed: vi.fn(), onProgress: vi.fn() };
    await reconcileActiveTasks([task('done', 'completed'), task('bad', 'failed')], d);
    expect(getStatus).not.toHaveBeenCalled();
  });

  it('swallows a getStatus error and leaves the task untouched', async () => {
    const d = deps(async () => {
      throw new Error('network');
    });
    await reconcileActiveTasks([task('t1', 'processing', 58)], d);
    expect(d.onCompleted).not.toHaveBeenCalled();
    expect(d.onFailed).not.toHaveBeenCalled();
    expect(d.onProgress).not.toHaveBeenCalled();
  });

  it('reconciles a mixed batch independently', async () => {
    const d = deps(async (id) => {
      if (id === 'a') return { taskId: id, status: 'completed', result: { report: {} } as never };
      if (id === 'b') return { taskId: id, status: 'failed', error: 'x' };
      return { taskId: id, status: 'processing', progress: 40 };
    });
    await reconcileActiveTasks(
      [task('a', 'processing'), task('b', 'pending'), task('c', 'processing')],
      d,
    );
    expect(d.onCompleted).toHaveBeenCalledTimes(1);
    expect(d.onFailed).toHaveBeenCalledTimes(1);
    expect(d.onProgress).toHaveBeenCalledTimes(1);
  });
});
