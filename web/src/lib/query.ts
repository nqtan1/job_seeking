import { useMutation, useQueryClient } from '@tanstack/react-query'

/** A mutation that refreshes the listed queries when it succeeds. */
export function useInvalidating<V, R>(fn: (v: V) => Promise<R>, keys: string[][]) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => keys.forEach((queryKey) => qc.invalidateQueries({ queryKey })),
  })
}
