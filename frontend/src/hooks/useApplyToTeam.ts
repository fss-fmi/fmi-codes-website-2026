import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useToast } from '@/components/common/useToast';
import api from '@/lib/api';

export interface UseApplyToTeamResult {
  applyingTo: number | null;
  appliedSet: Set<number>;
  applyToTeam: (teamId: number) => Promise<void>;
  isApplied: (teamId: number) => boolean;
  isApplying: (teamId: number) => boolean;
}

export function useApplyToTeam(invalidateKey?: unknown[]): UseApplyToTeamResult {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const [applyingTo, setApplyingTo] = useState<number | null>(null);
  const [appliedSet, setAppliedSet] = useState<Set<number>>(new Set());

  async function applyToTeam(teamId: number) {
    setApplyingTo(teamId);
    try {
      const d = await api.post<{ success: boolean; error?: string }>(
        `/api/teams/${teamId}/apply`,
        {},
      );
      if (d.success) {
        setAppliedSet((prev) => new Set([...prev, teamId]));
        showToast({ kind: 'success', message: 'Application submitted.' });
        if (invalidateKey) {
          queryClient.invalidateQueries({ queryKey: invalidateKey });
        }
      } else {
        showToast({ kind: 'danger', message: d.error ?? 'Failed to apply.' });
      }
    } catch {
      showToast({ kind: 'danger', message: 'Network error.' });
    } finally {
      setApplyingTo(null);
    }
  }

  function isApplied(teamId: number) {
    return appliedSet.has(teamId);
  }

  function isApplying(teamId: number) {
    return applyingTo === teamId;
  }

  return { applyingTo, appliedSet, applyToTeam, isApplied, isApplying };
}
