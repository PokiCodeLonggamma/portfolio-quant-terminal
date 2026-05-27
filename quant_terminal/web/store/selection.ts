"use client";
import { create } from "zustand";
import { persist } from "zustand/middleware";

type SelectionState = {
  currentTicker: string | null;
  setCurrentTicker: (t: string | null) => void;
};

export const useSelectionStore = create<SelectionState>()(
  persist(
    (set) => ({
      currentTicker: null,
      setCurrentTicker: (t) => set({ currentTicker: t }),
    }),
    { name: "qt-selection" },
  ),
);
