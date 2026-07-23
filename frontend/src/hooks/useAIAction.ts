"use client";

import { useAIProcessingContext } from "@/providers/AIProcessingProvider";

export function useAIAction() {
  return useAIProcessingContext();
}
