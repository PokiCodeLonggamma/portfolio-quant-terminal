"use client";
import { create } from "zustand";
import { persist } from "zustand/middleware";

type UIState = {
  sidebarCollapsed: boolean;
  collapsedSections: Record<string, boolean>;
  toggleSidebar: () => void;
  toggleSection: (key: string) => void;
};

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      collapsedSections: {},
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      toggleSection: (key) =>
        set((s) => ({
          collapsedSections: {
            ...s.collapsedSections,
            [key]: !s.collapsedSections[key],
          },
        })),
    }),
    { name: "qt-ui" },
  ),
);
